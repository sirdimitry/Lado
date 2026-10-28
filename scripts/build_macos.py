"""Build an ad-hoc signed macOS app and a drag-to-Applications DMG."""
import hashlib
import platform
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise SystemExit("This packaging configuration targets an Apple Silicon Mac.")
    version = (ROOT / "VERSION").read_text().strip()
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
    run(sys.executable, "scripts/collect_licenses.py")
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "packaging/Lado.spec")
    app = ROOT / "dist/Lado.app"
    run("codesign", "--verify", "--deep", "--strict", str(app))
    run(str(app / "Contents/MacOS/Lado"), "--self-test")
    staging = ROOT / "build/dmg-root"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copytree(app, staging / "Lado.app", symlinks=True)
    (staging / "Applications").symlink_to("/Applications")
    (staging / "Install — Установка.txt").write_text(
        "Lado " + version + "\n\nDrag Lado.app to Applications, then open it.\n"
        "Allow Lado in System Settings → Privacy & Security → Accessibility.\n"
        "macOS may also request Input Monitoring.\n\n"
        "Перетащите Lado.app в Программы и запустите установленную копию.\n"
        "Разрешите Lado доступ: Системные настройки → Конфиденциальность и безопасность → Универсальный доступ.\n\n"
        "Offline. No typing history. / Локально. Без истории ввода.\n"
        "Preview: ad-hoc signed, not Apple-notarized. / Предварительная сборка без заверения Apple.\n"
        "https://github.com/sirdimitry/Lado\n", encoding="utf-8")
    dmg = ROOT / f"dist/Lado-{version}-macOS-arm64.dmg"
    run("hdiutil", "create", "-volname", "Lado", "-srcfolder", str(staging),
        "-format", "UDZO", "-fs", "HFS+", "-ov", str(dmg))
    run("hdiutil", "verify", str(dmg))
    digest = hashlib.sha256(dmg.read_bytes()).hexdigest()
    dmg.with_suffix(".dmg.sha256").write_text(f"{digest}  {dmg.name}\n")
    print(f"Built {dmg} ({dmg.stat().st_size / 1024**2:.1f} MiB)")


if __name__ == "__main__":
    main()
