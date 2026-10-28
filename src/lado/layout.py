"""Physical-key conversion, deliberately separate from language detection."""
from collections import Counter

EN = "`qwertyuiop[]asdfghjkl;'zxcvbnm,."
RU = "ёйцукенгшщзхъфывапролджэячсмитьбю"
EN_SHIFT = '~QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>'
DEFAULT_PAIRS = dict(zip(EN + EN_SHIFT, RU + RU.upper()))


def language(text: str) -> str | None:
    counts = Counter("ru" if "а" <= c.lower() <= "я" or c.lower() == "ё"
                     else "en" if "a" <= c.lower() <= "z" else None for c in text)
    if counts["ru"] == counts["en"]:
        return None
    return "ru" if counts["ru"] > counts["en"] else "en"


class LayoutConverter:
    def __init__(self, pairs: dict[str, str] | None = None):
        self.forward = pairs or DEFAULT_PAIRS
        self.reverse = {v: k for k, v in self.forward.items()}

    def convert(self, text: str, source: str | None = None) -> str:
        """Letters convert by script; ambiguous punctuation follows source."""
        source = source or language(text) or "en"
        punctuation = self.forward if source == "en" else self.reverse
        out = []
        for c in text:
            if c.isalpha():
                out.append(self.forward.get(c, self.reverse.get(c, c)))
            else:
                out.append(punctuation.get(c, c))
        return "".join(out)
