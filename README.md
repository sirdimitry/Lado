<p align="center"><img src="assets/brand/github-banner.png" alt="Lado — Your words stay with you" width="100%"></p>

<p align="center"><a href="README.ru.md">Русский</a> · <b>English</b> · <a href="docs/ROADMAP.md">Roadmap</a> · <a href="docs/PRIVACY.md">Privacy</a> · <a href="https://github.com/sirdimitry/Lado/releases">Downloads</a></p>

# Lado

A small macOS menu-bar companion for typing in Russian and English. Forgot the
layout? `ghbdtn` → `привет`. Press **Shift twice** to convert a word or a selection.
Built with Python and native macOS interfaces. Windows support is planned.

**Offline. No typing history. No telemetry. No accounts. No subscription.**

Lado does not transmit your typing or save it to disk. A bounded, short-lived
context exists in RAM to make corrections possible. Only your preferences and
explicitly added personal exceptions are saved. See [the exact privacy
boundaries](docs/PRIVACY.md), including password-field limitations.

## Status

**0.1.0 is an early macOS preview**, not a claim of universal editor compatibility.
The shared engine, native adapter, menu-bar UI and DMG packaging are implemented.
See [validation](docs/VALIDATION.md) for completed checks and outstanding manual
checks. No neural model is bundled in this version: it uses compact local word
frequency tables. A small local model will be evaluated separately against this
baseline, including its memory cost.

## What it does

- Shows the current working language, **RU / EN**, in the menu bar.
- Corrects confident layout mistakes at a word boundary, including short tokens
  when surrounding words support the correction.
- Skips **ALL-CAPS** words during automatic correction.
- **Double Shift:** converts selected text; otherwise converts the last observed
  word, including a one-letter word. Repeat to reverse the last operation.
- Preserves a selection where the editor supports selection control. A selected
  paragraph is processed by deterministic key mapping, never paraphrased.
- Supports explicit personal word exceptions, optional case sensitivity and app
  exclusions. Word exceptions do not prevent manual conversion.
- Lets you select one installed English/Russian layout pair. Other installed
  languages can remain enabled; Lado pauses when one is active.
- Disables processing and clears context for detected secure input, shows a dim
  lock icon, and resumes with empty context afterwards.
- Includes pause, optional start at login, settings and About with author links.

This is **keyboard-layout conversion, not translation**: `hello` → `руддщ`.
Mixed-script selections convert letters in both directions; ambiguous punctuation
follows the dominant script. A selection does not change the active layout.

## Install on macOS

1. Download the **macOS arm64 DMG** from [Releases](https://github.com/sirdimitry/Lado/releases).
2. Drag **Lado.app** to **Applications**, then launch that copy.
3. Allow **Lado** in **System Settings → Privacy & Security → Accessibility**.
   macOS may additionally request **Input Monitoring**. Permissions belong to the
   installed app; source-code runs have a different identity.
4. Enable an English and a Russian keyboard layout in macOS, then choose your
   working pair in Lado Settings.

The preview DMG is **ad-hoc signed, not Apple-notarized**. macOS may require you to
approve opening it in Privacy & Security. No administrator/root access is needed
for normal use. Intel builds and Windows installers are not provided yet.

Default exclusions include Terminal, iTerm, VS Code, Xcode and common 1Password
bundle IDs. Review this list in Settings. Password managers with other bundle IDs
should be added explicitly.

## Double Shift details

Two short press/release cycles, 400 ms by default. Shift used for a capital letter
or a shortcut does not count. The last-word buffer is invalidated after a click,
cursor navigation, a shortcut, a focus change or 30 idle seconds, so Lado does not
guess which old text to delete. Select text to convert an earlier passage.

Selections are limited to **65,536 UTF-16 code units**. Only the last operation is
temporarily retained for exact reversal. No clipboard access is used. Rich-text
formatting preservation depends on the editor and is not guaranteed.

## Development

macOS 13+ and Python 3.11+ are the target. The initial binary is built for Apple
Silicon. From a clone of this repository:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[build]'
python -m unittest discover -s tests -v
python -m lado --self-test
python -m lado
python scripts/build_macos.py
```

The checked-in compact dictionaries work offline; `wordfreq` is **not** a runtime
dependency. Rebuilding them is optional; see [BUILDING.md](docs/BUILDING.md).

## Project

- [Phased checklist / Поэтапный план](docs/ROADMAP.md)
- [Privacy and security](docs/PRIVACY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Build and DMG instructions](docs/BUILDING.md)
- [Validation and limitations](docs/VALIDATION.md)
- [Brand assets](assets/brand/README.md)

Created by **[@sirdimitry](https://x.com/sirdimitry)** · [GitHub](https://github.com/sirdimitry)

Lado code: [MIT](LICENSE). Adapted dictionary data: CC BY-SA 4.0 with embedded
[wordfreq and corpus attribution](src/lado/data/NOTICE.md). Fonts are not bundled.
