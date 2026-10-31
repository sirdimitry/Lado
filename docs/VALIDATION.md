# rc.8 package — 2026-10-31

162 isolated tests pass, including fresh-focus rejection and the Codex-only synthetic gate. DMG integrity, strict ad-hoc signature and bundled self-test pass. rc.8 is installed at /Applications/Lado.app; installed WebKit validation passed 23/23 on the third attempt after permission refresh. The first two attempts failed at auto_wrong_layout before any replacement; cause remains unresolved. See validation/installed-0.1.1-rc.8-webkit-2026-10-31.json and validation/installed-rc8-startup-failures-2026-10-31.json. The user confirmed both automatic correction and double-Shift reversal in the installed Codex app. See validation/installed-rc8-codex-user-2026-10-31.json. Chromium selected text remains untested/unsupported. Historical source-run results below are not a claim that this installed package has already passed.

The synthetic fallback is enabled only for com.openai.codex. Other Chromium apps are untested and do not get synthetic replacement. Whole-field writes remain disabled.

---

# Release candidate rc.8 — 2026-10-31 (source only)

**159 isolated tests pass. 23/23 live local WKWebView cases pass. Live Codex auto-correction and double-Shift reversal pass.**

- **WebKit:** strict `TextOperationReplacePreserveCase`, replacement-response validation and bounded read-back. Green and unchanged from rc.7.
- **Chromium/Codex:** Chromium accepts AX range writes but does not apply them, and `MacAccessibilityTextOperation` is disabled by default. rc.8 adds **one** bounded, tagged synthetic batch (Keyboop technique: Backspace + Unicode) only for detected Chromium/Electron, only after the AX read-back proves the text did not change. Maximum 128 characters, no retry, and `chromium_synthetic` can disable it. Verification reads only the replaced span via `AXStringForRange`.
- **Double Shift:** fires on the **second press** (Keyboop-style), not on release. Any ordinary key or mouse event between the taps cancels the gesture. Synthetic events are created with `flags=0`, so a correction made while Shift is still held keeps the intended case.
- **Live target:** `/Applications/ChatGPT.app` (`com.openai.codex` 26.1027.30824). `ghbdtn ` → `привет `; double Shift (fired on the second press while Shift was held) → `ghbdtn `; composer cleared. Diagnostic: `range-replaced/synthetic-unicode`.
- **Limits:** selected-text conversion in Chromium still uses the AX path and is not covered by the synthetic fallback. The synthetic verification blocks the main run loop for roughly 0.15–0.2 s. Physical input is not suppressed; the posting window is small but a race is possible. Other Chromium apps were not tested live. Whole-field edits remain disabled.
- No clipboard, typing history, network or telemetry. TIS remains main-thread only.
- The installed `/Applications/Lado.app` is rc.7 (ad-hoc), not rc.8. No DMG, build or notarization was produced, and the source changes are not committed.
- Reports: [WebKit 23/23](validation/webkit-0.1.1-rc.8-2026-10-31.json), [Codex Chromium synthetic](validation/codex-chromium-synthetic-2026-10-31.md).

---

# Previous candidate — rc.6 (historical)

rc.6 passes 145 isolated tests and packaging checks. Live WebKit automatic correction FAILS despite granted permissions, an active field and successful AX write responses. Do not claim ChatGPT compatibility or publish this as a working release. The earlier AppKit passes below do not cover this defect.

The diagnostic fixture launched with `--keep-open` on 2026-10-30 was terminated on 2026-10-31; its normal-close binary was restored before subsequent checks. Temporary test app bundles were removed after checks.

The TIS background-thread crash was traced to four macOS crash reports. Source queries now run on the main thread; probes consume cached source IDs.

---

# Current candidate — 2026-10-30

**0.1.1-rc.3** passes 132 isolated checks and 23 live native AppKit cases.
The installed binary, packaged source modules, code signature and DMG were checked.
See [current native report](validation/native-0.1.1-rc.3-2026-10-30.json).

The user still reports no correction in ChatGPT/Codex. This is an unresolved
compatibility defect, not covered by the passing AppKit tests. No universal
editor support or resolution of the ChatGPT field is claimed.

