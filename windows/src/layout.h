// Physical-key conversion, deliberately separate from language detection.
#pragma once

#include <string>
#include <string_view>
#include <unordered_map>

namespace lado {

enum class Lang { None, En, Ru };

// Majority script of the RU/EN letters in the text; ties are ambiguous (None).
Lang language_of(std::wstring_view text);

class LayoutConverter {
 public:
  LayoutConverter();

  // Letters convert by script; ambiguous punctuation follows the source
  // language. An unknown source falls back to detection, then English.
  std::wstring convert(std::wstring_view text,
                       Lang source = Lang::None) const;

 private:
  std::unordered_map<wchar_t, wchar_t> forward_;
  std::unordered_map<wchar_t, wchar_t> reverse_;
};

}  // namespace lado
