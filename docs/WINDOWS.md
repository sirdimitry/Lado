# Windows implementation

The Windows app is a native rewrite of the macOS adapter, not a wrapper around
the Python app. `layout.py`, `engine.py` and `settings.py` remain the shared
specification; the C++ port in `windows/src/engine.cpp` is a line-by-line
translation with the same constants, thresholds and test corpus.

The manual-gesture model — undo the last fix, otherwise convert the selection,
otherwise the whole typed phrase (manual mode), otherwise the last word, then
switch the layout — follows [Keyboop](https://github.com/iffuno/keyboop) (MIT).
No Keyboop code is used; the Windows implementation reads selections through UI
Automation and types Unicode without ever touching the clipboard.

- Language: C++20, Win32 API, no third-party libraries.
- Binary: one `Lado.exe`, static C/C++ runtime, dictionary embedded as an
  `RCDATA` resource (≈2.4 MB; the whole executable is ≈6.2 MB).
- Settings: `%APPDATA%\Lado\settings.json`.
- Diagnostics: `%LOCALAPPDATA%\Lado\lado.log` (metadata only, rotates at 256 KiB).

## Component map

| File | Responsibility |
| --- | --- |
| `src/layout.cpp` | Physical-key RU/EN conversion table, script detection |
| `src/engine.cpp` | `Detector`, `Buffer`, `DoubleShift` — direct port of `engine.py` |
| `src/lexicon.cpp` | Loader for the compact frequency dictionary |
| `src/settings.cpp` | Bounded JSON settings, defaults, normalisation |
| `src/json.cpp` | Small bounded JSON reader/writer (no external dependency) |
| `src/app.cpp` | Orchestration: keys, pending edits, tray state, menu, lifecycle |
| `src/platform/hook.cpp` | `WH_KEYBOARD_LL` + `WH_MOUSE_LL` |
| `src/platform/focus.cpp` | Foreground window, thread layout, executable name cache |
| `src/platform/secure.cpp` | UIA worker: `IsPassword`, selection read, watchdog |
| `src/platform/layout_switch.cpp` | `WM_INPUTLANGCHANGEREQUEST` for the corrected language |
| `src/platform/input.cpp` | `SendInput` Unicode/Backspace replacement |
| `src/platform/tray.cpp` | Notification-area icon and tooltip |
| `src/platform/ui.cpp` | Programmatic settings window, DPI aware |
| `src/platform/autostart.cpp` | Per-user `Run` key |
| `src/strings.cpp` | RU/EN UI strings chosen from the Windows UI language |

The dictionary and icons are generated artifacts:

- `windows/tools/build_lexicon.py` reads the same
  `src/lado/data/frequencies.json.gz` used by macOS and writes
  `windows/data/lexicon.bin` (little-endian, UTF-16 keys, float32
  `score / 100`, casefolded). `data/lexicon.txt` records counts and SHA-256.
- `windows/tools/make_icons.py` renders six tray states (RU, EN, RU/EN secure,
  other layout, paused) and the application icon from the brand assets.

## Event flow

1. `WH_KEYBOARD_LL` runs on the UI thread. The callback only tracks modifiers,
   translates the key with `ToUnicodeEx` using the foreground thread's `HKL`,
   and feeds a bounded buffer. It never calls `SendInput` and never blocks on
   another process.
2. Space is a word boundary: `Buffer::finish(" ")`. A bare Enter is a boundary
   too, but it is **swallowed**: the word is corrected first and a synthetic
   Enter is sent afterwards, so a chat message is never sent in the wrong
   layout. Tab, Escape, arrows, navigation keys, clicks and shortcuts clear the
   buffer. Backspace edits it. Any Ctrl/Alt/Win key clears it.
3. When `Detector::correction` returns a confident edit, the app schedules
   `WM_TIMER` in 30 ms and lets the physical space reach the target first. A
   zero-delay replacement from inside the hook would race the pending keystroke.
4. `App::apply_pending` re-validates everything, then performs a single
   `SendInput` batch: `N` Backspaces and the converted text as
   `KEYEVENTF_UNICODE` events. No clipboard, no `WM_SETTEXT`, no UIA writes.
   After a successful replacement the target layout is selected, so the next
   word is typed in the language of the corrected text.
5. Double Shift only posts a message; it never reads UIA inside the hook. The
   handler mirrors Keyboop's order: undo the last edit; if nothing was typed,
   convert the **selection** (UI Automation `TextPattern`, read asynchronously
   by the worker, at most 500 characters, single line); if automatic correction
   is off and the session has at least two words (≤200 characters, ≤8 idle
   seconds), convert the **whole phrase**; otherwise convert the last word.
   Selection text is overwritten by typing; a phrase is one delete-and-retype
   batch. No clipboard is involved.

The generation counter increments on every non-injected key-down and mouse
button. A pending edit is dropped if anything happened between scheduling and
applying, so a fast typist never loses the following character.

## Safety gates

A correction is attempted only when **all** of the following hold:

- not paused;
- foreground window exists and is not Lado itself;
- the executable name is known and not in the app-exclusion list;
- the UIA secure-input state is `Clear` (not `Secure`, not `Unknown`);
- the active layout is English or Russian;
- at edit time: the foreground window and `HKL` are unchanged, no input event
  occurred since the edit was scheduled, and a fresh synchronous check of
  classic `Edit` + `ES_PASSWORD` focus is negative.

The secure-input worker polls UI Automation every 300 ms and is additionally
nudged by `EVENT_OBJECT_FOCUS`/`EVENT_SYSTEM_FOREGROUND` hooks. A query that
takes longer than 2 s flips the state to `Unknown`, which suppresses all
corrections until it returns. If UIA cannot be created at all, Lado logs the
failure and falls back to the classic password check only.

`SendInput` is rejected by UIPI when the target runs elevated. Lado logs the
rejection and clears its buffer; it never falls back to a different injection
method.

## Buffer and invalidation

At most three completed words and one current word (128 UTF-16 units) are kept.
A separate session list keeps every completed word of the current phrase
(200 characters max, 8 idle seconds) for manual phrase conversion. The buffer
is cleared by:

- 30 idle seconds (`Buffer::touch`); the phrase session expires after 8;
- foreground window change, or a real layout change (event hook and 250 ms
  state timer). Lado's own layout switch updates the cached `HKL`, so it does
  not drop the undo context;
- mouse button, Return/Tab/Escape/arrows/Home/End/Page/Insert/Delete/F-keys;
- Ctrl, Alt or Win, and any shortcut;
- Pause;
- overflow (a single token longer than 128 units);
- closing/opening the settings window (focus leaves the target);
- a detected password field.

## Why not clipboard or UI Automation writes

The clipboard is a global shared buffer and would expose text to other
programs, while UIA range writes are ignored by Chromium and can be slow or
hang. Unicode `SendInput` is the narrowest mechanism that works across Win32,
WinUI and Chromium editors. Its limitation is that it types into whatever has
focus; the re-validation above is what makes that acceptable.

Selections are **read** through UIA `TextPattern` on the worker thread (never
through Ctrl+C) and replaced by typing over them. Controls that do not expose
`TextPattern` — notably the classic Win32 `Edit` — deliberately do nothing when
double Shift finds nothing typed, rather than falling back to the clipboard.

## Settings file

```json
{
  "version": 1,
  "automatic": true,
  "double_shift_ms": 400,
  "case_sensitive": false,
  "exceptions": ["Ghbdtn"],
  "excluded_apps": ["WindowsTerminal.exe", "cmd.exe", "Code.exe", "1Password.exe"]
}
```

The loader caps the file at 1 MiB, limits each list to 5 000 entries of 256
characters, drops duplicates, and clamps the interval to 200–800 ms on both
load and save. A damaged file falls back to defaults instead of failing.
Exclusions match the executable file name case-insensitively.

Autostart is not stored in JSON: it is the presence of the quoted executable
path in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Lado`.

## DPI, theming and localisation

The manifest declares Per-Monitor-V2 DPI awareness and common-controls v6. The
settings window is built in code with scaled coordinates, Segoe UI at 9 pt and
`WM_DPICHANGED` handling. UI strings follow the Windows UI language (Russian or
English); the tray icons are pre-rendered per size so two letters stay legible
at 16 px.

## Testing

- `lado_tests.exe`: 182 checks. The regression corpus is the same
  `tests/corpus.json` used by the Python suite; detection, conversion, buffer,
  phrase-session, Enter, gesture, JSON and settings tests mirror
  `tests/test_engine.py`.
- `windows/tools/qa_typing.ps1`: end-to-end check of the actual hook and
  replacement path through `LadoQaPad.exe`. It expects the automatic correction
  and double-Shift reversal in a normal field, no change in an `ES_PASSWORD`
  field, selection conversion in a RichEdit field, and correction before Enter.
  It sets `LADO_QA_ACCEPT_INJECTED=1` for the Lado process so `SendInput` from
  the harness is observed; Lado's own events carry a `dwExtraInfo` tag and are
  always ignored. The pad writes its text to a report file so password content
  never has to cross the `WM_GETTEXT` boundary.
- `.github/workflows/windows.yml`: MSVC build and `ctest` on `windows-latest`.

## Parity with macOS

| Capability | macOS 0.1.1-rc.8 | Windows 0.1.1-windows.1 |
| --- | --- | --- |
| Automatic correction, shared dictionary | yes | yes |
| ALL-CAPS/digit/URL guards, exceptions | yes | yes |
| Double Shift last word + undo | yes | yes |
| Double Shift selected text | yes (AX ranges, bounded) | yes where UIA `TextPattern` exists, ≤500 chars, single line |
| Double Shift whole typed phrase | no | yes, in manual mode (auto off) |
| Correction before Enter | no (Return clears context) | yes |
| Password/secure input | AX + focus checks | UIA worker + classic check |
| App exclusions | bundle IDs | executable names |
| RU/EN indicator | menu bar item | tray icon with dynamic tooltip |
| Layout pair selection | configurable | automatic EN/RU detection |
| Layout switch after correction | no | yes (`WM_INPUTLANGCHANGEREQUEST`) |
| Update checks | GitHub releases | **no network code** |
| Whole-field fallback | optional, off | not applicable |
| Installer/signing | DMG, ad-hoc | portable exe, unsigned |
| Tests | 162 + live app checks | 182 + isolated QA harness |

## Known limitations

- **Selections in classic `Edit` controls** and controls without a UIA
  `TextPattern` are not converted; nothing is guessed or copied. Multiline
  selections and selections longer than 500 characters are refused.
- **Elevated windows** (Task Manager, admin consoles) reject `SendInput`; the
  app cannot fix text there without an elevated helper, which is out of scope.
- **Layout switching** depends on the target app handling
  `WM_INPUTLANGCHANGEREQUEST`; a few games and custom editors ignore it.
- **IME and dead keys**: a dead-key or IME composition clears the buffer.
  Composed input is not reconstructed.
- **Non-EN/RU layouts** pause processing. The pair is detected from installed
  layouts; a per-app layout override is not read.
- **Games and anti-cheat** may block or flag global low-level hooks; Lado is a
  keyboard utility, but it cannot control how third-party software reacts.
- **No installer or code signing**, so SmartScreen shows an unknown-publisher
  warning for a downloaded build.
- The tray icon lives in the notification area; Windows 11 may hide it in the
  overflow flyout until the user pins it.

## Future work

1. Selection support in classic `Edit` and terminal-like controls without a
   clipboard fallback (for example a small helper that reads `EM_GETSEL` inside
   the target process, with the same bounds).
2. Optional "do not switch layout after conversion" for users who prefer the
   macOS behavior.
3. A signed MSIX or MSI installer and an update checker with the same privacy
   rules as macOS.
4. Per-app layout tracking if Windows exposes it reliably.
