> **Superseded 2026-10-31 by rc.8:** the synthetic fallback from Keyboop was implemented and verified in the real Codex composer. See [codex-chromium-synthetic-2026-10-31.md](codex-chromium-synthetic-2026-10-31.md). The analysis below is kept as history.

# Codex / ChatGPT (Chromium) target check — 2026-10-31

**Result: the WebKit fix does not transfer to this target. No safe AX-only range
replacement exists in this Chromium build. No release is claimed.**

**Decision (2026-10-31): Option A.** Keep the AX-only design. Chromium-based
apps are marked unsupported; no synthetic input and no whole-field write were
enabled.

## Target

- `/Applications/ChatGPT.app`, `CFBundleIdentifier` **com.openai.codex**
- Version **26.1027.30824**
- Embedded **Codex Framework 156.0.8078.48** (Chromium, not WebKit)

The composer is an `AXTextArea` inside an `AXWebArea`. Only synthetic text was
used; nothing was sent. The composer was confirmed empty before each attempt by
comparing `AXValue` with the public placeholder/description, and it was cleared
afterwards.

## What the live run showed

1. The listen-only event tap connected, the probe reported `active`/`ready` on
   the Codex `AXTextArea`, and the engine received the synthetic `ghbdtn `.
2. The app set `AXSelectedTextRange` to `(0, 7)`. The AX call returned success.
   An immediate `AXSelectedText` read returned `""`; a read ~20 ms later
   returned `ghbdtn `. Chromium applies the selection asynchronously. rc.6
   therefore aborted with `observed-span-mismatch`.
3. After adding a bounded settle, the app reached the write. Chromium's
   `AXSelectedText` setter (`kReplaceSelectedText`) returned success but the
   text did not change; the honest result became `selected-text-unverified`.
4. Chromium's `AXTextOperation` is **not** in the composer's parameterized
   attributes. The feature `kMacAccessibilityTextOperation` is
   `FEATURE_DISABLED_BY_DEFAULT` in Chromium
   (`ui/accessibility/accessibility_features.cc`); Codex does not enable it.
5. The only mutation that actually works is the whole-field `AXValue` write
   (Blink `setInnerText`). It is unsafe for automatic correction: after writing
   `hello привет `, the next physical key was inserted at the **start** of the
   composer (`1hello привет `). The selection-based caret write did not move the
   renderer caret. Whole-field writes also lose rich text/undo and read the
   entire draft.
6. `AXReplaceRangeWithText` is advertised but undocumented; public reports
   describe crashes/garbage when it is used, so it is not a safe candidate.

## Why this is a platform limit, not a permission problem

Accessibility and Input Monitoring were granted and the tap was connected. The
failure is inside Chromium's macOS accessibility implementation for this
contenteditable: range writes are accepted but not applied to the renderer, and
the range-replacement operation is compiled off by default.

## Options that require an explicit decision

- **A. Keep the safe AX-only design.** Ship the WebKit fix; mark Chromium-based
  apps unsupported. No new synthetic input, no whole-draft reads.
- **B. Targeted synthetic input for Chromium.** Select the word with
  `Shift+Option+Left` (or `Shift+Left` × length) and post the replacement, with
  strict focus/secure-field gating and abort paths. This changes the current
  safety model and needs a new incident review.
- **C. Whole-field `AXValue` write.** Works, but resets the caret to the start
  and reads/writes the entire draft. Not recommended.
- **D. Enable Chromium's AX text operation.** `MacAccessibilityTextOperation`
  must be enabled by the host app (launch flag or vendor change). Lado cannot
  toggle it inside a running Codex process.

Option A is the only one that preserves the current input/privacy guarantees.
Options B and C must not be enabled silently.

## Cleanup

The synthetic text was cleared, the input source was restored, the Codex window
was returned to its previous minimized state, Lado and all test processes were
stopped, and the temporary test `.app` bundles were removed.
