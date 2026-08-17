import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT


INSTALLER = ROOT / "scripts" / "install-skills.py"
GOLDEN = ROOT / "packages" / "course-contract" / "test" / "fixtures" / "coverage-course.json"


class RuntimeBundleTests(unittest.TestCase):
    def install_runtime(self, home: Path) -> Path:
        result = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--home",
                str(home),
                "--target",
                "codex",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return home / ".codex" / "skills" / "_course-toolkit" / "course_toolkit" / "runtime_dist"

    def test_installed_course_validator_runs_without_repository_node_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.install_runtime(Path(tmp))
            result = subprocess.run(
                ["node", str(runtime / "validate-course-definition.mjs"), str(GOLDEN), "--json"],
                cwd=Path(tmp),
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_installed_video_validator_runs_without_repository_node_modules(self):
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        owner = golden["course"]["parts"][0]["slices"][0]["blocks"][0]
        interaction = {
            "schemaVersion": "1.1",
            "video": {
                "blockId": owner["id"],
                "source": owner["source"],
                "durationSeconds": owner["durationSeconds"],
                "cues": [],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            runtime = self.install_runtime(temporary)
            owner_path = temporary / "owner.json"
            interaction_path = temporary / "interaction.json"
            owner_path.write_text(json.dumps(owner), encoding="utf-8")
            interaction_path.write_text(json.dumps(interaction), encoding="utf-8")
            result = subprocess.run(
                [
                    "node",
                    str(runtime / "validate-video-interaction.mjs"),
                    str(interaction_path),
                    str(owner_path),
                    "--json",
                ],
                cwd=temporary,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
