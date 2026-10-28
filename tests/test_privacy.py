import ast
from dataclasses import asdict
import json
from pathlib import Path
import stat
import tempfile
import unittest

from lado.settings import Settings, load, save


class PrivacyTests(unittest.TestCase):
    def test_only_explicit_settings_are_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            s = Settings(exceptions=["MyBrand"])
            save(s, path)
            self.assertEqual(json.loads(path.read_text()), asdict(s))
            self.assertEqual(load(path), s)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(list(Path(d).iterdir()), [path])

    def test_untrusted_settings_are_validated(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            p.write_text('{"automatic":"yes","double_shift_ms":0,"exceptions":[3,"word"],"history":["secret"]}')
            s = load(p)
            self.assertIs(s.automatic, True)
            self.assertEqual(s.double_shift_ms, 200)
            self.assertEqual(s.exceptions, ["word"])
            self.assertFalse(hasattr(s, "history"))

    def test_no_network_or_logging_imports_in_runtime(self):
        root = Path(__file__).parents[1] / "src/lado"
        prohibited = {"socket", "requests", "http", "urllib", "httpx", "aiohttp", "logging", "sentry_sdk", "subprocess"}
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                for name in names:
                    self.assertNotIn(name.split(".")[0], prohibited, str(path))

    def test_corrupt_settings_fall_back(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            path.write_text("invalid json")
            self.assertEqual(load(path), Settings())
