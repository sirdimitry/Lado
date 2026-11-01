#include "settings.h"

#include <windows.h>

#include <algorithm>
#include <fstream>
#include <iterator>

#include "json.h"
#include "util.h"

namespace lado {
namespace {

constexpr size_t kMaxSettingsFile = 1024 * 1024;
constexpr size_t kMaxEntries = 5000;
constexpr size_t kMaxEntryLength = 256;

void normalize_entries(std::vector<std::wstring>* entries) {
  std::vector<std::wstring> clean;
  clean.reserve(std::min(entries->size(), kMaxEntries));
  for (const auto& raw : *entries) {
    if (clean.size() >= kMaxEntries) break;
    std::wstring value = trim(raw, L" \t\r\n");
    if (value.empty()) continue;
    if (value.size() > kMaxEntryLength) value.resize(kMaxEntryLength);
    if (std::find(clean.begin(), clean.end(), value) != clean.end()) continue;
    clean.push_back(std::move(value));
  }
  *entries = std::move(clean);
}

}  // namespace

std::vector<std::wstring> Settings::default_excluded_apps() {
  return {
      L"WindowsTerminal.exe", L"conhost.exe",       L"cmd.exe",
      L"powershell.exe",      L"pwsh.exe",          L"Code.exe",
      L"devenv.exe",          L"idea64.exe",        L"1Password.exe",
      L"KeePassXC.exe",       L"Bitwarden.exe",
  };
}

Settings normalize_settings(Settings settings) {
  normalize_entries(&settings.exceptions);
  normalize_entries(&settings.excluded_apps);
  settings.double_shift_ms = std::clamp(settings.double_shift_ms, 200, 800);
  return settings;
}

std::filesystem::path settings_directory() {  wchar_t buffer[MAX_PATH * 2] = {};
  const DWORD length = GetEnvironmentVariableW(L"APPDATA", buffer,
                                               static_cast<DWORD>(std::size(buffer)));
  std::filesystem::path base;
  if (length > 0 && length < std::size(buffer)) {
    base = std::wstring(buffer, length);
  } else {
    base = std::filesystem::temp_directory_path();
  }
  return base / L"Lado";
}

std::filesystem::path settings_path() {
  return settings_directory() / L"settings.json";
}

Settings load_settings(const std::filesystem::path& path) {
  Settings settings;
  std::ifstream file(path, std::ios::binary | std::ios::ate);
  if (!file) return settings;
  const std::streamoff length = file.tellg();
  if (length <= 0 || static_cast<uint64_t>(length) > kMaxSettingsFile) {
    return settings;
  }
  file.seekg(0);
  std::string raw(static_cast<size_t>(length), '\0');
  if (!file.read(raw.data(), length)) return settings;

  std::wstring error;
  auto parsed = json::parse(widen(raw), &error);
  if (!parsed || !parsed->is_object()) return settings;

  if (const json::Value* value = parsed->find(L"automatic");
      value != nullptr && value->is_bool()) {
    settings.automatic = value->as_bool();
  }
  if (const json::Value* value = parsed->find(L"case_sensitive");
      value != nullptr && value->is_bool()) {
    settings.case_sensitive = value->as_bool();
  }
  if (const json::Value* value = parsed->find(L"double_shift_ms");
      value != nullptr && value->is_number()) {
    const double number = value->as_number();
    if (number >= 200.0 && number <= 800.0) {
      settings.double_shift_ms = static_cast<int>(number);
    }
  }

  auto read_list = [&](const wchar_t* key, std::vector<std::wstring>* out) {
    const json::Value* value = parsed->find(key);
    if (value == nullptr || !value->is_array()) return;
    out->clear();
    for (const auto& item : value->items()) {
      if (item.is_string()) out->push_back(item.as_string());
    }
    normalize_entries(out);
  };
  read_list(L"exceptions", &settings.exceptions);
  read_list(L"excluded_apps", &settings.excluded_apps);
  return normalize_settings(std::move(settings));
}

bool save_settings(const Settings& settings, const std::filesystem::path& path) {
  std::error_code ec;
  std::filesystem::create_directories(path.parent_path(), ec);

  json::Value root = json::Value::make_object();
  root.set(L"version", json::Value(1.0));
  root.set(L"automatic", json::Value(settings.automatic));
  root.set(L"double_shift_ms", json::Value(static_cast<double>(settings.double_shift_ms)));
  root.set(L"case_sensitive", json::Value(settings.case_sensitive));

  json::Value exceptions = json::Value::make_array();
  for (const auto& word : settings.exceptions) exceptions.push(json::Value(word));
  root.set(L"exceptions", std::move(exceptions));

  json::Value excluded = json::Value::make_array();
  for (const auto& app : settings.excluded_apps) excluded.push(json::Value(app));
  root.set(L"excluded_apps", std::move(excluded));

  const std::wstring text = json::serialize(root);
  const std::string utf8 = narrow(text);

  const std::filesystem::path temp = path.parent_path() / L"settings.tmp";
  {
    std::ofstream file(temp, std::ios::binary | std::ios::trunc);
    if (!file) return false;
    file.write(utf8.data(), static_cast<std::streamsize>(utf8.size()));
    file.flush();
    if (!file) return false;
  }
  if (!MoveFileExW(temp.c_str(), path.c_str(),
                   MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
    DeleteFileW(temp.c_str());
    return false;
  }
  return true;
}

bool process_is_excluded(const std::vector<std::wstring>& excluded,
                         std::wstring_view executable_name) {
  if (executable_name.empty()) return false;
  const std::wstring folded = casefold(executable_name);
  for (const auto& app : excluded) {
    if (casefold(app) == folded) return true;
  }
  return false;
}

}  // namespace lado
