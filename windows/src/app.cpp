#include "app.h"

#include <windows.h>

#include <algorithm>
#include <array>
#include <cwchar>
#include <iterator>
#include <string>

#include "platform/autostart.h"
#include "platform/foreground.h"
#include "platform/input.h"
#include "platform/log.h"
#include "resource.h"
#include "strings.h"
#include "util.h"

#ifndef LADO_VERSION_STRING
#define LADO_VERSION_STRING "0.1.0-windows.1"
#endif

namespace lado {

const wchar_t kAppWindowClass[] = L"LadoMainWindow";

namespace {

App* g_app_for_events = nullptr;

bool clear_context_key(UINT vk) {
  switch (vk) {
    case VK_RETURN:
    case VK_TAB:
    case VK_ESCAPE:
    case VK_LEFT:
    case VK_RIGHT:
    case VK_UP:
    case VK_DOWN:
    case VK_HOME:
    case VK_END:
    case VK_PRIOR:
    case VK_NEXT:
    case VK_INSERT:
    case VK_DELETE:
    case VK_CLEAR:
    case VK_PAUSE:
      return true;
    default:
      return vk >= VK_F1 && vk <= VK_F24;
  }
}

std::wstring format_tooltip(const wchar_t* format, const std::wstring& value) {
  wchar_t buffer[256] = {};
  _snwprintf(buffer, std::size(buffer), format, value.c_str());
  buffer[std::size(buffer) - 1] = L'\0';
  return buffer;
}

// Cheap, synchronous password check for classic edit controls. The UIA worker
// covers Chromium/UWP, but this one cannot be stale.
bool focused_classic_password() {
  const HWND foreground = GetForegroundWindow();
  if (foreground == nullptr) return false;
  const DWORD thread = GetWindowThreadProcessId(foreground, nullptr);
  if (thread == 0) return false;
  GUITHREADINFO info = {};
  info.cbSize = sizeof(info);
  if (!GetGUIThreadInfo(thread, &info) || info.hwndFocus == nullptr) return false;
  wchar_t class_name[64] = {};
  if (GetClassNameW(info.hwndFocus, class_name,
                    static_cast<int>(std::size(class_name))) == 0) {
    return false;
  }
  if (_wcsicmp(class_name, L"Edit") != 0) return false;
  return (GetWindowLongW(info.hwndFocus, GWL_STYLE) & ES_PASSWORD) != 0;
}

}  // namespace

App::App(HINSTANCE instance) : instance_(instance) {}

App::~App() = default;

bool App::initialize() {
  settings_ = load_settings(settings_path());
  gesture_.set_interval(settings_.double_shift_ms / 1000.0);
  caps_lock_ = (GetKeyState(VK_CAPITAL) & 1) != 0;

  // QA hook: lets an isolated harness drive the real pipeline with SendInput.
  // Release builds never set this variable; injected input stays ignored.
  accept_injected_ =
      GetEnvironmentVariableW(L"LADO_QA_ACCEPT_INJECTED", nullptr, 0) > 0;

  const HRSRC resource =
      FindResourceW(instance_, MAKEINTRESOURCEW(IDR_LEXICON), RT_RCDATA);
  if (resource == nullptr) {
    log_message(L"embedded lexicon resource missing");
    MessageBoxW(nullptr, ui_strings().error_lexicon, ui_strings().error_title,
                MB_OK | MB_ICONERROR);
    return false;
  }
  const HGLOBAL loaded = LoadResource(instance_, resource);
  void* data = LockResource(loaded);
  const DWORD size = SizeofResource(instance_, resource);
  if (data == nullptr || size == 0 || !lexicon_.load_from_memory(data, size)) {
    log_message(L"embedded lexicon invalid (%lu bytes)", size);
    MessageBoxW(nullptr, ui_strings().error_lexicon, ui_strings().error_title,
                MB_OK | MB_ICONERROR);
    return false;
  }
  buffer_ = std::make_unique<Buffer>(Detector(settings_, lexicon_), now_seconds);

  WNDCLASSEXW window_class = {};
  window_class.cbSize = sizeof(window_class);
  window_class.lpfnWndProc = &App::window_proc;
  window_class.hInstance = instance_;
  window_class.hCursor = LoadCursorW(nullptr, IDC_ARROW);
  window_class.hIcon = reinterpret_cast<HICON>(LoadImageW(
      instance_, MAKEINTRESOURCEW(IDI_APP), IMAGE_ICON, 32, 32, LR_DEFAULTCOLOR));
  window_class.lpszClassName = kAppWindowClass;
  if (!RegisterClassExW(&window_class) &&
      GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
    log_message(L"RegisterClassEx failed: %lu", GetLastError());
    return false;
  }

  window_ = CreateWindowExW(WS_EX_TOOLWINDOW, kAppWindowClass, L"Lado",
                            WS_OVERLAPPED, 0, 0, 0, 0, nullptr, nullptr,
                            instance_, this);
  if (window_ == nullptr) {
    log_message(L"CreateWindowEx failed: %lu", GetLastError());
    return false;
  }

  if (!tray_.create(instance_, window_, kTrayMessage)) {
    log_message(L"tray icon creation failed");
    return false;
  }

  if (!hook_.install(
          window_, [this](const KeyEvent& event) { return on_key(event); },
          [this] { on_mouse(); })) {
    MessageBoxW(nullptr, ui_strings().error_hook, ui_strings().error_title,
                MB_OK | MB_ICONERROR);
    return false;
  }

  g_app_for_events = this;
  foreground_hook_ = SetWinEventHook(
      EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, nullptr,
      &App::win_event_proc, 0, 0, WINEVENT_OUTOFCONTEXT);
  focus_hook_ = SetWinEventHook(EVENT_OBJECT_FOCUS, EVENT_OBJECT_FOCUS, nullptr,
                                &App::win_event_proc, 0, 0,
                                WINEVENT_OUTOFCONTEXT);
  if (foreground_hook_ == nullptr || focus_hook_ == nullptr) {
    log_message(L"SetWinEventHook failed: %lu", GetLastError());
  }

  secure_ = new SecureWatcher();
  secure_->start();

  SetTimer(window_, kTimerState, 250, nullptr);
  refresh_state();
  return true;
}

void App::shutdown() {
  if (foreground_hook_ != nullptr) {
    UnhookWinEvent(foreground_hook_);
    foreground_hook_ = nullptr;
  }
  if (focus_hook_ != nullptr) {
    UnhookWinEvent(focus_hook_);
    focus_hook_ = nullptr;
  }
  if (g_app_for_events == this) g_app_for_events = nullptr;

  if (window_ != nullptr) {
    KillTimer(window_, kTimerState);
    KillTimer(window_, kTimerApply);
  }
  settings_window_.close();
  tray_.destroy();
  hook_.uninstall();
  if (secure_ != nullptr) {
    if (secure_->stop()) {
      delete secure_;
    }
    // Otherwise a UIA call is still blocked: intentionally leaked so the
    // detached worker never touches freed memory at process exit.
    secure_ = nullptr;
  }
}

int App::run(int show_command) {
  (void)show_command;
  if (!initialize()) {
    shutdown();
    return 1;
  }
  MSG message = {};
  while (GetMessageW(&message, nullptr, 0, 0) > 0) {
    const HWND settings = settings_window_.hwnd();
    if (settings != nullptr && IsWindowVisible(settings) != FALSE &&
        IsDialogMessageW(settings, &message)) {
      continue;
    }
    TranslateMessage(&message);
    DispatchMessageW(&message);
  }
  shutdown();
  return 0;
}

LRESULT CALLBACK App::window_proc(HWND hwnd, UINT message, WPARAM wparam,
                                  LPARAM lparam) {
  App* self = nullptr;
  if (message == WM_NCCREATE) {
    auto* create = reinterpret_cast<CREATESTRUCTW*>(lparam);
    self = static_cast<App*>(create->lpCreateParams);
    SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
    if (self != nullptr) self->window_ = hwnd;
  } else {
    self = reinterpret_cast<App*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
  }
  if (self == nullptr) return DefWindowProcW(hwnd, message, wparam, lparam);
  return self->handle(hwnd, message, wparam, lparam);
}

LRESULT App::handle(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
  switch (message) {
    case kTrayMessage: {
      switch (LOWORD(lparam)) {
        case WM_LBUTTONUP:
        case WM_RBUTTONUP: {
          POINT point = {};
          GetCursorPos(&point);
          show_menu(point);
          return 0;
        }
        case WM_LBUTTONDBLCLK:
          show_settings();
          return 0;
        default:
          return 0;
      }
    }
    case kApplyMessage:
      apply_pending();
      return 0;
    case kShowSettingsMessage:
      show_settings();
      return 0;
    case WM_TIMER:
      if (wparam == kTimerState) {
        on_timer();
      } else if (wparam == kTimerApply) {
        apply_pending();
      }
      return 0;
    case WM_COMMAND:
      switch (LOWORD(wparam)) {
        case kCommandSettings: show_settings(); return 0;
        case kCommandPause:
          paused_ = !paused_;
          buffer_->clear();
          cancel_pending();
          gesture_.clear();
          update_tray();
          update_status_window();
          return 0;
        case kCommandAutomatic:
          settings_.automatic = !settings_.automatic;
          save_preferences();
          buffer_->clear();
          update_tray();
          return 0;
        case kCommandExclude: {
          const std::wstring process = menu_process_;
          if (process.empty() || menu_pid_ == GetCurrentProcessId()) {
            return 0;
          }
          auto& excluded = settings_.excluded_apps;
          const std::wstring folded = casefold(process);
          const auto found = std::find_if(
              excluded.begin(), excluded.end(), [&](const std::wstring& item) {
                return casefold(item) == folded;
              });
          if (found != excluded.end()) {
            excluded.erase(found);
          } else if (excluded.size() < 5000) {
            excluded.push_back(process);
          }
          save_preferences();
          buffer_->clear();
          update_tray();
          update_status_window();
          return 0;
        }
        case kCommandAbout: show_about(); return 0;
        case kCommandQuit: DestroyWindow(hwnd); return 0;
        default:
          return 0;
      }
    case WM_CLOSE:
      DestroyWindow(hwnd);
      return 0;
    case WM_DESTROY:
      PostQuitMessage(0);
      return 0;
    default:
      break;
  }
  return DefWindowProcW(hwnd, message, wparam, lparam);
}

void CALLBACK App::win_event_proc(HWINEVENTHOOK hook, DWORD event, HWND hwnd,
                                  LONG object, LONG child, DWORD thread,
                                  DWORD time) {
  (void)hook;
  (void)hwnd;
  (void)object;
  (void)child;
  (void)thread;
  (void)time;
  App* app = g_app_for_events;
  if (app != nullptr) app->on_system_event(event);
}

void App::on_system_event(DWORD event) {
  if (event == EVENT_SYSTEM_FOREGROUND) {
    focus_.refresh();
    buffer_->clear();
    cancel_pending();
  }
  if (secure_ != nullptr) secure_->refresh_soon();
}

bool App::on_key(const KeyEvent& event) {
  if (event.injected) {
    if (!accept_injected_ ||
        event.extra_info == static_cast<uintptr_t>(input::kInjectionTag)) {
      return false;
    }
  }

  const UINT vk = event.vk;
  if (vk == VK_SHIFT || vk == VK_LSHIFT || vk == VK_RSHIFT) {
    if (event.down) ++generation_;
    return handle_shift(event);
  }

  if (vk == VK_CAPITAL && event.down) caps_lock_ = !caps_lock_;

  if (vk == VK_LWIN || vk == VK_RWIN) win_down_ = event.down;
  if (vk == VK_CONTROL || vk == VK_LCONTROL || vk == VK_RCONTROL) {
    ctrl_down_ = event.down;
  }
  if (vk == VK_MENU || vk == VK_LMENU || vk == VK_RMENU) alt_down_ = event.down;

  if (!event.down) return false;

  ++generation_;
  gesture_.key_used();

  const HWND previous_window = focus_.info().hwnd;
  const Lang previous_language = focus_.info().lang;
  focus_.refresh();
  if (focus_.info().hwnd != previous_window ||
      focus_.info().lang != previous_language) {
    buffer_->clear();
  }

  if (!processing_allowed()) {
    buffer_->clear();
    return false;
  }
  if (ctrl_down_ || alt_down_ || win_down_) {
    buffer_->clear();
    return false;
  }

  if (vk == VK_BACK) {
    buffer_->backspace();
    return false;
  }
  if (clear_context_key(vk)) {
    buffer_->clear();
    return false;
  }
  if (vk == VK_SPACE) {
    if (auto edit = buffer_->finish(L" ", settings_.automatic)) {
      begin_edit(*edit, 30);
    }
    return false;
  }

  const std::wstring text = char_for_key(event);
  if (text.size() != 1) {
    buffer_->clear();
    return false;
  }
  const wchar_t character = text[0];
  if (character < 0x20 || character > 0x052F) {
    buffer_->clear();
    return false;
  }
  buffer_->feed(text);
  return false;
}

bool App::handle_shift(const KeyEvent& event) {
  if (event.vk == VK_RSHIFT) {
    shift_right_ = event.down;
  } else {
    shift_left_ = event.down;
  }

  if (!event.down) {
    if (!shift_left_ && !shift_right_) {
      gesture_.update(false, now_seconds(),
                      ctrl_down_ || alt_down_ || win_down_);
    }
    return false;
  }

  if (shift_left_ && shift_right_) {
    gesture_.clear();
    return false;
  }

  if (gesture_.update(true, now_seconds(),
                      ctrl_down_ || alt_down_ || win_down_)) {
    begin_manual_conversion();
  }
  return false;
}

void App::on_mouse() {
  ++generation_;
  cancel_pending();
  buffer_->clear();
  gesture_.key_used();
}

void App::on_timer() {
  refresh_state();
}

void App::refresh_state() {
  const HWND previous_window = focus_.info().hwnd;
  const Lang previous_language = focus_.info().lang;
  focus_.refresh();
  if (focus_.info().hwnd != previous_window ||
      focus_.info().lang != previous_language) {
    buffer_->clear();
    cancel_pending();
  }
  update_tray();
  update_status_window();
}

void App::update_tray() {
  const UiStrings& strings = ui_strings();
  const Lang language = focus_.info().lang;
  const SecureState secure = secure_->effective_state();

  TrayIconKind kind = TrayIconKind::Other;
  if (paused_) {
    kind = TrayIconKind::Paused;
  } else if (secure == SecureState::Secure) {
    kind = language == Lang::Ru ? TrayIconKind::RuSecure
                                : language == Lang::En ? TrayIconKind::EnSecure
                                                       : TrayIconKind::Other;
  } else if (language == Lang::Ru) {
    kind = TrayIconKind::Ru;
  } else if (language == Lang::En) {
    kind = TrayIconKind::En;
  }

  std::wstring status;
  if (paused_) {
    status = strings.suffix_paused;
  } else {
    status = language_short_name(language);
    if (!focus_.info().process.empty() &&
        focus_.info().pid != GetCurrentProcessId()) {
      status += L" · " + focus_.info().process;
    }
    if (secure == SecureState::Secure) {
      status += L" · " + std::wstring(strings.suffix_secure);
    } else if (current_is_excluded()) {
      status += L" · " + std::wstring(strings.suffix_excluded);
    }
  }

  tray_.update(kind, format_tooltip(strings.tray_format, status));
}

void App::update_status_window() {
  if (settings_window_.visible()) settings_window_.set_status(status_text());
}

void App::show_menu(POINT point) {
  const UiStrings& strings = ui_strings();
  // Pin the target so the command applies to the app that was active when the
  // menu opened, not to whatever happens to be foreground when it closes.
  menu_process_ = focus_.info().process;
  menu_pid_ = focus_.info().pid;

  HMENU menu = CreatePopupMenu();
  if (menu == nullptr) return;

  const std::wstring header = L"Lado · " + language_short_name(focus_.info().lang);
  AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, header.c_str());
  AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
  AppendMenuW(menu, MF_STRING | (settings_.automatic ? MF_CHECKED : 0),
              kCommandAutomatic, strings.menu_automatic);
  AppendMenuW(menu, MF_STRING | (paused_ ? MF_CHECKED : 0), kCommandPause,
              strings.menu_pause);
  AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);

  const bool can_exclude =
      !menu_process_.empty() && menu_pid_ != GetCurrentProcessId();
  const bool excluded =
      menu_pid_ == GetCurrentProcessId() ||
      process_is_excluded(settings_.excluded_apps, menu_process_);
  AppendMenuW(menu, MF_STRING | (can_exclude ? 0u : MF_GRAYED), kCommandExclude,
              excluded ? strings.menu_unexclude : strings.menu_exclude);
  AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
  AppendMenuW(menu, MF_STRING, kCommandSettings, strings.menu_settings);
  AppendMenuW(menu, MF_STRING, kCommandAbout, strings.menu_about);
  AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
  AppendMenuW(menu, MF_STRING, kCommandQuit, strings.menu_exit);

  force_foreground(window_);
  const UINT command = TrackPopupMenuEx(
      menu, TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON, point.x, point.y,
      window_, nullptr);
  DestroyMenu(menu);
  PostMessageW(window_, WM_NULL, 0, 0);
  if (command != 0) SendMessageW(window_, WM_COMMAND, command, 0);
}

