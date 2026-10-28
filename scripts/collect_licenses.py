"""Copy distributable runtime notices into the application."""
from importlib.metadata import distribution
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/licenses/runtime"
OUT.mkdir(parents=True, exist_ok=True)
for name in ("pyobjc-framework-Cocoa", "pyobjc-framework-Quartz", "pyobjc-framework-CoreText", "pyinstaller"):
    dist = distribution(name)
    for entry in dist.files:
        if str(entry).endswith(("LICENSE.txt", "COPYING.txt")):
            (OUT / (name + ".txt")).write_bytes(dist.locate_file(entry).read_bytes())
python_license = Path(sys.base_prefix) / "lib/python3.12/LICENSE.txt"
if python_license.exists():
    (OUT / "Python.txt").write_bytes(python_license.read_bytes())
print("Runtime license notices:", OUT)
