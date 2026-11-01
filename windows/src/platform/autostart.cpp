#include "autostart.h"

#include <windows.h>

#include <array>
#include <filesystem>

namespace lado {
namespace {

constexpr wchar_t kRunKey[] =
    L"Software\\Microsoft\\Windows\\CurrentVersion\\Run";
constexpr wchar_t kValueName[] = L"Lado";

}  // namespace

std::wstring current_executable_path() {
  std::array<wchar_t, 32768> buffer{};
  const DWORD length =
      GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
  if (length == 0) return {};
  return std::wstring(buffer.data(), length);
}

bool autostart_enabled() {
  HKEY key = nullptr;
  if (RegOpenKeyExW(HKEY_CURRENT_USER, kRunKey, 0, KEY_QUERY_VALUE, &key) !=
      ERROR_SUCCESS) {
    return false;
  }
  std::array<wchar_t, 2048> buffer{};
  DWORD bytes = static_cast<DWORD>(buffer.size() * sizeof(wchar_t));
  DWORD type = 0;
  const LONG status =
      RegQueryValueExW(key, kValueName, nullptr, &type,
                       reinterpret_cast<BYTE*>(buffer.data()), &bytes);
  RegCloseKey(key);
  if (status != ERROR_SUCCESS || type != REG_SZ) return false;

  const std::wstring value(buffer.data());
  const std::wstring executable = current_executable_path();
  // Compare unquoted, case-insensitively; an update in the same folder keeps
  // autostart meaningful.
  auto unquote = [](std::wstring text) {
    if (text.size() >= 2 && text.front() == L'"' && text.back() == L'"') {
      text = text.substr(1, text.size() - 2);
    }
    return text;
  };
  const std::wstring stored = unquote(value);
  if (stored.empty()) return false;
  return _wcsicmp(stored.c_str(), executable.c_str()) == 0;
}

bool set_autostart(bool enabled) {
  HKEY key = nullptr;
  const LONG open =
      RegCreateKeyExW(HKEY_CURRENT_USER, kRunKey, 0, nullptr, 0,
                      KEY_SET_VALUE | KEY_QUERY_VALUE, nullptr, &key, nullptr);
  if (open != ERROR_SUCCESS) return false;

  bool ok = true;
  if (enabled) {
    const std::wstring executable = current_executable_path();
    if (executable.empty()) {
      ok = false;
    } else {
      const std::wstring quoted = L"\"" + executable + L"\"";
      ok = RegSetValueExW(key, kValueName, 0, REG_SZ,
                          reinterpret_cast<const BYTE*>(quoted.c_str()),
                          static_cast<DWORD>((quoted.size() + 1) * sizeof(wchar_t))) ==
           ERROR_SUCCESS;
    }
  } else {
    const LONG removed = RegDeleteValueW(key, kValueName);
    ok = removed == ERROR_SUCCESS || removed == ERROR_FILE_NOT_FOUND;
  }
  RegCloseKey(key);
  return ok;
}

}  // namespace lado