The records below concern earlier candidates and are historical.

---

# Current safety status — 2026-10-29

The published 0.1.0 DMG was followed by a reported system freeze. Its historical
checks below are insufficient evidence of system resilience. The revised source
passes **97 isolated automated checks**, including the formerly failing input
safety gates, passive/deferred pipeline, stale/focus/permission failure paths and
duplicate-instance lock. The unchanged installed rc.2 now passes 19 isolated native checks.
The user's ChatGPT field still fails with `no-focused-element` despite granted
permissions; compatibility there is unresolved. See [the safety audit](validation/safety-audit-2026-10-29.md).

Local candidate **0.1.1-rc.2** is now installed in `/Applications/Lado.app`, with signature,
DMG integrity, bundled-source and mounted-content checks passing. It was not
launched for live input. [Build record](releases/0.1.1-rc.2.md).

---

# Validation / Проверки

Final candidate checked on **2026-10-29**, Apple Silicon, macOS 27.2, Python 3.12.9,
PyObjC 12.2.2 and PyInstaller 6.22.3. This is a preview, not universal editor certification.

## Completed

- [x] **53 automated checks**: correction/context, uppercase protection, exceptions,
  bounded buffers, gesture recognition, secure-input ordering, non-destructive AX
  failure paths, release/version/processor selection, HTTPS/repository URL validation,
  bounded unauthenticated requests and background scheduling/offline failures.
- [x] **19 isolated live checks passed for `/Applications/Lado.app`**. See the
  [sanitized native report](validation/native-2026-10-29.json). Ordinary system key
  events were sent only to the exact project-owned native test pad, with aborts on
  focus change. It checked automatic correction, double Shift and reversal, ALL-CAPS
  and manual override, explicit exceptions, selected multiline text and reversal,
  single-letter words, secure-field blocking and ignored double Shift in secure input.
- [x] The live run also verified one image-only language indicator. Secure input
  dims it and the runtime renderer adds the lock inside that same image. The actual
  EN/RU and lock variants were rendered separately for visual inspection.
- [x] Native TIS discovery and installed layout-data mapping worked for ABC/Russian.
- [x] Bundled self-test passes. The bundled `--check-updates` HTTPS test succeeds
  without starting input monitoring; initially there were no public releases.
- [x] Onboarding, General (including update preference), Exceptions, Privacy and
  About were visually inspected. X and GitHub links target the author profiles.
- [x] `codesign --verify --deep --strict` passes: **ad-hoc, not notarized**.
- [x] `hdiutil verify` passes. DMG contains Lado.app, an Applications link and
  bilingual installation instructions. Final candidate is about **12.5 MiB**.
- [x] Updated-build idle sample: **77 MB physical footprint, 79 MB peak** while
  awaiting input permission. This is a one-machine sample, not a universal cap.
- [x] The installed app and native fixture terminated after the live run. Keyboop
  was closed before testing; Lang Switcher was not running.

## Test-method corrections

An early trial was inconclusive: another layout utility was running, the automation
could send directly to background windows, and an enabled stale macOS permission
row did not authorize the rebuilt code. It must not be treated as a clean Lado
compatibility result. The successful run instead used real system event routing,
verified foreground ownership, refreshed the exact installed app permission and
made synthetic event characters agree with Shift/keycodes. Word replacement also
uses a bounded, validated AX operation rather than destructive Backspace bursts.

The native report contains only case labels and PASS/FAIL metadata, no typed text
or secure-field contents. Update checks are disabled in compatibility mode.

## Still to validate

- [ ] Safari/Chrome password fields and text editors beyond native AppKit controls.
- [ ] Rich-text preservation, large selections, third-layout transitions under live input.
- [ ] Long fast-typing sessions, sleep/wake, unusual shortcuts and active-load memory.
- [ ] VoiceOver and a full light/dark-mode accessibility audit.
- [ ] Intel macOS, Windows and Apple Developer ID/notarization.

Linux GitHub Actions covers the shared engine, preferences and update checker;
macOS-only adapter tests are skipped there. The installed live run was performed
locally and is recorded separately above.
