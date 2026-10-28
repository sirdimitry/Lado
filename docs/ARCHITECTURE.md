# Architecture

`layout.py`, `engine.py` and `settings.py` are platform-independent. The native
adapter is under `platforms/`; the current UI uses AppKit via PyObjC. Windows will
need its own adapter and UI, not a rewrite of the correction engine.

1. **Safety gate:** protected input, permissions, app exclusions, source pair and
   supported editable focus are checked before reading event characters.
2. **Event stream:** a session-level Core Graphics event tap observes input.
   Events synthesized by Lado are tagged and excluded from its own processing.
3. **Context:** a bounded in-memory word buffer, invalidated when assumptions
   about the caret or focused element are no longer reliable.
4. **Decision:** local dictionary frequency difference, uppercase/exception/token
   guards and stronger context requirements for single-letter tokens.
5. **Replacement:** marked Unicode/key events at the current event tap, or an
   accessibility selected-text replacement when supported. No clipboard access.
6. **Source:** TIS APIs identify/select the configured layout. Key mappings are
   built from the installed layout data rather than assuming all Russian layouts
   have identical punctuation.
7. **UI:** native status item, settings tabs, permission onboarding and About.

The event callback is deliberately bounded and does not run inference or load
files. Dictionaries load once at startup. Accessibility messages have short
timeouts. A timed-out event tap is re-enabled with cleared context; an unexpected
callback exception stops processing without logging the event or selection.

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
