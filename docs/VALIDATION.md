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
