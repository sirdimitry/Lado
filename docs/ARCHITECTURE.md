# Architecture

`layout.py`, `engine.py` and `settings.py` are platform-independent. The native
adapter is under `platforms/`; the current UI uses AppKit via PyObjC. Windows will
need its own adapter and UI, not a rewrite of the correction engine.

1. **Safety gate:** protected input, permissions, app exclusions, source pair and
   supported editable focus are checked before reading event characters.
2. **Event stream:** a session-level Core Graphics event tap observes input.
   The production adapter is listen-only and never submits keyboard events.
   A bounded queue of at most 16 native event copies is drained outside the callback
   after fresh focus/security checks; stale events expire after 250 ms.
3. **Context:** a bounded in-memory word buffer, invalidated when assumptions
   about the caret or focused element are no longer reliable.
4. **Decision:** local dictionary frequency difference, uppercase/exception/token
   guards and stronger context requirements for single-letter tokens.
5. **Replacement:** words use a validated, bounded accessibility range and
   selected-text replacement; unsupported word replacements are skipped without
   deleting anything. Explicit user selections also require atomic accessibility replacement;
   unsupported editors are skipped. No clipboard access or synthetic fallback.
6. **Source:** TIS APIs identify/select the configured layout. Key mappings are
   built from the installed layout data rather than assuming all Russian layouts
   have identical punctuation.
7. **UI:** native status item, settings tabs, permission onboarding and About.

The event callback is deliberately bounded and does not run inference or load
files. Dictionaries load once at startup. Accessibility messages have short
timeouts. A timeout, user-requested tap disable or unexpected callback exception latches
processing off until process restart. The UI timer cannot re-enable a faulted tap.
AX calls and edits execute only after returning from the passive callback.
A process-lifetime advisory lock prevents concurrent installed/source copies.

No background model process, polling of document contents, whole-document reads,
or automatic learning from typed text. A 0.5-second state check updates permissions,
focus status and idle expiry; it reads metadata, not field contents.

## Future local model

A small classifier may evaluate ambiguous candidates using synthetic/public test
data. It must select a layout, not generate text. No model is included in 0.1.0.
Memory/latency measurements and a reduction in false positives are prerequisites
for making it a runtime dependency.

## Important implementation limits

Selection support and rich-text behavior depend on the host editor. Ordinary
typing is only processed in supported accessibility text elements. Cursor movement
performed through app-specific commands may not always be observable; app-level
integration tests are required. This preview is intentionally conservative.

## Optional update checker

`updates.py` is the only network boundary. It accepts the constant app version and
processor architecture, never text buffers or personal exceptions. One background
worker requests a fixed public GitHub release endpoint with a timeout, response-size
limit and in-memory ETag caching. Checks run at startup and hourly when enabled.
Downloads must be HTTPS assets of sirdimitry/Lado, match the release version and
processor, and are opened in the default browser only after Update is chosen.

## Isolated live checks

With `--compatibility-test --run-compatibility-test`, the app runs synthetic physical
key events only in the exact project-owned LadoTestPad.app. It aborts on a focus
change, restores temporary settings, writes PASS/FAIL metadata without text, and
closes both apps. Update checking is disabled in this mode.

After the 2026-10-29 freeze report, the old native report is historical only.
Return/Tab always retain their native action and no longer trigger corrections.
A correction is skipped when subsequent input, a changed range, a security
transition, or an expired edit deadline invalidates its assumptions.