void App::show_settings() {
  settings_window_.show(
      instance_, window_, settings_, autostart_enabled(), status_text(),
      [this](const Settings& updated, bool autostart) {
        settings_ = updated;
        save_preferences();
        if (autostart_enabled() != autostart) set_autostart(autostart);
        gesture_.set_interval(settings_.double_shift_ms / 1000.0);
        buffer_->clear();
        update_tray();
        update_status_window();
      });
}

void App::show_about() {
  wchar_t body[1024] = {};
  _snwprintf(body, std::size(body), ui_strings().about_body,
             L"" LADO_VERSION_STRING);
  body[std::size(body) - 1] = L'\0';
  MessageBoxW(nullptr, body, ui_strings().about_title, MB_OK | MB_ICONINFORMATION);
}

void App::save_preferences() {
  if (!save_settings(settings_, settings_path())) {
    log_message(L"could not save settings");
  }
}

void App::begin_manual_conversion() {
  if (!processing_allowed()) {
    buffer_->clear();
    return;
  }
  auto edit = buffer_->manual();
  if (!edit) return;
  begin_edit(*edit, 1);
}

void App::begin_edit(const Edit& edit, UINT delay_ms) {
  if (edit.before.empty() || edit.after.empty()) return;
  if (edit.before.size() > 1024 || edit.after.size() > 2048) return;

  PendingEdit pending;
  pending.text = edit.after;
  pending.delete_units = static_cast<int>(edit.before.size());
  pending.target = focus_.info().hwnd;
  pending.layout = focus_.info().layout;
  pending.generation = generation_;
  pending_ = std::move(pending);
  SetTimer(window_, kTimerApply, delay_ms, nullptr);
}

