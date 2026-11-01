// Two languages, matching the macOS app: Russian and English UI strings.
#pragma once

namespace lado {

struct UiStrings {
  const wchar_t* settings_title;
  const wchar_t* group_layout;
  const wchar_t* group_words;
  const wchar_t* group_apps;
  const wchar_t* automatic;
  const wchar_t* case_sensitive;
  const wchar_t* interval_label;
  const wchar_t* interval_ms;
  const wchar_t* start_with_windows;
  const wchar_t* words_note;
  const wchar_t* apps_note;
  const wchar_t* privacy_note;
  const wchar_t* save;
  const wchar_t* cancel;

  const wchar_t* status_layout_format;  // "Раскладка: %s"
  const wchar_t* lang_ru;
  const wchar_t* lang_en;
  const wchar_t* lang_other;
  const wchar_t* suffix_paused;
  const wchar_t* suffix_secure;
  const wchar_t* suffix_excluded;

  const wchar_t* tray_format;   // "Lado · %s"
  const wchar_t* menu_automatic;
  const wchar_t* menu_pause;
  const wchar_t* menu_exclude;
  const wchar_t* menu_unexclude;
  const wchar_t* menu_settings;
  const wchar_t* menu_about;
  const wchar_t* menu_exit;

  const wchar_t* about_title;
  const wchar_t* about_body;  // takes the version as %s
  const wchar_t* error_hook;
  const wchar_t* error_lexicon;
  const wchar_t* error_title;
};

const UiStrings& ui_strings();

}  // namespace lado
