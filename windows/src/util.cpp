#include "util.h"

#include <windows.h>

#include <chrono>
#include <cwctype>

namespace lado {

std::wstring widen(std::string_view utf8) {
  if (utf8.empty()) return {};
  const int size = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8.data(),
                                       static_cast<int>(utf8.size()), nullptr, 0);
  if (size <= 0) return {};
  std::wstring out(static_cast<size_t>(size), L'\0');
  MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8.data(),
                      static_cast<int>(utf8.size()), out.data(), size);
  return out;
}

std::string narrow(std::wstring_view text) {
  if (text.empty()) return {};
  const int size = WideCharToMultiByte(CP_UTF8, 0, text.data(),
                                       static_cast<int>(text.size()), nullptr, 0,
                                       nullptr, nullptr);
  if (size <= 0) return {};
  std::string out(static_cast<size_t>(size), '\0');
  WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()),
                      out.data(), size, nullptr, nullptr);
  return out;
}

bool is_alpha(wchar_t c) {
  return (c >= L'a' && c <= L'z') || (c >= L'A' && c <= L'Z') ||
         (c >= 0x0430 && c <= 0x044F) || (c >= 0x0410 && c <= 0x042F) ||
         c == 0x0451 || c == 0x0401;
}

bool is_digit(wchar_t c) { return c >= L'0' && c <= L'9'; }

bool is_upper(wchar_t c) {
  return (c >= L'A' && c <= L'Z') || (c >= 0x0410 && c <= 0x042F) || c == 0x0401;
}

bool is_lower(wchar_t c) {
  return (c >= L'a' && c <= L'z') || (c >= 0x0430 && c <= 0x044F) || c == 0x0451;
}

wchar_t fold_char(wchar_t c) {
  if (c >= L'A' && c <= L'Z') return static_cast<wchar_t>(c + 0x20);
  if (c >= 0x0410 && c <= 0x042F) return static_cast<wchar_t>(c + 0x20);
  if (c == 0x0401) return 0x0451;
  return c;
}

wchar_t upper_char(wchar_t c) {
  if (c >= L'a' && c <= L'z') return static_cast<wchar_t>(c - 0x20);
  if (c >= 0x0430 && c <= 0x044F) return static_cast<wchar_t>(c - 0x20);
  if (c == 0x0451) return 0x0401;
  return c;
}

std::wstring casefold(std::wstring_view text) {
  std::wstring out(text);
  for (wchar_t& c : out) c = fold_char(c);
  return out;
}

std::wstring to_upper(std::wstring_view text) {
  std::wstring out(text);
  for (wchar_t& c : out) c = upper_char(c);
  return out;
}

std::wstring trim_end(std::wstring_view text, std::wstring_view chars) {
  size_t end = text.size();
  while (end > 0 && chars.find(text[end - 1]) != std::wstring_view::npos) --end;
  return std::wstring(text.substr(0, end));
}

std::wstring trim(std::wstring_view text, std::wstring_view chars) {
  size_t begin = 0;
  size_t end = text.size();
  while (begin < end && chars.find(text[begin]) != std::wstring_view::npos) ++begin;
  while (end > begin && chars.find(text[end - 1]) != std::wstring_view::npos) --end;
  return std::wstring(text.substr(begin, end - begin));
}

double now_seconds() {
  using clock = std::chrono::steady_clock;
  static const clock::time_point origin = clock::now();
  return std::chrono::duration<double>(clock::now() - origin).count();
}

}  // namespace lado
