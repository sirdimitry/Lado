// Unit tests for the platform-independent core. Run with ctest or directly.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <optional>
#include <string>
#include <vector>

#include "engine.h"
#include "json.h"
#include "layout.h"
#include "lexicon.h"
#include "settings.h"
#include "util.h"

namespace {

int g_checks = 0;
int g_failures = 0;

void report_failure(const char* file, int line, const std::string& message) {
  ++g_failures;
  std::cerr << "FAIL " << file << ":" << line << ": " << message << "\n";
}

#define CHECK(condition)                                                     \
  do {                                                                       \
    ++g_checks;                                                              \
    if (!(condition)) report_failure(__FILE__, __LINE__, #condition);        \
  } while (false)

#define CHECK_EQ(actual, expected)                                           \
  do {                                                                       \
    ++g_checks;                                                              \
    const auto& actual_value = (actual);                                     \
    const auto& expected_value = (expected);                                 \
    if (!(actual_value == expected_value)) {                                 \
      report_failure(__FILE__, __LINE__,                                     \
                     std::string(#actual) + " != " + #expected);             \
    }                                                                        \
  } while (false)

using lado::Buffer;
using lado::Detector;
using lado::DoubleShift;
using lado::Edit;
using lado::Lang;
using lado::LayoutConverter;
using lado::Lexicon;
using lado::Settings;

std::wstring W(const char* utf8) { return lado::widen(utf8); }

// Printable form for failure messages.
std::string show(const std::optional<std::wstring>& value) {
  return value ? lado::narrow(*value) : "<none>";
}

std::optional<std::wstring> correction_of(const Detector& detector,
                                          const std::wstring& word) {
  return detector.correction(word);
}

void test_detection_common(const Detector& detector) {
  struct Case {
    const wchar_t* before;
    const wchar_t* after;  // nullptr means no correction
  } cases[] = {
      {L"ghbdtn", L"привет"},  {L"Ghbdtn", L"Привет"},
      {L"ghbdtn,", L"привет,"}, {L"руддщ", L"hello"},
      {L"спасибо", nullptr},   {L"hello", nullptr},
  };
  for (const auto& item : cases) {
    const auto actual = correction_of(detector, item.before);
    if (item.after == nullptr) {
      CHECK(!actual.has_value());
      if (actual) {
        report_failure(__FILE__, __LINE__,
                       "unexpected correction: " + show(actual));
      }
    } else {
      CHECK(actual == std::optional<std::wstring>(item.after));
      if (actual != std::optional<std::wstring>(item.after)) {
        report_failure(__FILE__, __LINE__,
                       "wrong correction: " + show(actual));
      }
    }
  }
}

void test_uppercase(const Detector& detector) {
  const std::vector<std::wstring> previous = {L"я", L"иду"};
  for (const wchar_t* word : {L"GHBDTN", L"API", L"СССР", L"D", L"В", L"GHBDTN!"}) {
    CHECK(!detector.correction(word, previous).has_value());
  }
}

void test_short_tokens(const Detector& detector) {
  CHECK(!detector.correction(L"d").has_value());
  CHECK(!detector.correction(L"d", {L"я"}).has_value());
  CHECK(detector.correction(L"d", {L"я", L"иду"}) ==
        std::optional<std::wstring>(L"в"));
  CHECK(detector.correction(L"d", {L"иду"}, L"магазин") ==
        std::optional<std::wstring>(L"в"));
  CHECK(!detector.correction(L"d", {L"hello", L"иду"}).has_value());
}

void test_sensitive_tokens(const Detector& detector) {
  for (const wchar_t* word :
       {L"user@example.com", L"github.com", L"foo_bar", L"x=1", L"abc123",
        L"foo-bar", L"https://a"}) {
    CHECK(!detector.correction(word).has_value());
  }
}

void test_lexicon_required(const Lexicon& lexicon) {
  CHECK(lexicon.loaded());
  CHECK(lexicon.size(Lang::En) > 50000);
  CHECK(lexicon.size(Lang::Ru) > 50000);
  CHECK(lexicon.score(L"привет", Lang::Ru) > 1.0);
  CHECK(lexicon.score(L"hello", Lang::En) > 1.0);
  CHECK_EQ(lexicon.score(L"hello", Lang::Ru), 0.0);
}

void test_corpus(const Detector& detector, const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary);
  if (!file) {
    report_failure(__FILE__, __LINE__, "corpus not found: " + path.string());
    return;
  }
  std::string raw((std::istreambuf_iterator<char>(file)),
                  std::istreambuf_iterator<char>());
  std::wstring error;
  auto document = lado::json::parse(lado::widen(raw), &error);
  if (!document) {
    report_failure(__FILE__, __LINE__, "corpus parse error: " + lado::narrow(error));
    return;
  }
  const auto* positive = document->find(L"positive");
  const auto* negative = document->find(L"negative");
  CHECK(positive != nullptr && positive->is_object());
  CHECK(negative != nullptr && negative->is_array());
  if (positive == nullptr || negative == nullptr) return;

  for (const auto& [word, expected] : positive->members()) {
    ++g_checks;
    const auto actual = detector.correction(word);
    if (!actual || *actual != expected.as_string()) {
      report_failure(__FILE__, __LINE__,
                     "corpus positive failed for \"" + lado::narrow(word) +
                         "\": got " + show(actual) + ", want " +
                         lado::narrow(expected.as_string()));
    }
  }
  for (const auto& word : negative->items()) {
    ++g_checks;
    const auto actual = detector.correction(word.as_string());
    if (actual) {
      report_failure(__FILE__, __LINE__,
                     "corpus negative failed for \"" +
                         lado::narrow(word.as_string()) + "\": got " + show(actual));
    }
  }
}

class Fixture {
 public:
  Fixture() : lexicon_loaded_(lexicon_.load(lexicon_path())) {}

  bool ready() const { return lexicon_loaded_; }
  Lexicon& lexicon() { return lexicon_; }
  Settings& settings() { return settings_; }
  Detector detector() { return Detector(settings_, lexicon_); }
  Buffer buffer(Detector detector, Buffer::Clock clock = lado::now_seconds) {
    return Buffer(std::move(detector), std::move(clock));
  }

  static std::filesystem::path lexicon_path() {
#ifdef LADO_LEXICON_PATH
    return std::filesystem::path(LADO_LEXICON_PATH);
#else
    return std::filesystem::path(L"data/lexicon.bin");
#endif
  }

 private:
  Lexicon lexicon_;
  Settings settings_;
  bool lexicon_loaded_ = false;
};

void test_conversion() {
  LayoutConverter converter;
  CHECK_EQ(converter.convert(W("Ghbdtn\nVbh")), W("Привет\nМир"));
  CHECK_EQ(converter.convert(W("GHBDTN")), W("ПРИВЕТ"));
  CHECK_EQ(converter.convert(W("ghbdtn привет")), W("привет ghbdtn"));
  CHECK_EQ(converter.convert(W("123 😀\n")), W("123 😀\n"));
  CHECK_EQ(converter.convert(W(";['"), Lang::En), W("жхэ"));
  CHECK_EQ(converter.convert(W(":\"{"), Lang::En), W("ЖЭХ"));
}

void test_language() {
  CHECK(lado::language_of(W("Привет!")) == Lang::Ru);
  CHECK(lado::language_of(W("hello")) == Lang::En);
  CHECK(lado::language_of(W("123")) == Lang::None);
}

void test_buffer(Fixture& fixture) {
  Settings settings;
  Buffer buffer(fixture.buffer(Detector(settings, fixture.lexicon())));
  auto type_word = [&](const std::wstring& word) {
    buffer.feed(word);
    return buffer.finish(L" ");
  };

  auto edit = type_word(L"ghbdtn");
  CHECK(edit.has_value());
  if (edit) {
    CHECK_EQ(edit->before, W("ghbdtn "));
    CHECK_EQ(edit->after, W("привет "));
  }
  auto reversed = buffer.manual();
  CHECK(reversed.has_value());
  if (reversed) CHECK_EQ(reversed->after, W("ghbdtn "));
  auto reversed_again = buffer.manual();
  CHECK(reversed_again.has_value());
  if (reversed_again) CHECK_EQ(reversed_again->after, W("привет "));
}

void test_manual_ignores_exceptions(Fixture& fixture) {
  Settings settings;
  settings.exceptions = {L"ghbdtn"};
  Buffer buffer(fixture.buffer(Detector(settings, fixture.lexicon())));
  buffer.feed(L"ghbdtn");
  CHECK(!buffer.finish(L" ").has_value());
  auto edit = buffer.manual();
  CHECK(edit.has_value());
  if (edit) CHECK_EQ(edit->after, W("привет "));
}

void test_one_letter_manual(Fixture& fixture) {
  Settings settings;
  Buffer buffer(fixture.buffer(Detector(settings, fixture.lexicon())));
  buffer.feed(L"d");
  auto edit = buffer.manual();
  CHECK(edit.has_value());
  if (edit) CHECK_EQ(edit->after, W("в"));
  auto again = buffer.manual();
  CHECK(again.has_value());
  if (again) CHECK_EQ(again->after, W("d"));
}

void test_following_word(Fixture& fixture) {
  Settings settings;
  Buffer buffer(fixture.buffer(Detector(settings, fixture.lexicon())));
  auto type_word = [&](const std::wstring& word) {
    buffer.feed(word);
    return buffer.finish(L" ");
  };
  CHECK(!type_word(L"иду").has_value());
  CHECK(!type_word(L"d").has_value());
  auto edit = type_word(L"магазин");
  CHECK(edit.has_value());
  if (edit) {
    CHECK_EQ(edit->before, W("d магазин "));
    CHECK_EQ(edit->after, W("в магазин "));
  }
  auto reversed = buffer.manual();
  CHECK(reversed.has_value());
  if (reversed) CHECK_EQ(reversed->after, W("d магазин "));
}

void test_previous_two_words(Fixture& fixture) {
  Settings settings;
  Buffer buffer(fixture.buffer(Detector(settings, fixture.lexicon())));
  for (const wchar_t* word : {L"я", L"иду"}) {
    buffer.feed(word);
    buffer.finish(L" ");
  }
  buffer.feed(L"d");
  auto edit = buffer.finish(L" ");
  CHECK(edit.has_value());
  if (edit) CHECK_EQ(edit->after, W("в "));
}

void test_bounded_history(Fixture& fixture) {
  Settings settings;
  Buffer buffer(fixture.buffer(Detector(settings, fixture.lexicon())));
  for (int i = 0; i < 100; ++i) {
    buffer.feed(L"hello");
    buffer.finish(L" ", false);
  }
  CHECK_EQ(buffer.words().size(), static_cast<size_t>(3));
  buffer.feed(std::wstring(lado::kMaxWord + 1, L'x'));
  CHECK(buffer.current().empty());
  CHECK(!buffer.manual().has_value());
  buffer.finish(L" ");
  CHECK(!buffer.overflow());
}

void test_idle_clear(Fixture& fixture) {
  double now = 0.0;
  Settings settings;
  Buffer buffer(
      fixture.buffer(Detector(settings, fixture.lexicon()), [&] { return now; }));
  buffer.feed(L"ghbdtn");
  now = 31.0;
  CHECK(!buffer.manual().has_value());
}

void test_clear_removes_undo(Fixture& fixture) {
  Settings settings;
  Buffer buffer(fixture.buffer(Detector(settings, fixture.lexicon())));
  buffer.feed(L"ghbdtn");
  CHECK(buffer.manual().has_value());
  buffer.clear();
  CHECK(!buffer.last_edit().has_value());
  CHECK(!buffer.manual().has_value());
}

void test_backspace(Fixture& fixture) {
  Settings settings;
  Buffer buffer(fixture.buffer(Detector(settings, fixture.lexicon())));
  buffer.feed(L"ghbdtna");
  buffer.backspace();
  auto edit = buffer.manual();
  CHECK(edit.has_value());
  if (edit) CHECK_EQ(edit->after, W("привет"));
  buffer.clear();
  buffer.feed(L"hello");
  buffer.finish(L" ");
  buffer.backspace();
  CHECK(!buffer.manual().has_value());
}

void test_group_conversion(Fixture& fixture) {
  Settings settings;
  settings.automatic = false;
  double now = 0.0;
  Buffer buffer(
      fixture.buffer(Detector(settings, fixture.lexicon()), [&] { return now; }));

  auto type_word = [&](const std::wstring& word) {
    buffer.feed(word);
    return buffer.finish(L" ", false);
  };

  CHECK(!type_word(L"ghbdtn").has_value());
  CHECK(!buffer.group_available());  // one word is not a group
  CHECK(!type_word(L"vbh").has_value());
  CHECK(buffer.group_available());

  auto edit = buffer.manual_group();
  CHECK(edit.has_value());
  if (edit) {
    CHECK_EQ(edit->before, W("ghbdtn vbh "));
    CHECK_EQ(edit->after, W("привет мир "));
    CHECK(edit->target == Lang::Ru);
  }

  now = 9.0;  // past the 8 second session window
  CHECK(!buffer.group_available());

  // Valid words inside the group are preserved.
  Buffer mixed(fixture.buffer(Detector(settings, fixture.lexicon())));
  mixed.feed(L"hello");
  mixed.finish(L" ", false);
  mixed.feed(L"ghbdtn");
  mixed.finish(L" ", false);
  auto mixed_edit = mixed.manual_group();
  CHECK(mixed_edit.has_value());
  if (mixed_edit) {
    CHECK_EQ(mixed_edit->before, W("hello ghbdtn "));
    CHECK_EQ(mixed_edit->after, W("hello привет "));
  }
}

void test_enter_boundary(Fixture& fixture) {
  Settings settings;
  Buffer buffer(fixture.buffer(Detector(settings, fixture.lexicon())));
  buffer.feed(L"ghbdtn");
  auto edit = buffer.finish(L"\n", true);
  CHECK(edit.has_value());
  if (edit) {
    CHECK_EQ(edit->before, W("ghbdtn\n"));
    CHECK_EQ(edit->after, W("привет\n"));
    CHECK(edit->target == Lang::Ru);
  }
}

void test_gesture() {  DoubleShift gesture;
  CHECK(!gesture.update(true, 0.0));
  CHECK(!gesture.update(false, 0.05));
  CHECK(gesture.update(true, 0.15));
  CHECK(!gesture.update(false, 0.2));
  CHECK(!gesture.update(true, 0.25));

  DoubleShift used;
  used.update(true, 0.0);
  used.key_used();
  CHECK(!used.update(false, 0.1));
  CHECK(!used.update(true, 0.2));
  CHECK(!used.update(false, 0.3));

  DoubleShift interrupted;
  interrupted.update(true, 0.0);
  interrupted.update(false, 0.05);
  interrupted.key_used();
  CHECK(!interrupted.update(true, 0.1));
  CHECK(!interrupted.update(false, 0.15));
  CHECK(interrupted.update(true, 0.2));

  DoubleShift slow;
  slow.update(true, 0.0);
  CHECK(!slow.update(false, 1.0));
  CHECK(!slow.update(true, 1.1));
  CHECK(!slow.update(false, 1.2, true));
  slow.update(true, 1.3);
  CHECK(!slow.update(false, 1.4));
}

void test_json() {
  std::wstring error;
  auto value = lado::json::parse(W(R"({"a": 1, "b": [true, null, "x\u0451"], "c": {"d": -2.5}})"),
                                 &error);
  CHECK(value.has_value());
  if (!value) {
    report_failure(__FILE__, __LINE__, "json parse: " + lado::narrow(error));
    return;
  }
  const auto* a = value->find(L"a");
  CHECK(a != nullptr && a->is_number() && a->as_number() == 1.0);
  const auto* b = value->find(L"b");
  CHECK(b != nullptr && b->is_array() && b->items().size() == 3);
  if (b != nullptr && b->items().size() == 3) {
    CHECK(b->items()[2].as_string() == W("xё"));
  }
  const auto* c = value->find(L"c");
  CHECK(c != nullptr && c->find(L"d") != nullptr);
  CHECK(!lado::json::parse(L"{\"a\": }", &error).has_value());
  CHECK(!lado::json::parse(L"[1] x", &error).has_value());
  CHECK(!lado::json::parse(L"\"\x01\"", &error).has_value());
  CHECK(error.size() > 0);

  std::wstring text = lado::json::serialize(*value);
  auto roundtrip = lado::json::parse(text, &error);
  CHECK(roundtrip.has_value());
  if (roundtrip) {
    CHECK(roundtrip->find(L"b") != nullptr);
    CHECK(roundtrip->find(L"b")->items()[2].as_string() == W("xё"));
  }
}

void test_settings_roundtrip() {
  const auto directory =
      std::filesystem::temp_directory_path() / L"lado-tests-settings";
  std::error_code ec;
  std::filesystem::remove_all(directory, ec);
  const auto path = directory / L"settings.json";

  Settings defaults = lado::load_settings(path);
  CHECK(defaults.automatic);
  CHECK_EQ(defaults.double_shift_ms, 400);
  CHECK(defaults.excluded_apps.size() > 5);
  CHECK(std::none_of(defaults.excluded_apps.begin(), defaults.excluded_apps.end(),
                     [](const std::wstring& value) { return value.empty(); }));

  defaults.double_shift_ms = 550;
  defaults.case_sensitive = true;
  defaults.exceptions = {L"Ghbdtn", L"  привет  ", L"Ghbdtn", L""};
  CHECK(lado::save_settings(defaults, path));

  Settings loaded = lado::load_settings(path);
  CHECK_EQ(loaded.double_shift_ms, 550);
  CHECK(loaded.case_sensitive);
  CHECK_EQ(loaded.exceptions.size(), static_cast<size_t>(2));
  if (loaded.exceptions.size() == 2) {
    CHECK_EQ(loaded.exceptions[0], W("Ghbdtn"));
    CHECK_EQ(loaded.exceptions[1], W("привет"));
  }

  // Invalid values fall back to the previous/default behavior instead of
  // producing a bad runtime interval.
  {
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    file << "{\"double_shift_ms\": 5000, \"automatic\": \"yes\"}";
  }
  Settings clamped = lado::load_settings(path);
  CHECK(clamped.automatic);
  CHECK_EQ(clamped.double_shift_ms, 400);

  std::filesystem::remove_all(directory, ec);
}

void test_exclusions() {
  const std::vector<std::wstring> excluded = {L"Code.exe", L"1Password.exe"};
  CHECK(lado::process_is_excluded(excluded, L"code.exe"));
  CHECK(lado::process_is_excluded(excluded, L"1PASSWORD.EXE"));
  CHECK(!lado::process_is_excluded(excluded, L"notepad.exe"));
}

}  // namespace

int main(int argc, char** argv) {
  Fixture fixture;
  if (!fixture.ready()) {
    std::cerr << "FATAL: cannot load lexicon at "
              << fixture.lexicon_path().string() << "\n";
    return 2;
  }

  Detector detector(fixture.detector());
  test_detection_common(detector);
  test_uppercase(detector);
  test_short_tokens(detector);
  test_sensitive_tokens(detector);
  test_lexicon_required(fixture.lexicon());
  test_conversion();
  test_language();

  {
    Settings settings;
    settings.exceptions = {L"Ghbdtn"};
    Detector exempt(settings, fixture.lexicon());
    CHECK(!exempt.correction(L"ghbdtn").has_value());
    settings.case_sensitive = true;
    Detector sensitive(settings, fixture.lexicon());
    CHECK(sensitive.correction(L"ghbdtn") ==
          std::optional<std::wstring>(L"привет"));
    CHECK(!sensitive.correction(L"Ghbdtn").has_value());
  }

  test_buffer(fixture);
  test_manual_ignores_exceptions(fixture);
  test_one_letter_manual(fixture);
  test_following_word(fixture);
  test_previous_two_words(fixture);
  test_bounded_history(fixture);
  test_idle_clear(fixture);
  test_clear_removes_undo(fixture);
  test_backspace(fixture);
  test_group_conversion(fixture);
  test_enter_boundary(fixture);
  test_gesture();
  test_json();
  test_settings_roundtrip();
  test_exclusions();

  std::filesystem::path corpus;
  if (argc > 1) {
    corpus = lado::widen(argv[1]);
  } else {
#ifdef LADO_CORPUS_PATH
    corpus = std::filesystem::path(LADO_CORPUS_PATH);
#else
    corpus = std::filesystem::path(L"../tests/corpus.json");
#endif
  }
  test_corpus(detector, corpus);

  std::cout << (g_failures == 0 ? "PASS" : "FAIL") << ": " << g_checks
            << " checks, " << g_failures << " failures\n";
  return g_failures == 0 ? 0 : 1;
}
