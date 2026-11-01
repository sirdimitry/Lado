// Bounded, offline correction. Nothing in this module writes text to disk.
// A direct port of src/lado/engine.py; the macOS and Windows apps share the
// same rules so a word is corrected the same way on both platforms.
#pragma once

#include <cstddef>
#include <deque>
#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "layout.h"
#include "lexicon.h"
#include "settings.h"

namespace lado {

constexpr size_t kMaxWord = 128;
constexpr size_t kMaxSelection = 65536;
constexpr double kIdleSeconds = 30.0;
inline constexpr std::wstring_view kTailPunctuation = L".,!?;:";

struct Edit {
  std::wstring before;  // text currently at the caret, including separator
  std::wstring after;   // replacement, including separator
  Lang target = Lang::None;
};

class Detector {
 public:
  Detector(const Settings& settings, const Lexicon& lexicon);

  // Returns the converted word (possibly with punctuation) when the evidence is
  // strong enough, otherwise nothing. Never touches the system.
  std::optional<std::wstring> correction(
      std::wstring_view word, const std::vector<std::wstring>& previous = {},
      std::wstring_view following = L"") const;

  const LayoutConverter& converter() const { return converter_; }

 private:
  bool exempt(std::wstring_view word) const;

  const Settings& settings_;
  const Lexicon& lexicon_;
  LayoutConverter converter_;
};

class Buffer {
 public:
  using Clock = std::function<double()>;

  Buffer(Detector detector, Clock clock);

  void clear();
  void touch();
  void feed(std::wstring_view text);
  void backspace();
  std::optional<Edit> finish(std::wstring separator, bool automatic = true);
  std::optional<Edit> manual();

  const std::wstring& current() const { return current_; }
  const std::deque<std::pair<std::wstring, std::wstring>>& words() const {
    return words_;
  }
  const std::optional<Edit>& last_edit() const { return last_edit_; }
  bool overflow() const { return overflow_; }

 private:
  void set_tail(std::wstring_view text);

  Detector detector_;
  Clock clock_;
  std::deque<std::pair<std::wstring, std::wstring>> words_;
  std::wstring current_;
  std::optional<Edit> last_edit_;
  double changed_ = 0.0;
  bool overflow_ = false;
};

// Two clean taps of Shift; fires on the second press (Keyboop-style).
class DoubleShift {
 public:
  explicit DoubleShift(double interval = 0.4);

  void set_interval(double interval) { interval_ = interval; }
  void clear();
  void key_used();
  bool update(bool pressed, double now, bool other_modifiers = false);

 private:
  double interval_;
  bool down_ = false;
  std::optional<double> last_tap_;
  bool used_ = false;
};

}  // namespace lado
