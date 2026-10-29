# Building Lado

Target: macOS 13+, Python 3.11+. Current distributed architecture: arm64.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[build]'
python -m unittest discover -s tests -v
python -m lado --self-test
python scripts/build_macos.py
```

Outputs: `dist/Lado.app`, `dist/Lado-0.1.0-macOS-arm64.dmg`, and its SHA-256 file.
Python is bundled; end users do not install Python or pip dependencies.

PyInstaller builds a windowed application with `LSUIElement`, bundle identifier
`com.sirdimitry.lado` and bundled dictionaries/brand resources. The DMG contains
Lado.app and an Applications link. Signing is ad-hoc unless a real Developer ID
is configured. Ad-hoc signing is not notarization and does not bypass Gatekeeper.
Do not claim an Intel build unless built and tested on an appropriate environment.

## Optional dictionary rebuild

The compact dictionaries are already checked in. To rebuild, install the build-only
`wordfreq==3.1.1` dependency and run:

```sh
pip install -e '.[lexicon]'
python scripts/prepare_lexicon.py
```

The source notice is retained in `docs/licenses/wordfreq-NOTICE.md`; attribution is
also embedded inside the compressed dictionary. Adapted data retain CC BY-SA 4.0.
The app does not ship the wordfreq runtime or its full multi-language corpus.

## Brand rebuild

```sh
python scripts/build_brand.py
```

Uses Pillow and system fonts to render the editable pixel geometry. No generated
raster, external font, network call or image model is needed during a normal build.

## Permissions during testing

Grant permissions to the exact app copy being tested. Moving between source runs,
build folders and Applications can produce separate identities in macOS privacy
settings. Never change the bundle ID between normal releases. Stable Developer ID
signing is recommended for a mature release to improve permission continuity.

## Isolated native compatibility run

Compile `scripts/manual_fixture.swift` with `swiftc -target arm64-apple-macos13.0`
into `build/LadoTestPad.app` (bundle ID `com.sirdimitry.lado-testpad`). Launch the
fixture, then start the installed Lado with:

```sh
open /Applications/Lado.app --args --compatibility-test --run-compatibility-test --fixture-root "$PWD"
```

The runner requires permission for that exact signed app, accepts only the
project-owned fixture, aborts if focus leaves it, restores temporary settings,
writes non-text PASS/FAIL metadata to `build/compatibility-results.json` and closes
both apps. It does not contact GitHub. To test HTTPS separately without starting
input monitoring, run `Lado.app/Contents/MacOS/Lado --check-updates`.

Ad-hoc rebuilds can invalidate macOS access while the old row remains enabled.
Remove the stale Lado entry and re-add the exact app copy in Accessibility (named
Device Control and Data Access on newer macOS). Toggling the old row alone may not
refresh its code requirement. Normal releases should use stable Developer ID signing.
