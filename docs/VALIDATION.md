# Validation / Проверки

This file records evidence, not intended capabilities. Initial checks: 2026-10-28,
Apple Silicon, macOS 27.2, Python 3.12.9, PyObjC 12.2.2, PyInstaller 6.22.3.

- [x] **36 automated checks** on macOS: correction, context, ALL-CAPS protection,
  explicit exceptions, bounded buffers, idle expiry, double Shift recognition,
  selection reversal, password-gate ordering and non-destructive failure paths.
- [x] A separate synthetic regression corpus covers ordinary/wrong-layout words,
  acronyms, mixed scripts and address/code-like tokens. This is not an independent
  statistical accuracy benchmark.
- [x] Native TIS discovery found ABC and Russian on the test Mac. Mappings from
  installed source data convert `ghbdtn` / `GHBDTN` correctly.
- [x] Self-test inside the bundled application exits successfully.
- [x] Onboarding, General, Exceptions, Privacy and About windows opened and were
  visually inspected. X and GitHub destinations are configured in About.
- [x] `codesign --verify --deep --strict` passes (ad-hoc, **not notarized**).
- [x] `hdiutil verify` passes; mounted DMG contains the app, Applications link and
  bilingual installation note. Final candidate is about **12.4 MiB**; app about 25 MiB.
- [x] Initial idle measurement, before active typing: **66 MB physical footprint**,
  76 MB peak; about 126 MiB RSS including shared pages; observed CPU 0.0–0.1%.
  These are one-machine samples, not universal limits or typing-load measurements.
- [x] A sampled `lsof` check found no open network sockets for Lado. Runtime source
  also has no networking/telemetry client. A finite sample is not a general proof.
- [x] Linux GitHub Actions run for commit `79d0017` passed the shared-engine/privacy
  suite; macOS-only adapter tests are skipped on Linux.
- [ ] **End-to-end word/selection conversion still needs a successful retest.**
  An initial live trial exposed an insertion failure after Backspace-based word
  deletion. That strategy was removed: word replacement now validates only the
  observed span and uses AXSelectedText, skipping unsupported editors without
  deleting their text. The replacement path has automated regression coverage;
  this is not a claim that live compatibility has passed.
- [ ] The user requested stopping Lado during testing; it was terminated. Do not
  silently restart it to complete these checks.
- [ ] Native password field with the running app (lock indicator + no mutation),
  browser password fields and third-layout behavior under actual input.
- [ ] TextEdit/Safari/Chrome compatibility, rich text and large selections.
- [ ] Active typing resource measurements, fast input, sleep/wake and shortcuts.
- [ ] Windows and Intel macOS: not implemented/validated in this release.

The Swift fixture in `scripts/manual_fixture.swift` creates disposable plain and
secure native fields. It contains no real credentials. Compile it with an explicit
deployment target, e.g. `swiftc -target arm64-apple-macos13.0`; an ambient deployment
target can otherwise exceed the installed OS version.
