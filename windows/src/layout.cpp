#include "layout.h"

#include "util.h"

namespace lado {
namespace {

// The same table the macOS engine uses: one physical key, one pair of symbols.
// Kept as character pairs so the correction is testable without a keyboard.
constexpr wchar_t kEn[] = L"`qwertyuiop[]asdfghjkl;'zxcvbnm,.";
constexpr wchar_t kRu[] = L"ёйцукенгшщзхъфывапролджэячсмитьбю";
constexpr wchar_t kEnShift[] = L"~QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>";
constexpr size_t kKeyCount = 33;

wchar_t upper(wchar_t c) { return upper_char(c); }

}  // namespace

Lang language_of(std::wstring_view text) {
  int ru = 0;
  int en = 0;
  for (wchar_t c : text) {
    const wchar_t lower = fold_char(c);
    if ((lower >= 0x0430 && lower <= 0x044F) || lower == 0x0451) {
      ++ru;
    } else if (lower >= L'a' && lower <= L'z') {
      ++en;
    }
  }
  if (ru == en) return Lang::None;
  return ru > en ? Lang::Ru : Lang::En;
}

LayoutConverter::LayoutConverter() {
  for (size_t i = 0; i < kKeyCount; ++i) {
    forward_[kEn[i]] = kRu[i];
    forward_[kEnShift[i]] = upper(kRu[i]);
  }
  for (const auto& [from, to] : forward_) reverse_[to] = from;
}

std::wstring LayoutConverter::convert(std::wstring_view text,
                                      Lang source) const {
  if (source == Lang::None) source = language_of(text);
  if (source == Lang::None) source = Lang::En;

  const auto& punctuation = source == Lang::En ? forward_ : reverse_;
  std::wstring out;
  out.reserve(text.size());
  for (wchar_t c : text) {
    if (is_alpha(c)) {
      auto direct = forward_.find(c);
      if (direct != forward_.end()) {
        out.push_back(direct->second);
        continue;
      }
      auto back = reverse_.find(c);
      out.push_back(back != reverse_.end() ? back->second : c);
    } else {
      auto found = punctuation.find(c);
      out.push_back(found != punctuation.end() ? found->second : c);
    }
  }
  return out;
}

}  // namespace lado
