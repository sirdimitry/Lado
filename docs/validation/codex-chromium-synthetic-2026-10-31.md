# Codex / ChatGPT (Chromium) — synthetic fallback live check

**Result: PASS for automatic correction and double-Shift reversal.**

## Target

- `/Applications/ChatGPT.app`, `com.openai.codex`, version 26.1027.30824
- Embedded Codex Framework 156.0.8078.48 (Chromium)

Only synthetic text was used. The composer was empty before the check and was
cleared afterwards; nothing was sent.

## Why the AX path alone fails

Chromium accepts `AXSelectedTextRange` and `AXSelectedText` writes but does not
apply them to the contenteditable. `AXTextOperation` is behind
`MacAccessibilityTextOperation`, disabled by default. A previous attempt also
showed that whole-field `AXValue` works but resets the renderer caret to the
start.

## Implemented fallback (Keyboop technique)

After the AX read-back proves the text did not change, and only for a detected
Chromium/Electron app, Lado builds one batch:

1. `len(observed)` Backspace down/up events;
2. the replacement as Unicode key events in chunks of at most 12 UTF-16 units.

Every event is tagged with Lado's own `eventSourceUserData` marker, so its
listen-only tap ignores it, and every event has `flags=0` so the physical Shift
that is still held cannot uppercase the replacement. The batch is posted to `kCGHIDEventTap` in one pass.
Physical input is not suppressed and there is no retry. The result is verified
by reading only the replaced span with `AXStringForRange`; `AXSelectedText` was
avoided because it timed out in this target.

## Live result

- Composer empty: yes (AXValue equals the public placeholder).
- Typed `ghbdtn ` → composer became `привет `.
- Double Shift (fired on the second press while Shift was still held) → composer became `ghbdtn `.
- Diagnostic: `range-replaced/synthetic-unicode` for both edits.
- Synthetic batch time: about 157 ms per edit; the app processed the next
  double Shift normally.
- Composer cleared to the placeholder; input source restored; Lado stopped;
  Codex window returned to its previous minimized state.

## Limits

- Selected text in Chromium is not covered: `_selection` still uses the AX path.
- The synthetic verification blocks the main run loop for roughly 0.15–0.2 s.
- A physical key could interleave in the tiny posting window; no input is
  suppressed.
- Only Codex was tested live. Other Chromium apps are untested.
- Whole-field reads/writes remain disabled.
