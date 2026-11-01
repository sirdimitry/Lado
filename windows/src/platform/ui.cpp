#include "ui.h"

#include <algorithm>
#include <array>
#include <cstdlib>
#include <cwchar>
#include <iterator>
#include <vector>

#include "autostart.h"
#include "foreground.h"
#include "resource.h"
#include "strings.h"
#include "util.h"

namespace lado {
namespace {

constexpr wchar_t kWindowClass[] = L"LadoSettingsWindow";
constexpr int kBaseWidth = 640;
constexpr int kBaseHeight = 612;

constexpr int kStatus = 1000;
constexpr int kAutomatic = 1001;
constexpr int kIntervalLabel = 1002;
constexpr int kInterval = 1003;
constexpr int kWords = 1004;
constexpr int kApps = 1005;
constexpr int kCaseSensitive = 1006;
constexpr int kAutostart = 1007;
constexpr int kGroupLayout = 1010;
constexpr int kGroupWords = 1011;
constexpr int kGroupApps = 1012;
constexpr int kWordsNote = 1013;
constexpr int kAppsNote = 1014;
constexpr int kPrivacy = 1015;

constexpr int kIntervals[] = {300, 400, 500, 600};

std::wstring get_text(HWND control) {
  const int length = GetWindowTextLengthW(control);
  if (length <= 0) return {};
  std::wstring text(static_cast<size_t>(length) + 1, L'\0');
  GetWindowTextW(control, text.data(), length + 1);
  text.resize(static_cast<size_t>(length));
  return text;
}

std::vector<std::wstring> split_lines(std::wstring_view text) {
  std::vector<std::wstring> lines;
  size_t start = 0;
  while (start <= text.size()) {
    size_t end = text.find(L'\n', start);
    if (end == std::wstring_view::npos) end = text.size();
    std::wstring line(text.substr(start, end - start));
    while (!line.empty() && (line.back() == L'\r' || line.back() == L' ')) {
      line.pop_back();
    }
    if (!line.empty()) lines.push_back(std::move(line));
    if (end == text.size()) break;
    start = end + 1;
  }
  return lines;
}

bool is_checked(HWND control) {
  return SendMessageW(control, BM_GETCHECK, 0, 0) == BST_CHECKED;
}

void set_checked(HWND control, bool checked) {
  SendMessageW(control, BM_SETCHECK, checked ? BST_CHECKED : BST_UNCHECKED, 0);
}

}  // namespace

bool SettingsWindow::visible() const {
  return hwnd_ != nullptr && IsWindowVisible(hwnd_) != FALSE;
}

int SettingsWindow::scale(int value) const {
  return MulDiv(value, dpi_, 96);
}

HWND SettingsWindow::create_control(const wchar_t* class_name, const wchar_t* text,
                                    DWORD style, DWORD ex_style, int control_id) {
  return CreateWindowExW(
      ex_style, class_name, text, WS_CHILD | WS_VISIBLE | style, 0, 0, 0, 0,
      hwnd_, reinterpret_cast<HMENU>(static_cast<INT_PTR>(control_id)),
      instance_, nullptr);
}

void SettingsWindow::create_controls() {
  const UiStrings& strings = ui_strings();
  constexpr DWORD kStatic = SS_LEFT | SS_NOPREFIX;
  HINSTANCE instance = instance_;

  group_layout_ = create_control(L"BUTTON", strings.group_layout,
                                 BS_GROUPBOX, 0, kGroupLayout);
  group_words_ = create_control(L"BUTTON", strings.group_words, BS_GROUPBOX, 0,
                                kGroupWords);
  group_apps_ = create_control(L"BUTTON", strings.group_apps, BS_GROUPBOX, 0,
                               kGroupApps);

  status_ = create_control(L"STATIC", L"", kStatic | SS_ENDELLIPSIS, 0, kStatus);

  automatic_ = create_control(L"BUTTON", strings.automatic,
                              BS_AUTOCHECKBOX | WS_TABSTOP, 0, kAutomatic);
  interval_label_ = create_control(L"STATIC", strings.interval_label, kStatic, 0,
                                   kIntervalLabel);
  interval_ = create_control(L"COMBOBOX", L"",
                             CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP, 0,
                             kInterval);
  for (int value : kIntervals) {
    wchar_t item[32] = {};
    _snwprintf(item, std::size(item), L"%d %s", value, strings.interval_ms);
    item[std::size(item) - 1] = L'\0';
    SendMessageW(interval_, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(item));
  }

  words_note_ = create_control(L"STATIC", strings.words_note, kStatic, 0,
                               kWordsNote);
  words_ = create_control(L"EDIT", L"",
                          ES_MULTILINE | ES_AUTOVSCROLL | WS_VSCROLL |
                              ES_WANTRETURN | WS_TABSTOP,
                          WS_EX_CLIENTEDGE, kWords);

  apps_note_ =
      create_control(L"STATIC", strings.apps_note, kStatic, 0, kAppsNote);
  apps_ = create_control(L"EDIT", L"",
                         ES_MULTILINE | ES_AUTOVSCROLL | WS_VSCROLL |
                             ES_WANTRETURN | WS_TABSTOP,
                         WS_EX_CLIENTEDGE, kApps);

  case_sensitive_ = create_control(L"BUTTON", strings.case_sensitive,
                                   BS_AUTOCHECKBOX | WS_TABSTOP, 0,
                                   kCaseSensitive);
  autostart_ = create_control(L"BUTTON", strings.start_with_windows,
                              BS_AUTOCHECKBOX | WS_TABSTOP, 0, kAutostart);
  privacy_ = create_control(L"STATIC", strings.privacy_note, kStatic, 0, kPrivacy);

  save_ = create_control(L"BUTTON", strings.save,
                         BS_DEFPUSHBUTTON | WS_TABSTOP, 0, IDOK);
  cancel_ = create_control(L"BUTTON", strings.cancel, BS_PUSHBUTTON | WS_TABSTOP,
                           0, IDCANCEL);
  (void)instance;
}

void SettingsWindow::destroy_fonts() {
  if (font_ != nullptr) {
    DeleteObject(font_);
    font_ = nullptr;
  }
  if (font_bold_ != nullptr) {
    DeleteObject(font_bold_);
    font_bold_ = nullptr;
  }
}

void SettingsWindow::update_fonts() {
  destroy_fonts();
  font_ = CreateFontW(-MulDiv(9, dpi_, 72), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                      DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                      CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE,
                      L"Segoe UI");
  font_bold_ = CreateFontW(-MulDiv(9, dpi_, 72), 0, 0, 0, FW_SEMIBOLD, FALSE,
                           FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
                           CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                           DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
  if (font_ == nullptr) return;

  const std::array<HWND, 16> controls = {
      status_,      automatic_,     interval_label_, interval_,  words_note_,
      words_,       group_layout_,  group_words_,    group_apps_, apps_note_,
      apps_,        case_sensitive_, autostart_,     privacy_,   save_,
      cancel_};
  for (HWND control : controls) {
    if (control != nullptr) {
      SendMessageW(control, WM_SETFONT, reinterpret_cast<WPARAM>(font_), TRUE);
    }
  }
  if (group_layout_ != nullptr) {
    SendMessageW(group_layout_, WM_SETFONT,
                 reinterpret_cast<WPARAM>(font_bold_), TRUE);
    SendMessageW(group_words_, WM_SETFONT,
                 reinterpret_cast<WPARAM>(font_bold_), TRUE);
    SendMessageW(group_apps_, WM_SETFONT,
                 reinterpret_cast<WPARAM>(font_bold_), TRUE);
  }
}

void SettingsWindow::relayout() {
  const int m = scale(20);
  auto place = [&](HWND control, int x, int y, int width, int height) {
    if (control != nullptr) {
      MoveWindow(control, scale(x), scale(y), scale(width), scale(height), TRUE);
    }
  };

  place(status_, 20, 16, 600, 22);
  place(group_layout_, 20, 46, 600, 104);
  place(automatic_, 36, 68, 560, 24);
  place(interval_label_, 36, 100, 150, 22);
  place(interval_, 190, 98, 140, 240);

  place(group_words_, 20, 158, 600, 150);
  place(words_note_, 36, 176, 560, 34);
  place(words_, 36, 214, 568, 84);

  place(group_apps_, 20, 318, 600, 150);
  place(apps_note_, 36, 336, 560, 34);
  place(apps_, 36, 374, 568, 84);

  place(case_sensitive_, 20, 480, 300, 24);
  place(autostart_, 340, 480, 280, 24);
  place(privacy_, 20, 510, 600, 48);

  place(save_, 446, 566, 94, 30);
  place(cancel_, 550, 566, 70, 30);
  (void)m;
}

void SettingsWindow::load_into_controls(bool autostart) {
  set_checked(automatic_, settings_.automatic);
  set_checked(case_sensitive_, settings_.case_sensitive);
  set_checked(autostart_, autostart);

  int selected = 0;
  int best = 1 << 30;
  for (int i = 0; i < static_cast<int>(std::size(kIntervals)); ++i) {
    const int distance = std::abs(kIntervals[i] - settings_.double_shift_ms);
    if (distance < best) {
      best = distance;
      selected = i;
    }
  }
  SendMessageW(interval_, CB_SETCURSEL, selected, 0);

  std::wstring words;
  for (const auto& word : settings_.exceptions) {
    words += word;
    words += L"\r\n";
  }
  SetWindowTextW(words_, words.c_str());

  std::wstring apps;
  for (const auto& app : settings_.excluded_apps) {
    apps += app;
    apps += L"\r\n";
  }
  SetWindowTextW(apps_, apps.c_str());
}

void SettingsWindow::collect_and_save() {
  Settings updated = settings_;
  updated.automatic = is_checked(automatic_);
  updated.case_sensitive = is_checked(case_sensitive_);

  const int selected =
      static_cast<int>(SendMessageW(interval_, CB_GETCURSEL, 0, 0));
  if (selected >= 0 && selected < static_cast<int>(std::size(kIntervals))) {
    updated.double_shift_ms = kIntervals[selected];
  }

  updated.exceptions = split_lines(get_text(words_));
  updated.excluded_apps = split_lines(get_text(apps_));
  updated = normalize_settings(std::move(updated));

  const bool autostart = is_checked(autostart_);
  if (handler_) handler_(updated, autostart);
  DestroyWindow(hwnd_);
}

void SettingsWindow::close() {
  if (hwnd_ != nullptr && IsWindow(hwnd_) != FALSE) {
    DestroyWindow(hwnd_);
  }
}

void SettingsWindow::activate() {
  if (hwnd_ == nullptr) return;
  ShowWindow(hwnd_, SW_SHOWNORMAL);
  force_foreground(hwnd_);
  if (automatic_ != nullptr) SetFocus(automatic_);
}

void SettingsWindow::set_status(std::wstring_view status) {
  if (status_ == nullptr) return;
  const std::wstring text(status);
  if (get_text(status_) == text) return;
  SetWindowTextW(status_, text.c_str());
  InvalidateRect(status_, nullptr, TRUE);
}

bool SettingsWindow::show(HINSTANCE instance, HWND owner, const Settings& settings,
                          bool autostart, std::wstring status,
                          SaveHandler handler) {
  instance_ = instance;
  owner_ = owner;
  settings_ = settings;
  handler_ = std::move(handler);

  if (hwnd_ != nullptr && IsWindow(hwnd_) != FALSE) {
    load_into_controls(autostart);
    set_status(status);
    activate();
    return true;
  }

  static bool registered = false;
  if (!registered) {
    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(wc);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = &SettingsWindow::proc;
    wc.hInstance = instance;
    wc.hIcon = reinterpret_cast<HICON>(LoadImageW(
        instance, MAKEINTRESOURCEW(IDI_APP), IMAGE_ICON, 32, 32, LR_DEFAULTCOLOR));
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    wc.lpszClassName = kWindowClass;
    if (!RegisterClassExW(&wc)) return false;
    registered = true;
  }

  dpi_ = GetDpiForSystem();
  const DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_CLIPCHILDREN;
  const DWORD ex_style = WS_EX_TOOLWINDOW;

  RECT rect = {0, 0, scale(kBaseWidth), scale(kBaseHeight)};
  AdjustWindowRectExForDpi(&rect, style, FALSE, ex_style, dpi_);
  const int width = rect.right - rect.left;
  const int height = rect.bottom - rect.top;

  RECT work = {};
  SystemParametersInfoW(SPI_GETWORKAREA, 0, &work, 0);
  const int x = work.left + ((work.right - work.left) - width) / 2;
  const int y = work.top + ((work.bottom - work.top) - height) / 2;

  HWND window = CreateWindowExW(ex_style, kWindowClass, ui_strings().settings_title,
                                style, x, y, width, height, owner, nullptr,
                                instance, this);
  if (window == nullptr) return false;
  hwnd_ = window;

  load_into_controls(autostart);
  set_status(status);
  ShowWindow(window, SW_SHOWNORMAL);
  UpdateWindow(window);
  force_foreground(window);
  if (automatic_ != nullptr) SetFocus(automatic_);
  return true;
}

LRESULT CALLBACK SettingsWindow::proc(HWND hwnd, UINT message, WPARAM wparam,
                                      LPARAM lparam) {
  SettingsWindow* self = nullptr;
  if (message == WM_NCCREATE) {
    auto* create = reinterpret_cast<CREATESTRUCTW*>(lparam);
    self = static_cast<SettingsWindow*>(create->lpCreateParams);
    SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
  } else {
    self = reinterpret_cast<SettingsWindow*>(
        GetWindowLongPtrW(hwnd, GWLP_USERDATA));
  }
  if (self == nullptr) return DefWindowProcW(hwnd, message, wparam, lparam);
  self->hwnd_ = hwnd;
  return self->handle(message, wparam, lparam);
}

LRESULT SettingsWindow::handle(UINT message, WPARAM wparam, LPARAM lparam) {
  switch (message) {
    case WM_CREATE:
      create_controls();
      update_fonts();
      relayout();
      return 0;
    case WM_COMMAND:
      switch (LOWORD(wparam)) {
        case IDOK:
          collect_and_save();
          return 0;
        case IDCANCEL:
          DestroyWindow(hwnd_);
          return 0;
        default:
          break;
      }
      return 0;
    case WM_CTLCOLORSTATIC:
    case WM_CTLCOLORBTN: {
      HDC context = reinterpret_cast<HDC>(wparam);
      SetBkMode(context, TRANSPARENT);
      return reinterpret_cast<LRESULT>(GetSysColorBrush(COLOR_WINDOW));
    }
    case WM_CLOSE:
      DestroyWindow(hwnd_);
      return 0;
    case WM_DESTROY:
      destroy_fonts();
      hwnd_ = nullptr;
      return 0;
    case WM_DPICHANGED: {
      dpi_ = HIWORD(wparam);
      const RECT* suggested = reinterpret_cast<const RECT*>(lparam);
      SetWindowPos(hwnd_, nullptr, suggested->left, suggested->top,
                   suggested->right - suggested->left,
                   suggested->bottom - suggested->top,
                   SWP_NOZORDER | SWP_NOACTIVATE);
      update_fonts();
      relayout();
      return 0;
    }
    case WM_KEYDOWN:
      if (wparam == VK_ESCAPE) {
        DestroyWindow(hwnd_);
        return 0;
      }
      break;
    default:
      break;
  }
  return DefWindowProcW(hwnd_, message, wparam, lparam);
}

}  // namespace lado
