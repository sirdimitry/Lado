#include "engine.h"

#include <algorithm>
#include <cmath>
#include <cwctype>

#include "util.h"

namespace lado {
namespace {

bool all_upper(std::wstring_view letters) {
  bool saw_cased = false;
  for (wchar_t c : letters) {
    if (is_lower(c)) return false;
    if (is_upper(c)) saw_cased = true;
  }
  return saw_cased;
}

bool contains_any(std::wstring_view text, std::wstring_view chars) {
  for (wchar_t c : chars) {
    if (text.find(c) != std::wstring_view::npos) return true;
  }
  return false;
}

bool is_space(wchar_t c) {
  return c == L' ' || c == L'\t' || c == L'\n' || c == L'\r' || c == L'\v' ||
         c == L'\f';
}

}  // namespace

Detector::Detector(const Settings& settings, const Lexicon& lexicon)
    : settings_(settings), lexicon_(lexicon) {}

bool Detector::exempt(std::wstring_view word) const {
  const std::wstring clean = trim(word, kTailPunctuation);
  if (settings_.case_sensitive) {
    return std::find(settings_.exceptions.begin(), settings_.exceptions.end(),
                     clean) != settings_.exceptions.end();
  }
  const std::wstring folded = casefold(clean);
  return std::any_of(settings_.exceptions.begin(), settings_.exceptions.end(),
                     [&](const std::wstring& entry) {
                       return casefold(entry) == folded;
                     });
}

std::optional<std::wstring> Detector::correction(
    std::wstring_view word, const std::vector<std::wstring>& previous,
    std::wstring_view following) const {
  std::wstring letters;
  letters.reserve(word.size());
  for (wchar_t c : word) {
    if (is_alpha(c)) letters.push_back(c);
  }

  // ALL-CAPS includes a single uppercase letter. Manual conversion bypasses it.
  if (letters.empty() || all_upper(letters) || exempt(word) ||
      word.size() > kMaxWord || contains_any(word, L"0123456789") ||
      contains_any(word, L"@/\\:_=<>")) {
    return std::nullopt;
  }

  const std::wstring body = trim_end(word, kTailPunctuation);
  if (body.find(L'.') != std::wstring::npos ||
      word.find(L'-') != std::wstring::npos) {
    return std::nullopt;
  }

  const Lang src = language_of(letters);
  if (src == Lang::None) return std::nullopt;
  for (wchar_t c : letters) {
    const Lang letter_lang = language_of(std::wstring_view(&c, 1));
    if (letter_lang != Lang::None && letter_lang != src) return std::nullopt;
  }

  const Lang dst = src == Lang::Ru ? Lang::En : Lang::Ru;
  const double original = lexicon_.score(body, src);

  const std::wstring suffix =
      std::wstring(word.substr(body.size()));  // trailing punctuation
  std::vector<std::wstring> candidates;
  candidates.push_back(converter_.convert(word, src));
  if (!suffix.empty()) {
    candidates.push_back(
        converter_.convert(word.substr(0, word.size() - suffix.size()), src) +
        suffix);
  }

  std::wstring candidate = candidates.front();
  double best = lexicon_.score(trim_end(candidate, kTailPunctuation), dst);
  for (size_t i = 1; i < candidates.size(); ++i) {
    const double value =
        lexicon_.score(trim_end(candidates[i], kTailPunctuation), dst);
    if (value > best) {
      best = value;
      candidate = candidates[i];
    }
  }

  const std::wstring converted_word = trim_end(candidate, kTailPunctuation);
  const double score = lexicon_.score(converted_word, dst);

  std::vector<Lang> context;
  const size_t first = previous.size() > 2 ? previous.size() - 2 : 0;
  for (size_t i = first; i < previous.size(); ++i) {
    const Lang lang = language_of(previous[i]);
    if (lang != Lang::None) context.push_back(lang);
  }
  const Lang next_lang = language_of(following);

  if (letters.size() == 1) {
    // Short tokens need two agreeing neighbours, never just a guess.
    std::vector<Lang> neighbours = context;
    if (next_lang != Lang::None) neighbours.push_back(next_lang);
    if (neighbours.size() < 2) return std::nullopt;
    for (Lang lang : neighbours) {
      if (lang != dst) return std::nullopt;
    }
    static const std::vector<std::wstring> kRuAllowed = {
        L"в", L"с", L"к", L"у", L"о", L"а", L"и", L"я"};
    static const std::vector<std::wstring> kEnAllowed = {L"a", L"i"};
    const auto& allowed = dst == Lang::Ru ? kRuAllowed : kEnAllowed;
    const std::wstring folded = casefold(converted_word);
    if (std::find(allowed.begin(), allowed.end(), folded) == allowed.end()) {
      return std::nullopt;
    }
    if (score < 4.0) return std::nullopt;
    return candidate;
  }

  // Known words are intentionally protected from a switch based only on context.
  if (original >= 3.0 || score < 3.7 || score - original < 2.0) {
    return std::nullopt;
  }
  return candidate;
}

Buffer::Buffer(Detector detector, Clock clock)
    : detector_(std::move(detector)), clock_(std::move(clock)) {
  clear();
}

void Buffer::clear() {
  words_.clear();
  session_.clear();
  current_.clear();
  last_edit_.reset();
  changed_ = clock_();
  last_input_ = changed_;
  overflow_ = false;
}

void Buffer::touch() {
  if (clock_() - changed_ > kIdleSeconds) clear();
  changed_ = clock_();
  last_input_ = changed_;
}

void Buffer::feed(std::wstring_view text) {
  touch();
  last_edit_.reset();
  if (overflow_) return;
  if (current_.size() + text.size() > kMaxWord) {
    clear();
    overflow_ = true;
    return;
  }
  current_.append(text);
}

void Buffer::backspace() {
  touch();
  last_edit_.reset();
  if (!current_.empty()) {
    current_.pop_back();
  } else {
    // Editing beyond the observed word invalidates positional assumptions.
    clear();
  }
}

std::optional<Edit> Buffer::finish(std::wstring separator, bool automatic) {
  touch();
  last_edit_.reset();
  if (overflow_) {
    clear();
    return std::nullopt;
  }
  if (current_.empty()) {
    if (!words_.empty() && words_.back().second.size() < 16) {
      auto [word, sep] = words_.back();
      words_.pop_back();
      words_.emplace_back(word, sep + separator);
      if (!session_.empty()) session_.back().tail += separator;
    } else {
      clear();
    }
    return std::nullopt;
  }

  const std::wstring word = current_;
  const std::wstring before = word + separator;
  std::wstring output = word;
  std::vector<std::wstring> previous;
  previous.reserve(words_.size());
  for (const auto& [stored, sep] : words_) previous.push_back(stored);
  if (automatic) {
    if (auto fixed = detector_.correction(word, previous)) output = *fixed;
  }

  std::optional<Edit> edit;
  if (output != word) {
    edit = Edit{before, output + separator, language_of(output)};
  }

  // A just-completed next word can resolve an earlier one-letter token.
  if (automatic && !edit && !words_.empty()) {
    const std::wstring old = words_.back().first;
    const std::wstring sep = words_.back().second;
    std::vector<std::wstring> preceding;
    for (size_t i = 0; i + 1 < words_.size(); ++i) {
      preceding.push_back(words_[i].first);
    }
    if (auto fixed = detector_.correction(old, preceding, output)) {
      if (trim(old, kTailPunctuation).size() == 1) {
        words_.back().first = *fixed;
        if (!session_.empty()) session_.back().word = *fixed;
        edit = Edit{old + sep + before, *fixed + sep + before,
                    language_of(*fixed)};
      }
    }
  }

  words_.emplace_back(output, separator);
  while (words_.size() > 3) words_.pop_front();
  remember_completed(output, separator);
  current_.clear();
  last_edit_ = edit;
  return edit;
}

std::optional<Edit> Buffer::manual() {
  touch();
  if (last_edit_) {
    const Edit old = *last_edit_;
    Edit edit{old.after, old.before, language_of(old.before)};
    last_edit_ = edit;
    set_tail(edit.after);
    // A reversed edit makes the session history unreliable for a group fix.
    session_.clear();
    return edit;
  }
  if (overflow_) return std::nullopt;

  std::wstring before;
  std::wstring suffix;
  if (!current_.empty()) {
    before = current_;
  } else if (!words_.empty()) {
    before = words_.back().first;
    suffix = words_.back().second;
  } else {
    return std::nullopt;
  }

  const std::wstring after = detector_.converter().convert(before);
  if (after == before) return std::nullopt;

  Edit edit{before + suffix, after + suffix, language_of(after)};
  last_edit_ = edit;
  if (!current_.empty()) {
    current_ = after;
  } else {
    words_.back().first = after;
    if (!session_.empty()) session_.back().word = after;
  }
  return edit;
}

bool Buffer::group_available() const {
  if (session_.size() < 2) return false;
  if (!current_.empty()) return false;
  if (clock_() - last_input_ > 8.0) return false;
  if (session_chars() > 200) return false;
  for (const auto& item : session_) {
    if (item.word.empty()) return false;
    if (item.tail.find_first_of(L"\r\n") != std::wstring::npos) return false;
  }
  return true;
}

std::optional<Edit> Buffer::manual_group() {
  if (!group_available()) return std::nullopt;

  std::wstring before;
  std::wstring after;
  std::vector<std::wstring> previous;
  Lang target = Lang::None;
  bool converted_any = false;
  for (const auto& item : session_) {
    before += item.word + item.tail;
    std::wstring output = item.word;
    if (auto fixed = detector_.correction(item.word, previous)) {
      output = *fixed;
      target = language_of(output);
      converted_any = true;
    }
    after += output + item.tail;
    previous.push_back(output);
  }

  if (!converted_any || after == before) return std::nullopt;
  if (before.empty() || before.size() > 1024 || after.size() > 2048) {
    return std::nullopt;
  }
  last_edit_.reset();  // group conversion is not reversible as one edit
  return Edit{before, after, target};
}

void Buffer::remember_completed(const std::wstring& word,
                                const std::wstring& tail) {
  session_.push_back(SessionWord{word, tail});
  trim_session();
}

size_t Buffer::session_chars() const {
  size_t total = 0;
  for (const auto& item : session_) total += item.word.size() + item.tail.size();
  return total;
}

void Buffer::trim_session() {
  while (session_.size() > 1 && session_chars() > 200) {
    session_.pop_front();
  }
}

void Buffer::set_tail(std::wstring_view text) {
  std::vector<std::pair<std::wstring, std::wstring>> parts;
  size_t i = 0;
  while (i < text.size()) {
    if (is_space(text[i])) {
      ++i;
      continue;
    }
    const size_t word_start = i;
    while (i < text.size() && !is_space(text[i])) ++i;
    std::wstring word(text.substr(word_start, i - word_start));
    const size_t space_start = i;
    while (i < text.size() && is_space(text[i])) ++i;
    parts.emplace_back(std::move(word),
                       std::wstring(text.substr(space_start, i - space_start)));
  }

  if (!current_.empty()) {
    current_ = parts.empty() ? std::wstring() : parts.back().first;
  } else if (!parts.empty()) {
    words_.clear();
    const size_t first = parts.size() > 3 ? parts.size() - 3 : 0;
    for (size_t k = first; k < parts.size(); ++k) words_.push_back(parts[k]);
  }
}

DoubleShift::DoubleShift(double interval) : interval_(interval) {}

void DoubleShift::clear() {
  down_ = false;
  last_tap_.reset();
  used_ = false;
}

void DoubleShift::key_used() {
  used_ = true;
  last_tap_.reset();
}

bool DoubleShift::update(bool pressed, double now, bool other_modifiers) {
  if (other_modifiers) {
    clear();
    return false;
  }
  if (!pressed) {
    // Release only closes the physical tap. The decision is made on the next
    // press, so a slow release does not delay the gesture.
    down_ = false;
    return false;
  }
  if (down_) return false;  // already held; key repeat is not a new tap
  down_ = true;

  const bool clean = !used_ && last_tap_.has_value() &&
                     (now - *last_tap_) <= interval_;
  if (clean) {
    last_tap_.reset();
    used_ = true;  // a third press must start a new pair
    return true;
  }
  last_tap_ = now;
  used_ = false;
  return false;
}

}  // namespace lado
