// The tray application: owns the hooks, the bounded buffer and the Win32 UI.
#pragma once

#include <windows.h>

#include <memory>
#include <optional>
#include <string>

#include "engine.h"
#include "lexicon.h"
#include "platform/focus.h"
#include "platform/hook.h"
#include "platform/secure.h"
#include "platform/tray.h"
#include "platform/ui.h"
#include "settings.h"

namespace lado {

extern const wchar_t kAppWindowClass[];

constexpr UINT kTrayMessage = WM_APP + 1;
constexpr UINT kApplyMessage = WM_APP + 2;
constexpr UINT kShowSettingsMessage = WM_APP + 3;
constexpr UINT kManualMessage = WM_APP + 4;

class App {
 public:
  explicit App(HINSTANCE instance);
  ~App();

  int run(int show_command);
  static LRESULT CALLBACK window_proc(HWND hwnd, UINT message, WPARAM wparam,
                                      LPARAM lparam);

 private:
  enum Command : UINT {
    kCommandSettings = 1000,
    kCommandPause,
    kCommandAutomatic,
    kCommandExclude,
    kCommandAbout,
    kCommandQuit,
  };
  enum TimerId : UINT_PTR {
    kTimerState = 1,
    kTimerApply = 2,
    kTimerSelection = 3,
  };

  struct PendingEdit {
    std::wstring text;
    int delete_units = 0;
    HWND target = nullptr;
    HKL layout = nullptr;
    Lang target_language = Lang::None;
    uint64_t generation = 0;
    bool enter_after = false;
    bool clear_after = false;
  };

  bool initialize();
  void shutdown();
  LRESULT handle(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam);
  void on_system_event(DWORD event);

  static void CALLBACK win_event_proc(HWINEVENTHOOK hook, DWORD event,
                                      HWND hwnd, LONG object, LONG child,
                                      DWORD thread, DWORD time);

  bool on_key(const KeyEvent& event);
  bool handle_shift(const KeyEvent& event);
  void on_mouse();
  void on_timer();

  void refresh_state();
  void update_tray();
  void update_status_window();
  void show_menu(POINT point);
  void show_settings();
  void show_about();
  void save_preferences();
  void handle_manual_conversion();
  void convert_selection(const std::wstring& text);
  void poll_selection();
  void cancel_selection();
  void begin_edit(const Edit& edit, UINT delay_ms, bool clear_after = false,
                  bool enter_after = false);
  void apply_pending();
  void cancel_pending();

  bool processing_allowed();
  bool current_is_excluded() const;
  std::wstring char_for_key(const KeyEvent& event);
  std::wstring language_full_name(Lang lang) const;
  std::wstring language_short_name(Lang lang) const;
  std::wstring status_text() const;

  HINSTANCE instance_;
  HWND window_ = nullptr;
  Settings settings_;
  Lexicon lexicon_;
  std::unique_ptr<Buffer> buffer_;
  DoubleShift gesture_;
  FocusMonitor focus_;
  SecureWatcher* secure_ = nullptr;
  TrayIcon tray_;
  InputHook hook_;
  SettingsWindow settings_window_;
  HWINEVENTHOOK foreground_hook_ = nullptr;
  HWINEVENTHOOK focus_hook_ = nullptr;

  std::optional<PendingEdit> pending_;
  uint64_t generation_ = 0;
  bool paused_ = false;
  bool accept_injected_ = false;  // QA only: see LADO_QA_ACCEPT_INJECTED
  std::wstring menu_process_;
  DWORD menu_pid_ = 0;
  bool selection_pending_ = false;
  uint64_t selection_generation_ = 0;
  HWND selection_target_ = nullptr;
  ULONGLONG selection_deadline_ = 0;
  bool caps_lock_ = false;
  bool shift_left_ = false;
  bool shift_right_ = false;
  bool ctrl_down_ = false;
  bool alt_down_ = false;
  bool win_down_ = false;
};

}  // namespace lado
