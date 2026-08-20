import os
import tempfile
import unittest
from pathlib import Path

from course_toolkit.jsonio import load_json, write_json_atomic


class JsonIoTests(unittest.TestCase):
    def test_atomic_write_uses_an_unpredictable_exclusive_temp_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "record.json"
            outside = root / "outside.json"
            outside.write_text("outside", encoding="utf-8")
            legacy_temp = root / f".record.json.{os.getpid()}.tmp"
            legacy_temp.symlink_to(outside)

            write_json_atomic(path, {"ok": True})

            self.assertEqual(outside.read_text(encoding="utf-8"), "outside")
            self.assertEqual(load_json(path), {"ok": True})

    def test_atomic_write_rejects_a_symlink_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.json"
            outside.write_text("outside", encoding="utf-8")
            path = root / "record.json"
            path.symlink_to(outside)

            with self.assertRaises(ValueError):
                write_json_atomic(path, {"ok": True}, reject_symlinks=True)

            self.assertEqual(outside.read_text(encoding="utf-8"), "outside")


if __name__ == "__main__":
    unittest.main()
