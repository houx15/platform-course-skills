import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT


VALIDATOR = ROOT / "scripts" / "validate-course-definition.ts"
SNAPSHOT_CHECKER = ROOT / "scripts" / "check-course-contract-sync.py"
GOLDEN = (
    ROOT
    / "packages"
    / "course-contract"
    / "test"
    / "fixtures"
    / "coverage-course.json"
)


def run_validator(input_path):
    return subprocess.run(
        [
            "node",
            "--import",
            "tsx",
            str(VALIDATOR),
            str(input_path),
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class SharedCourseContractTests(unittest.TestCase):
    def test_shared_validator_accepts_upstream_golden_course(self):
        result = run_validator(GOLDEN)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["courseId"], "evidence-comparability")
        self.assertIn("assets/videos/case.mp4", payload["assetPaths"])
        self.assertEqual(payload["assetPaths"], sorted(payload["assetPaths"]))

    def test_shared_validator_returns_ordered_contract_issues(self):
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        broken = copy.deepcopy(golden)
        broken["course"]["parts"][0]["slices"][0]["layout"]["slots"] = []
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "broken.json"
            input_path.write_text(json.dumps(broken), encoding="utf-8")

            result = run_validator(input_path)

        self.assertEqual(result.returncode, 2, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["issues"][0]["layer"], "structural")
        self.assertIn("slots", payload["issues"][0]["path"])

    def test_shared_validator_hides_stack_trace_for_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "broken.json"
            input_path.write_text("not json", encoding="utf-8")

            result = run_validator(input_path)

        self.assertEqual(result.returncode, 3)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(" at ", result.stderr)

    def test_snapshot_manifest_matches_vendored_contract(self):
        result = subprocess.run(
            [sys.executable, str(SNAPSHOT_CHECKER), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mismatches"], [])


if __name__ == "__main__":
    unittest.main()
