#include "log.h"

#include <windows.h>

#include <cstdarg>
#include <cstdio>
#include <ctime>
#include <iterator>
#include <mutex>
#include <string>

namespace lado {
namespace {

constexpr uint64_t kMaxLogBytes = 256 * 1024;

std::mutex g_log_mutex;

std::filesystem::path local_app_data() {
  wchar_t buffer[MAX_PATH * 2] = {};
  const DWORD length = GetEnvironmentVariableW(L"LOCALAPPDATA", buffer,
                                               static_cast<DWORD>(std::size(buffer)));
  if (length > 0 && length < std::size(buffer)) {
    return std::filesystem::path(std::wstring(buffer, length));
  }
  return std::filesystem::temp_directory_path();
}

}  // namespace

std::filesystem::path log_path() {
  return local_app_data() / L"Lado" / L"lado.log";
}

void log_message(const wchar_t* format, ...) {
  std::lock_guard<std::mutex> guard(g_log_mutex);
  const std::filesystem::path path = log_path();
  std::error_code ec;
  std::filesystem::create_directories(path.parent_path(), ec);

  if (std::filesystem::exists(path, ec)) {
    const auto size = std::filesystem::file_size(path, ec);
    if (!ec && size > kMaxLogBytes) {
      std::filesystem::remove(path, ec);
    }
  }

  wchar_t message[1024] = {};
  va_list args;
  va_start(args, format);
  _vsnwprintf(message, std::size(message), format, args);
  va_end(args);
  message[std::size(message) - 1] = L'\0';

  SYSTEMTIME now = {};
  GetLocalTime(&now);
  wchar_t line[1200] = {};
  _snwprintf(line, std::size(line),
             L"%04u-%02u-%02u %02u:%02u:%02u %s\r\n", now.wYear, now.wMonth,
             now.wDay, now.wHour, now.wMinute, now.wSecond, message);
  line[std::size(line) - 1] = L'\0';

  HANDLE file = CreateFileW(path.c_str(), FILE_APPEND_DATA,
                            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                            OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file == INVALID_HANDLE_VALUE) return;
  DWORD written = 0;
  const DWORD bytes = static_cast<DWORD>(wcslen(line) * sizeof(wchar_t));
  WriteFile(file, line, bytes, &written, nullptr);
  CloseHandle(file);
}

}  // namespace lado
