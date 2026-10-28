"""Build a compact, attributed offline lexicon; wordfreq is a build-only tool."""
import gzip
from importlib.metadata import distribution
import json
from pathlib import Path

from wordfreq import top_n_list, zipf_frequency

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src/lado/data"
TARGET.mkdir(parents=True, exist_ok=True)
dist = distribution("wordfreq")
notice_path = ROOT / "docs/licenses/wordfreq-NOTICE.md"
notice = notice_path.read_text()
(TARGET / "NOTICE.md").write_text(
    "# Lado dictionary attribution\n\n"
    "Lado adapts wordfreq 3.1.1 into compact RU/EN lookup tables, filtered to "
    "single-script alphabetic tokens and rounded to integer hundredths of Zipf frequency. "
    "These adapted data remain CC BY-SA 4.0. Attribution and the original notices "
    "are also embedded inside frequencies.json.gz. The Lado source code is MIT.\n\n"
    "Robyn Speer (2022), wordfreq: https://github.com/rspeer/wordfreq\n"
    "DOI: https://doi.org/10.5281/zenodo.7199437\n"
    "Data license: https://creativecommons.org/licenses/by-sa/4.0/\n\n" + notice,
    encoding="utf-8")
scores = {}
for lang in ("en", "ru"):
    words = {}
    for word in top_n_list(lang, 60000):
        if not word.isalpha() or len(word) > 40:
            continue
        if lang == "en" and not all("a" <= c <= "z" for c in word):
            continue
        if lang == "ru" and not all("а" <= c <= "я" or c == "ё" for c in word):
            continue
        words[word] = round(zipf_frequency(word, lang) * 100)
    scores[lang] = words
payload = {"format": "lado-lexicon-v1", "attribution": (TARGET / "NOTICE.md").read_text(),
           "license": "CC-BY-SA-4.0", "source": "wordfreq 3.1.1", "scores": scores}
compressed = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0)
(TARGET / "frequencies.json.gz").write_bytes(compressed)
print({"words": {k: len(v) for k, v in scores.items()}, "compressed_bytes": len(compressed)})
