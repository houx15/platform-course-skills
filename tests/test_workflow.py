import tempfile
import unittest
from pathlib import Path

from course_toolkit.jsonio import load_json, write_json_atomic


class AtomicJsonTests(unittest.TestCase):
    def test_write_json_atomic_creates_parent_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".course-work" / "session.json"

            write_json_atomic(path, {"phase": "intake", "title": "课程"})

            self.assertEqual(load_json(path)["title"], "课程")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
