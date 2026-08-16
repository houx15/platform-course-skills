import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT


SCRIPT = ROOT / "scripts" / "validate-video-interaction.ts"


def owner():
    return {
        "id": "case-video",
        "type": "video",
        "source": "assets/videos/case.mp4",
        "durationSeconds": 90,
        "interaction": {"source": "interactions/video/case-video.json"},
        "completion": {"rule": "video-ended-and-interactions-completed"},
    }


def document():
    cue = {
        "id": "prediction-check",
        "atSeconds": 42,
        "pauseVideo": True,
        "required": True,
        "prompt": "What do you predict?",
        "activity": {
            "type": "singleChoice",
            "options": [
                {"id": "same", "label": "Same"},
                {"id": "different", "label": "Different"},
            ],
            "assessment": {"mode": "survey"},
            "completion": {"rule": "submit-any"},
        },
    }
    return {
        "schemaVersion": "1.1",
        "video": {
            "blockId": "case-video",
            "source": "assets/videos/case.mp4",
            "durationSeconds": 90,
            "cues": [cue],
        },
    }


def run_bridge(doc, owning_block):
    with tempfile.TemporaryDirectory() as temporary:
        temporary_root = Path(temporary)
        document_path = temporary_root / "interaction.json"
        owner_path = temporary_root / "owner.json"
        document_path.write_text(json.dumps(doc), encoding="utf-8")
        owner_path.write_text(json.dumps(owning_block), encoding="utf-8")
        return subprocess.run(
            [
                "node",
                "--import",
                "tsx",
                str(SCRIPT),
                str(document_path),
                str(owner_path),
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )


class SharedVideoInteractionContractTests(unittest.TestCase):
    def test_valid_document_passes_with_summary(self):
        completed = run_bridge(document(), owner())

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["cueCount"], 1)
        self.assertEqual(payload["durationSeconds"], 90)

    def test_structural_issue_preserves_order_path_and_layer(self):
        broken = document()
        broken["schemaVersion"] = "1.0"
        broken["unexpected"] = True

        completed = run_bridge(broken, owner())

        self.assertEqual(completed.returncode, 2)
        issues = json.loads(completed.stdout)["issues"]
        self.assertEqual(issues[0]["layer"], "structural")
        self.assertEqual(issues[0]["path"], "schemaVersion")
        self.assertEqual(issues[1]["path"], "")

    def test_referential_mismatch_is_returned(self):
        broken = document()
        broken["video"]["blockId"] = "other-video"

        completed = run_bridge(broken, owner())

        self.assertEqual(completed.returncode, 2)
        issue = json.loads(completed.stdout)["issues"][0]
        self.assertEqual(issue["layer"], "referential")
        self.assertEqual(issue["path"], "video.blockId")

    def test_duplicate_and_non_increasing_cues_are_both_reported(self):
        broken = document()
        duplicate = copy.deepcopy(broken["video"]["cues"][0])
        duplicate["atSeconds"] = 42
        broken["video"]["cues"].append(duplicate)

        completed = run_bridge(broken, owner())

        messages = [
            issue["message"] for issue in json.loads(completed.stdout)["issues"]
        ]
        self.assertEqual(completed.returncode, 2)
        self.assertTrue(any("duplicate cue id" in message for message in messages))
        self.assertTrue(any("strictly increasing" in message for message in messages))

    def test_out_of_duration_cue_is_rejected(self):
        broken = document()
        broken["video"]["cues"][0]["atSeconds"] = 91

        completed = run_bridge(broken, owner())

        self.assertEqual(completed.returncode, 2)
        self.assertIn("beyond the video duration", completed.stdout)

    def test_bad_json_is_tool_failure_without_stack_trace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document_path = root / "interaction.json"
            owner_path = root / "owner.json"
            document_path.write_text("not json", encoding="utf-8")
            owner_path.write_text(json.dumps(owner()), encoding="utf-8")
            completed = subprocess.run(
                [
                    "node",
                    "--import",
                    "tsx",
                    str(SCRIPT),
                    str(document_path),
                    str(owner_path),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 3)
        self.assertNotIn(" at ", completed.stderr)
        self.assertNotIn("stack", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