void App::apply_pending() {
  if (!pending_) return;
  const PendingEdit pending = std::move(*pending_);
  pending_.reset();
  KillTimer(window_, kTimerApply);

  // Any abandoned edit means the on-screen text no longer agrees with the
  // buffer (the replacement never happened), so context is dropped.
  auto abandon = [this] { buffer_->clear(); };

  if (pending.generation != generation_) {
    abandon();
    return;
  }
  if (GetForegroundWindow() != pending.target) {
    abandon();
    return;
  }
  focus_.refresh();
  if (focus_.info().hwnd != pending.target) {
    abandon();
    return;
  }
  if (focused_classic_password()) {
    abandon();
    return;
  }
  if (!processing_allowed()) {
    abandon();
    return;
  }
  if (focus_.info().layout != pending.layout) {
    abandon();
    return;
  }
  if (pending.delete_units <= 0 || pending.text.empty()) {
    abandon();
    return;
  }
  if (!input::replace_backward(pending.delete_units, pending.text)) {
    log_message(L"SendInput rejected a replacement of %d units",
                pending.delete_units);
    abandon();
  }
}

void App::cancel_pending() {
  pending_.reset();
  if (window_ != nullptr) KillTimer(window_, kTimerApply);
}

bool App::processing_allowed() {
  if (paused_) return false;
  const FocusInfo& info = focus_.info();
  if (!info.valid || info.hwnd == nullptr) return false;
  if (info.pid == GetCurrentProcessId()) return false;
  if (info.process.empty()) return false;
  if (process_is_excluded(settings_.excluded_apps, info.process)) return false;
  if (secure_->effective_state() != SecureState::Clear) return false;
  if (info.lang == Lang::None) return false;
  return true;
}

