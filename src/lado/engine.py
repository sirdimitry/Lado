"""Bounded, offline correction. Nothing in this module writes text to disk."""
from collections import deque
from dataclasses import dataclass
import gzip
from importlib.resources import files
import json
import re
from time import monotonic

from .layout import LayoutConverter, language
from .settings import Settings

MAX_WORD = 128
MAX_SELECTION = 65536
IDLE_SECONDS = 30
TAIL_PUNCTUATION = ".,!?;:"


class Lexicon:
    def __init__(self, scores=None):
        if scores is None:
            data = files("lado").joinpath("data/frequencies.json.gz").read_bytes()
            scores = json.loads(gzip.decompress(data))["scores"]
        self.scores = scores

    def score(self, word: str, lang: str | None) -> float:
        return self.scores.get(lang, {}).get(word.casefold(), 0) / 100


@dataclass
class Edit:
    before: str
    after: str
    target: str | None


class Detector:
    def __init__(self, settings: Settings, lexicon=None, converter=None):
        self.settings = settings
        self.lexicon = lexicon or Lexicon()
        self.converter = converter or LayoutConverter()

    def exempt(self, word: str) -> bool:
        clean = word.strip(TAIL_PUNCTUATION)
        if self.settings.case_sensitive:
            return clean in self.settings.exceptions
        return clean.casefold() in {x.casefold() for x in self.settings.exceptions}

    def correction(self, word: str, previous=(), following: str = "") -> str | None:
        letters = "".join(c for c in word if c.isalpha())
        # ALL-CAPS includes a single uppercase letter. Manual conversion bypasses this.
        if (not letters or letters.isupper() or self.exempt(word) or len(word) > MAX_WORD
                or any(c.isdigit() for c in word) or any(c in word for c in "@/\\:_=<>")):
            return None
        if "." in word.rstrip(TAIL_PUNCTUATION) or "-" in word:
            return None
        src = language(letters)
        if src is None or any(language(c) not in (None, src) for c in letters):
            return None
        dst = "ru" if src == "en" else "en"
        original = self.lexicon.score(word.rstrip(TAIL_PUNCTUATION), src)
        suffix = word[len(word.rstrip(TAIL_PUNCTUATION)):]
        candidates = [self.converter.convert(word, src)]
        if suffix:
            candidates.append(self.converter.convert(word[:-len(suffix)], src) + suffix)
        candidate = max(candidates, key=lambda x: self.lexicon.score(x.rstrip(TAIL_PUNCTUATION), dst))
        converted_word = candidate.rstrip(TAIL_PUNCTUATION)
        score = self.lexicon.score(converted_word, dst)
        context = [language(x) for x in list(previous)[-2:]]
        context = [x for x in context if x]
        next_lang = language(following)
        if len(letters) == 1:
            # Short tokens need two agreeing neighbours, never just a guess.
            neighbours = context + ([next_lang] if next_lang else [])
            if len(neighbours) < 2 or any(x != dst for x in neighbours):
                return None
            if converted_word.casefold() not in ({"в", "с", "к", "у", "о", "а", "и", "я"}
                                                if dst == "ru" else {"a", "i"}):
                return None
            return candidate if score >= 4.0 else None
        # Known words are intentionally protected from a switch based only on context.
        if original >= 3.0 or score < 3.7 or score - original < 2.0:
            return None
        return candidate


class Buffer:
    """At most three completed words and one current word, cleared on idle/focus."""
    def __init__(self, detector: Detector, clock=monotonic):
        self.detector = detector
        self.clock = clock
        self.clear()

    def clear(self):
        self.words = deque(maxlen=3)  # (word, following separator)
        self.current = ""
        self.last_edit = None
        self.changed = self.clock()
        self.overflow = False

    def touch(self):
        if self.clock() - self.changed > IDLE_SECONDS:
            self.clear()
        self.changed = self.clock()

    def feed(self, text: str):
        self.touch()
        self.last_edit = None
        if self.overflow:
            return
        if len(self.current) + len(text) > MAX_WORD:
            self.clear()
            self.overflow = True
            return
        self.current += text

    def backspace(self):
        self.touch()
        self.last_edit = None
        if self.current:
            self.current = self.current[:-1]
        else:
            # Editing beyond the observed word invalidates positional assumptions.
            self.clear()

    def finish(self, separator: str, automatic=True) -> Edit | None:
        self.touch()
        self.last_edit = None
        if self.overflow:
            self.clear()
            return None
        if not self.current:
            if self.words and len(self.words[-1][1]) < 16:
                word, sep = self.words.pop()
                self.words.append((word, sep + separator))
            else:
                self.clear()
            return None
        word = self.current
        before = word + separator
        output = word
        previous = [x[0] for x in self.words]
        if automatic:
            output = self.detector.correction(word, previous) or word
        edit = Edit(before, output + separator, language(output)) if output != word else None
        # A just-completed next word can resolve an earlier one-letter token.
        if automatic and not edit and self.words:
            old, sep = self.words[-1]
            preceding = [x[0] for x in list(self.words)[:-1]]
            fix = self.detector.correction(old, preceding, output)
            if fix and len(old.strip(TAIL_PUNCTUATION)) == 1:
                self.words[-1] = (fix, sep)
                edit = Edit(old + sep + before, fix + sep + before, language(fix))
        self.words.append((output, separator))
        self.current = ""
        self.last_edit = edit
        return edit

    def manual(self) -> Edit | None:
        self.touch()
        if self.last_edit:
            old = self.last_edit
            edit = Edit(old.after, old.before, language(old.before))
            self.last_edit = edit
            self._set_tail(edit.after)
            return edit
        if self.overflow:
            return None
        if self.current:
            before, suffix = self.current, ""
        elif self.words:
            before, suffix = self.words[-1]
        else:
            return None
        after = self.detector.converter.convert(before)
        if after == before:
            return None
        edit = Edit(before + suffix, after + suffix, language(after))
        self.last_edit = edit
        if self.current:
            self.current = after
        else:
            self.words[-1] = (after, suffix)
        return edit

    def _set_tail(self, text):
        parts = re.findall(r"(\S+)(\s*)", text)
        if self.current:
            self.current = parts[-1][0] if parts else ""
        elif parts:
            # After a multiword context edit discard older positional context.
            self.words.clear()
            self.words.extend(parts[-3:])


class DoubleShift:
    """Two press/release cycles. Typing with Shift cancels the gesture."""
    def __init__(self, interval=0.4):
        self.interval = interval
        self.clear()

    def clear(self):
        self.down = None
        self.last_tap = None
        self.used = False

    def key_used(self):
        self.used = True
        self.last_tap = None

    def update(self, pressed: bool, now: float, other_modifiers=False) -> bool:
        if other_modifiers:
            self.clear()
            return False
        if pressed:
            if self.down is None:
                self.down = now
                self.used = False
            return False
        if self.down is None:
            return False
        valid = not self.used and now - self.down <= self.interval
        self.down = None
        if not valid:
            self.last_tap = None
            return False
        if self.last_tap is not None and now - self.last_tap <= self.interval:
            self.last_tap = None
            return True
        self.last_tap = now
        return False
