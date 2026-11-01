// Only explicit preferences and word/app exceptions are written to disk; never
// typed text. The file lives in %APPDATA%\Lado\settings.json.
#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace lado {

struct Settings {
  bool automatic = true;
  int double_shift_ms = 400;
  bool case_sensitive = false;
  std::vector<std::wstring> exceptions;
  std::vector<std::wstring> excluded_apps = default_excluded_apps();

  static std::vector<std::wstring> default_excluded_apps();
};

std::filesystem::path settings_directory();
std::filesystem::path settings_path();

Settings load_settings(const std::filesystem::path& path);
bool save_settings(const Settings& settings, const std::filesystem::path& path);

// Trims and caps the two lists and clamps the gesture interval. Applies the
// same rules to a freshly loaded file and to values edited in the UI.
Settings normalize_settings(Settings settings);

// Shared with app exclusions: case-insensitive "is the executable excluded".
bool process_is_excluded(const std::vector<std::wstring>& excluded,
                         std::wstring_view executable_name);

}  // namespace lado
