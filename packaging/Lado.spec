# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH).parent
version = (root / "VERSION").read_text().strip()
a = Analysis(
    [str(root / "scripts/launcher.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[
        (str(root / "src/lado/data"), "lado/data"),
        (str(root / "src/lado/resources"), "lado/resources"),
        (str(root / "LICENSE"), "licenses"),
        (str(root / "docs/licenses"), "licenses/dependencies"),
    ],
    hiddenimports=["AppKit", "Quartz", "ApplicationServices", "CoreFoundation", "Foundation", "objc"],
    hookspath=[],
    excludes=["wordfreq", "PIL", "numpy", "matplotlib", "tkinter", "pytest", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Lado", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          target_arch="arm64", codesign_identity=None, entitlements_file=None,
          disable_windowed_traceback=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Lado")
app = BUNDLE(coll, name="Lado.app", icon=str(root / "assets/brand/Lado.icns"),
    bundle_identifier="com.sirdimitry.lado", version=version,
    info_plist={
        "CFBundleDisplayName": "Lado",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        "NSSupportsAutomaticGraphicsSwitching": True,
        "NSHumanReadableCopyright": "© 2026 sirdimitry. MIT; dictionaries CC BY-SA 4.0.",
    })
