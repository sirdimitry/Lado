import os
from pathlib import Path
import stat
import tempfile
import unittest

if os.name == "posix":
    from lado.instance import InstanceLock


@unittest.skipUnless(os.name == "posix", "POSIX app lock")
class InstanceTests(unittest.TestCase):
    def test_second_copy_is_rejected_until_first_exits(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "instance.lock"
            first, second = InstanceLock(path), InstanceLock(path)
            try:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                first.close()
                self.assertTrue(second.acquire())
                self.assertEqual(path.read_bytes(), b"")
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            finally:
                first.close()
                second.close()

    def test_symlink_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "instance.lock"
            target = Path(d) / "target"
            target.write_text("unchanged")
            path.symlink_to(target)
            with self.assertRaises(OSError):
                InstanceLock(path).acquire()
            self.assertEqual(target.read_text(), "unchanged")
