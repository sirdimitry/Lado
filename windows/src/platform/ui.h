// Programmatic native settings window. Building the controls in code (rather
// than a dialog template) keeps the bilingual layout and DPI scaling explicit.
#pragma once

#include <windows.h>

#include <functional>
#include <string>
#include <string_view>

#include "settings.h"

namespace lado {

class SettingsWindow {
 public:
  using SaveHandler = std::function<void(const Settings& settings, bool autostart)>;

  bool show(HINSTANCE instance, HWND owner, const Settings& settings,
            bool autostart, std::wstring status, SaveHandler handler);
  void close();
  bool visible() const;
  void activate();
  void set_status(std::wstring_view status);
  HWND hwnd() const { return hwnd_; }

 private:
  static LRESULT CALLBACK proc(HWND hwnd, UINT message, WPARAM wparam,
                               LPARAM lparam);

  LRESULT handle(UINT message, WPARAM wparam, LPARAM lparam);
  void create_controls();
  void update_fonts();
  void destroy_fonts();
  void relayout();
  void load_into_controls(bool autostart);
  void collect_and_save();
  int scale(int value) const;
  HWND create_control(const wchar_t* class_name, const wchar_t* text,
                      DWORD style, DWORD ex_style, int control_id);

  HINSTANCE instance_ = nullptr;
  HWND owner_ = nullptr;
  HWND hwnd_ = nullptr;
  int dpi_ = 96;
  HICON icon_ = nullptr;

  HWND status_ = nullptr;
  HWND automatic_ = nullptr;
  HWND case_sensitive_ = nullptr;
  HWND autostart_ = nullptr;
  HWND interval_label_ = nullptr;
  HWND interval_ = nullptr;
  HWND group_layout_ = nullptr;
  HWND group_words_ = nullptr;
  HWND group_apps_ = nullptr;
  HWND words_note_ = nullptr;
  HWND apps_note_ = nullptr;
  HWND words_ = nullptr;
  HWND apps_ = nullptr;
  HWND privacy_ = nullptr;
  HWND save_ = nullptr;
  HWND cancel_ = nullptr;

  HFONT font_ = nullptr;
  HFONT font_bold_ = nullptr;

  Settings settings_;
  SaveHandler handler_;
};

}  // namespace lado
