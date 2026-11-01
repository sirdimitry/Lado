# Lado for Windows

A native Windows build of Lado: the RU/EN keyboard-layout companion. It is
written in **C++20 against the Win32 API** — the platform Windows itself is
built on. No Electron, no .NET runtime, no bundled Python, no background
service. The dictionary is embedded in the `.exe`, so the release artifact is a
single portable file.

**Status: preview `0.1.1-windows.1`.** Automatic correction, double-Shift of a
word/selection/phrase, Enter pre-conversion and layout switching work on
ordinary Win32, WinUI and Chromium text fields. Update checks are not
implemented. See [the design and limitation notes](../docs/WINDOWS.md).

## What it does

- Shows the active language as a **RU / EN tray icon**, dimmed with a small lock
  while a password field has focus.
- Corrects a confident wrong-layout word at a word boundary:
  `ghbdtn` + Space → `привет`. The decision uses the same local frequency
  dictionary and the same rules as the macOS app.
- Fixes the word **before Enter** in chat and search boxes, so a wrong-layout
  message is not sent.
- Switches the application's layout to the language of the corrected text.
- **Double Shift** is a single manual gesture with the same decision order as
  Keyboop: undo the last edit → convert the selection → convert the whole typed
  phrase when automatic correction is off → convert the last word. Selections
  are read through UI Automation, never through the clipboard.
- Skips ALL-CAPS words, digits, e-mail/URL-like tokens and mixed-script words.
- Supports personal word exceptions (optionally case-sensitive) and
  per-application exclusions (`chrome.exe`, `Code.exe`, …).
- Pause, start with Windows (per-user Run key), single instance; opening a
  second copy brings up Settings.
- `README`-level privacy: text is processed in memory only, there is no network
  code in this binary, no clipboard access and no typing history.

## Not implemented yet

- **Multiline selections** and selections in controls that expose no UI
  Automation `TextPattern` (classic `Edit`, some terminals). Single-line
  selections in RichEdit, WinUI and Chromium-based apps are supported.
- Update checks. The Windows binary makes no network requests at all.
- Other language pairs; anything except an English or Russian layout pauses
  processing.
- Windows on ARM, signed installers, auto-update.

## Build

Requirements: Windows 10/11, CMake 3.21+, and either Visual Studio 2022
("Desktop development with C++") or MinGW-w64 GCC 13+.

Visual Studio:

```powershell
cmake -S windows -B windows/build -A x64
cmake --build windows/build --config Release
ctest --test-dir windows/build -C Release --output-on-failure
```

MinGW (the reference build used w64devkit 2.11 / GCC 16):

```powershell
cmake -S windows -B windows/build-mingw -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
cmake --build windows/build-mingw -j
ctest --test-dir windows/build-mingw --output-on-failure
```

The executable appears at `windows/build/Release/Lado.exe` (MSVC) or
`windows/build-mingw/Lado.exe` (MinGW). `windows/build.ps1` wraps the common
case.

## Run

```powershell
.\windows\build\Release\Lado.exe
```

The app has no main window: it lives in the notification area. Left- or
right-click the tray icon for Pause, automatic correction, app exclusion,
Settings, About and Quit. Settings are stored in
`%APPDATA%\Lado\settings.json`; remove the executable and that folder to
uninstall. "Start with Windows" writes
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Lado`.

On first use, make sure an English and a Russian layout are installed. If any
other language is active, Lado pauses rather than guessing.

## Design in one paragraph

A `WH_KEYBOARD_LL` hook observes keys on the UI thread and converts the current
layout's characters with `ToUnicodeEx`. A bounded buffer keeps at most three
completed words plus the current word; a separate session list (200 characters,
8 idle seconds) is used for phrase conversion. At a space boundary the detector
compares dictionary weights and, when confident, schedules a replacement 30 ms
later so the space has reached the target app. A bare Enter is swallowed, the
word is fixed, then a synthetic Enter is sent. The replacement is one
`SendInput` batch: N Backspaces followed by Unicode characters (a selection is
overwritten directly). Before writing, the app re-checks the foreground window,
the layout, a generation counter, a fresh classic password check and the UIA
password state. The selected text, when used, is read asynchronously through
UIA `TextPattern` on a worker thread. No clipboard, no `WM_SETTEXT`, no
accessibility writes.

## Privacy boundaries

- Only `settings.json` and the optional autostart value are persisted. The log
  file (`%LOCALAPPDATA%\Lado\lado.log`) contains error metadata, never typed
  text.
- The in-memory buffer clears after 30 idle seconds, on focus/layout change, on
  Pause, on mouse clicks/caret keys, and when a password field is detected. The
  phrase session expires after 8 idle seconds.
- UI Automation is used for two things only: the `IsPassword` property of the
  focused element, and — when you press double Shift with nothing typed — the
  selected text of the focused element (at most 500 characters, held in RAM for
  the replacement). Password fields are never read.
- There is no network code in this build. GitHub update checks exist only in
  the macOS app.

## Tests

`lado_tests.exe` runs 182 checks: the shared regression corpus from
`../tests/corpus.json`, dictionary-backed detection, buffer/manual-toggle and
phrase-session semantics, Enter boundaries, double-Shift timing, JSON parsing
and settings bounds. The test binary embeds paths to the repo data so `ctest`
works from any build folder.

For an end-to-end check of the real hook and replacement path:

```powershell
powershell -ExecutionPolicy Bypass -File windows/tools/qa_typing.ps1
```

It starts Lado with `LADO_QA_ACCEPT_INJECTED=1` and checks six cases with
`SendInput` on `LadoQaPad.exe`: automatic correction, double-Shift reversal, a
real `ES_PASSWORD` field (no correction), a RichEdit selection, and conversion
before Enter. **It takes the foreground for about ten seconds** — do not run it
during a game or a call. The environment variable is only set for that process;
a normal Lado session ignores injected input.

## Regenerating checked-in artifacts

```powershell
python windows/tools/build_lexicon.py   # data/lexicon.bin from src/lado/data
python windows/tools/make_icons.py      # assets/icons/*.ico from assets/brand
```

Both scripts use only the Python standard library plus Pillow (already required
by the macOS build). `data/lexicon.txt` records the format version, word counts
and SHA-256 of the generated dictionary.

## Project docs

- [Windows design, safety model and parity matrix](../docs/WINDOWS.md)
- [Architecture of the shared engine](../docs/ARCHITECTURE.md)
- [Privacy](../docs/PRIVACY.md)
- [Roadmap](../docs/ROADMAP.md)
