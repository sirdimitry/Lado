// Small string and character helpers shared by the engine and the Win32 layer.
#pragma once

#include <string>
#include <string_view>

namespace lado {

std::wstring widen(std::string_view utf8);
std::string narrow(std::wstring_view text);

// RU/EN-only character classes. Deliberately independent of the process locale:
// the engine must behave identically on every machine.
bool is_alpha(wchar_t c);
bool is_digit(wchar_t c);
bool is_upper(wchar_t c);
bool is_lower(wchar_t c);
wchar_t fold_char(wchar_t c);
wchar_t upper_char(wchar_t c);

std::wstring casefold(std::wstring_view text);
std::wstring to_upper(std::wstring_view text);

std::wstring trim_end(std::wstring_view text, std::wstring_view chars);
std::wstring trim(std::wstring_view text, std::wstring_view chars);

double now_seconds();

}  // namespace lado
