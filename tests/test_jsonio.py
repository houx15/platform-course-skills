import os
import errno
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_atomic_write_preserves_existing_posix_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "record.json"
            path.write_text("{}\n", encoding="utf-8")
            path.chmod(0o640)

            write_json_atomic(path, {"ok": True})

            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_atomic_write_preserves_existing_mode_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "record.json"
            path.write_text("{}\n", encoding="utf-8")
            path.chmod(0)

            write_json_atomic(path, {"ok": True})

            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0)

    def test_unsupported_directory_fsync_does_not_report_failure_after_replace(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "record.json"
            with patch("course_toolkit.jsonio.os.fsync", side_effect=[None, OSError(errno.EINVAL, "unsupported")]):
                write_json_atomic(path, {"ok": True})
            self.assertEqual(load_json(path), {"ok": True})

    def test_windows_directory_permission_sync_error_is_ignored_but_posix_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "record.json"
            with patch("course_toolkit.jsonio.os.name", "nt"), patch("course_toolkit.jsonio.os.fsync", side_effect=[None, OSError(errno.EACCES, "unsupported")]):
                write_json_atomic(path, {"ok": True})
            self.assertEqual(load_json(path), {"ok": True})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "record.json"
            with patch("course_toolkit.jsonio.os.fsync", side_effect=[None, OSError(errno.EPERM, "denied")]):
                with self.assertRaises(OSError):
                    write_json_atomic(path, {"ok": True})


if __name__ == "__main__":
    unittest.main()