bool App::current_is_excluded() const {
  const FocusInfo& info = focus_.info();
  if (info.pid != 0 && info.pid == GetCurrentProcessId()) return true;
  if (info.process.empty()) return false;
  return process_is_excluded(settings_.excluded_apps, info.process);
}

std::wstring App::char_for_key(const KeyEvent& event) {
  BYTE state[256] = {};
  if (shift_left_ || shift_right_) state[VK_SHIFT] = 0x80;
  if (caps_lock_) state[VK_CAPITAL] = 0x01;
  if (ctrl_down_) state[VK_CONTROL] = 0x80;
  if (alt_down_) state[VK_MENU] = 0x80;

  const HKL layout = focus_.info().layout;
  if (layout == nullptr) return {};

  wchar_t buffer[8] = {};
  const int result =
      ToUnicodeEx(event.vk, event.scan, state, buffer, 8, 0, layout);
  if (result < 0) {
    // Dead key: flush the pending composition so the next key is not combined.
    wchar_t flush[8] = {};
    ToUnicodeEx(event.vk, event.scan, state, flush, 8, 0, layout);
    return {};
  }
  if (result <= 0) return {};
  return std::wstring(buffer, static_cast<size_t>(result));
}

std::wstring App::language_full_name(Lang language) const {
  const UiStrings& strings = ui_strings();
  if (language == Lang::Ru) return strings.lang_ru;
  if (language == Lang::En) return strings.lang_en;
  return strings.lang_other;
}

std::wstring App::language_short_name(Lang language) const {
  if (language == Lang::Ru) return L"RU";
  if (language == Lang::En) return L"EN";
  return L"—";
}

std::wstring App::status_text() const {
  const UiStrings& strings = ui_strings();
  wchar_t buffer[512] = {};
  const std::wstring language = language_full_name(focus_.info().lang);
  _snwprintf(buffer, std::size(buffer), strings.status_layout_format,
             language.c_str());
  buffer[std::size(buffer) - 1] = L'\0';
  std::wstring text = buffer;

  if (!focus_.info().process.empty() &&
      focus_.info().pid != GetCurrentProcessId()) {
    text += L" · " + focus_.info().process;
  }
  if (paused_) {
    text += L" · " + std::wstring(strings.suffix_paused);
  } else if (secure_->effective_state() == SecureState::Secure) {
    text += L" · " + std::wstring(strings.suffix_secure);
  } else if (current_is_excluded()) {
    text += L" · " + std::wstring(strings.suffix_excluded);
  }
  return text;
}

}  // namespace lado
