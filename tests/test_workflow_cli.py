import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "course-workflow.py"
COMPILER = REPOSITORY_ROOT / "scripts" / "compile-course.py"
APPROVED = (
    REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "course-blueprint"
    / "approved-blueprint.json"
)


class WorkflowCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "course"
        self.root.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def json_result(self, *arguments):
        completed = self.run_cli(*arguments)
        return completed, json.loads(completed.stdout)

    def init(self, *extra):
        return self.json_result(
            "init",
            self.root,
            "--course-local-id",
            "demo",
            *extra,
            "--json",
        )

    def test_init_creates_session_and_stable_json_summary(self):
        material = self.root / "materials" / "a.md"
        material.parent.mkdir()
        material.write_text("source", encoding="utf-8")

        completed, payload = self.init("--source", "materials/a.md")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["phase"], "intake")
        self.assertEqual(payload["status"], "in-progress")
        self.assertEqual(payload["completedGates"], [])
        self.assertEqual(payload["invalidatedGates"], [])
        self.assertEqual(payload["issues"], [])
        self.assertEqual(payload["pendingDecisions"], [])
        self.assertEqual(payload["nextAction"], "complete G0")
        self.assertTrue((self.root / ".course-work" / "session.json").is_file())

    def test_status_restores_existing_session(self):
        self.init()

        completed, payload = self.json_result("status", self.root, "--json")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["courseLocalId"], "demo")

    def test_reconcile_reports_missing_source_as_readable_issue(self):
        self.init("--source", "materials/missing.md")

        completed, payload = self.json_result("reconcile", self.root, "--json")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["issues"][0]["code"], "workflow-missing-source")
        self.assertEqual(payload["issues"][0]["severity"], "blocker")

    def test_complete_gate_enforces_prerequisite_with_exit_two(self):
        self.init()

        completed, payload = self.json_result(
            "complete-gate", self.root, "G1", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertIn("G1 requires G0", payload["error"]["message"])
        self.assertNotIn("Traceback", completed.stderr)

    def test_complete_gate_reconciles_then_persists(self):
        self.init()

        completed, payload = self.json_result(
            "complete-gate", self.root, "G0", "--json"
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["completedGates"], ["G0"])
        self.assertEqual(payload["phase"], "material-review")

    def test_set_status_persists_waiting_for_teacher(self):
        self.init()

        completed, payload = self.json_result(
            "set-status", self.root, "waiting-for-teacher", "--json"
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["status"], "waiting-for-teacher")

    def test_set_publish_status_cannot_bypass_gate(self):
        self.init()

        completed, payload = self.json_result(
            "set-status", self.root, "ready-to-publish", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires G8", payload["error"]["message"])

    def test_init_refuses_to_overwrite_existing_session(self):
        self.init()

        completed, payload = self.init()

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["error"]["code"], "workflow-blocked")

    def test_g10_cannot_be_manually_completed_without_publication_adapter(self):
        self.init()
        blueprint = self.root / ".course-work" / "course-blueprint.json"
        blueprint.write_bytes(APPROVED.read_bytes())
        for index in range(10):
            if index == 5:
                compilation = subprocess.run(
                    [sys.executable, str(COMPILER), str(self.root), "--json"],
                    cwd=REPOSITORY_ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(compilation.returncode, 0, compilation.stderr)
            completed = self.run_cli(
                "complete-gate", self.root, f"G{index}", "--json"
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

        completed, payload = self.json_result(
            "complete-gate", self.root, "G10", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("publication adapter", payload["error"]["message"])

    def test_g5_cannot_complete_without_current_compilation_outputs(self):
        self.init()
        for index in range(5):
            completed = self.run_cli(
                "complete-gate", self.root, f"G{index}", "--json"
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

        completed, payload = self.json_result(
            "complete-gate", self.root, "G5", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("compilation evidence is missing", payload["error"]["message"])

    def test_malformed_session_is_tool_error_without_traceback(self):
        work = self.root / ".course-work"
        work.mkdir()
        (work / "session.json").write_text("not json", encoding="utf-8")

        completed = self.run_cli("status", self.root)

        self.assertEqual(completed.returncode, 3)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertIn("Workflow tool error", completed.stderr)


if __name__ == "__main__":
    unittest.main()
