import unittest
import json
from pathlib import Path

from lado.engine import Buffer, Detector, DoubleShift, Lexicon, MAX_WORD
from lado.layout import LayoutConverter, language
from lado.settings import Settings


class DetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lexicon = Lexicon()

    def setUp(self):
        self.settings = Settings()
        self.detector = Detector(self.settings, self.lexicon)

    def test_common_wrong_layout(self):
        for before, after in (("ghbdtn", "привет"), ("Ghbdtn", "Привет"),
                              ("ghbdtn,", "привет,"), ("руддщ", "hello"),
                              ("спасибо", None), ("hello", None)):
            with self.subTest(before=before):
                self.assertEqual(self.detector.correction(before), after)

    def test_uppercase_never_automatic(self):
        for word in ("GHBDTN", "API", "СССР", "D", "В", "GHBDTN!"):
            self.assertIsNone(self.detector.correction(word, ("я", "иду")))

    def test_short_tokens_need_agreeing_context(self):
        self.assertIsNone(self.detector.correction("d"))
        self.assertIsNone(self.detector.correction("d", ("я",)))
        self.assertEqual(self.detector.correction("d", ("я", "иду")), "в")
        self.assertEqual(self.detector.correction("d", ("иду",), "магазин"), "в")
        self.assertIsNone(self.detector.correction("d", ("hello", "иду")))

    def test_sensitive_looking_tokens(self):
        for word in ("user@example.com", "github.com", "foo_bar", "x=1", "abc123", "foo-bar", "https://a"):
            self.assertIsNone(self.detector.correction(word))

    def test_explicit_exceptions(self):
        self.settings.exceptions = ["Ghbdtn"]
        self.assertIsNone(self.detector.correction("ghbdtn"))
        self.settings.case_sensitive = True
        self.assertEqual(self.detector.correction("ghbdtn"), "привет")
        self.assertIsNone(self.detector.correction("Ghbdtn"))

    def test_mixed_words_not_auto(self):
        self.assertIsNone(self.detector.correction("helloпривет"))

    def test_synthetic_regression_corpus(self):
        corpus = json.loads((Path(__file__).parent / "corpus.json").read_text())
        for before, after in corpus["positive"].items():
            with self.subTest(before=before):
                self.assertEqual(self.detector.correction(before), after)
        for word in corpus["negative"]:
            with self.subTest(untouched=word):
                self.assertIsNone(self.detector.correction(word))


class ConversionTests(unittest.TestCase):
    def test_case_and_multiline(self):
        c = LayoutConverter()
        self.assertEqual(c.convert("Ghbdtn\nVbh"), "Привет\nМир")
        self.assertEqual(c.convert("GHBDTN"), "ПРИВЕТ")
        self.assertEqual(c.convert("ghbdtn привет"), "привет ghbdtn")
        self.assertEqual(c.convert("123 😀\n"), "123 😀\n")
        self.assertEqual(c.convert(";['", "en"), "жхэ")
        self.assertEqual(c.convert(':\"{', "en"), "ЖЭХ")

    def test_language(self):
        self.assertEqual(language("Привет!"), "ru")
        self.assertEqual(language("hello"), "en")
        self.assertIsNone(language("123"))


class BufferTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()
        self.buffer = Buffer(Detector(self.settings))

    def type_word(self, word, automatic=True):
        self.buffer.feed(word)
        return self.buffer.finish(" ", automatic)

    def test_automatic_and_double_shift_reversal(self):
        edit = self.type_word("ghbdtn")
        self.assertEqual((edit.before, edit.after), ("ghbdtn ", "привет "))
        self.assertEqual(self.buffer.manual().after, "ghbdtn ")
        self.assertEqual(self.buffer.manual().after, "привет ")

    def test_manual_ignores_exceptions(self):
        self.settings.exceptions = ["ghbdtn"]
        self.assertIsNone(self.type_word("ghbdtn"))
        self.assertEqual(self.buffer.manual().after, "привет ")

    def test_one_letter_manual(self):
        self.buffer.feed("d")
        self.assertEqual(self.buffer.manual().after, "в")
        self.assertEqual(self.buffer.manual().after, "d")

    def test_following_word_resolves_preposition(self):
        self.type_word("иду")
        self.assertIsNone(self.type_word("d"))
        edit = self.type_word("магазин")
        self.assertEqual((edit.before, edit.after), ("d магазин ", "в магазин "))
        self.assertEqual(self.buffer.manual().after, "d магазин ")

    def test_previous_two_words(self):
        self.type_word("я")
        self.type_word("иду")
        self.assertEqual(self.type_word("d").after, "в ")

    def test_no_unbounded_history(self):
        for _ in range(100):
            self.type_word("hello", False)
        self.assertEqual(len(self.buffer.words), 3)
        self.buffer.feed("x" * (MAX_WORD + 1))
        self.assertEqual(self.buffer.current, "")
        self.assertIsNone(self.buffer.manual())
        self.buffer.finish(" ")
        self.assertFalse(self.buffer.overflow)

    def test_idle_clear(self):
        now = [0]
        b = Buffer(Detector(self.settings), clock=lambda: now[0])
        b.feed("ghbdtn")
        now[0] = 31
        self.assertIsNone(b.manual())

    def test_clear_removes_undo(self):
        self.buffer.feed("ghbdtn")
        self.buffer.manual()
        self.buffer.clear()
        self.assertIsNone(self.buffer.last_edit)
        self.assertIsNone(self.buffer.manual())

    def test_backspace(self):
        self.buffer.feed("ghbdtna")
        self.buffer.backspace()
        self.assertEqual(self.buffer.manual().after, "привет")
        self.buffer.clear()
        self.type_word("hello")
        self.buffer.backspace()
        self.assertIsNone(self.buffer.manual())


class GestureTests(unittest.TestCase):
    def test_two_clean_taps(self):
        g = DoubleShift()
        self.assertFalse(g.update(True, 0))
        self.assertFalse(g.update(False, .05))
        self.assertFalse(g.update(True, .15))
        self.assertTrue(g.update(False, .2))

    def test_shift_for_uppercase_not_gesture(self):
        g = DoubleShift()
        g.update(True, 0)
        g.key_used()
        self.assertFalse(g.update(False, .1))
        g.update(True, .2)
        self.assertFalse(g.update(False, .3))

    def test_long_hold_and_modifiers(self):
        g = DoubleShift()
        g.update(True, 0)
        self.assertFalse(g.update(False, 1))
        g.update(True, 1.1)
        self.assertFalse(g.update(False, 1.2, True))
        g.update(True, 1.3)
        self.assertFalse(g.update(False, 1.4))


if __name__ == "__main__":
    unittest.main()
