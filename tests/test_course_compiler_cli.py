import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_compiler import (
    compile_blueprint,
    write_compilation_outputs_atomic,
)
from course_toolkit.jsonio import load_json, write_json_atomic
from tests.helpers import ROOT


SCRIPT = ROOT / "scripts" / "compile-course.py"
APPROVED = ROOT / "tests" / "fixtures" / "course-blueprint" / "approved-blueprint.json"


class CourseCompilerCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "course-project"
        self.blueprint_path = self.root / ".course-work" / "course-blueprint.json"
        self.blueprint_path.parent.mkdir(parents=True)
        self.blueprint_path.write_bytes(APPROVED.read_bytes())

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.root), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    @property
    def outputs(self):
        return (
            self.root / "course" / "course.json",
            self.root / ".course-work" / "course-runtime-source-map.json",
            self.root / ".course-work" / "compilation-report.json",
        )

    def test_success_writes_complete_compilation_set(self):
        completed = self.run_cli()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "compiled")
        self.assertEqual(payload["assetPaths"], ["assets/audio/introduce-check.mp3"])
        self.assertTrue(all(path.is_file() for path in self.outputs))
        self.assertEqual(load_json(self.outputs[0])["schemaVersion"], "2.0")

    def test_blocked_recompile_preserves_previous_complete_set(self):
        first = self.run_cli()
        self.assertEqual(first.returncode, 0, first.stderr)
        before = tuple(path.read_bytes() for path in self.outputs)
        blueprint = load_json(self.blueprint_path)
        blueprint["course"]["parts"][0]["slices"][0]["layout"]["slots"] = []
        write_json_atomic(self.blueprint_path, blueprint)

        completed = self.run_cli()

        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["error"]["code"], "compilation-blocked")
        self.assertIn("course-contract-invalid", {item["code"] for item in payload["issues"]})
        self.assertEqual(tuple(path.read_bytes() for path in self.outputs), before)

    def test_malformed_blueprint_is_tool_failure_without_traceback(self):
        self.blueprint_path.write_text("not json", encoding="utf-8")

        completed = self.run_cli()

        self.assertEqual(completed.returncode, 3)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["error"]["code"], "tool-error")
        self.assertNotIn("Traceback", completed.stderr)

    def test_atomic_writer_rolls_back_if_a_final_replace_fails(self):
        result = compile_blueprint(load_json(self.blueprint_path))
        for index, path in enumerate(self.outputs):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"previous-{index}", encoding="utf-8")
        before = tuple(path.read_bytes() for path in self.outputs)

        def fail_on_source_map(source, destination):
            source_path = Path(source)
            destination_path = Path(destination)
            if (
                destination_path.name == "course-runtime-source-map.json"
                and source_path.name.endswith(".tmp")
            ):
                raise OSError("simulated replace failure")
            os.replace(source, destination)

        with self.assertRaisesRegex(OSError, "simulated replace failure"):
            write_compilation_outputs_atomic(
                self.root,
                result,
                replace=fail_on_source_map,
            )

        self.assertEqual(tuple(path.read_bytes() for path in self.outputs), before)
        leftovers = [
            path
            for parent in {path.parent for path in self.outputs}
            for path in parent.iterdir()
            if path.name.endswith((".tmp", ".bak"))
        ]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
