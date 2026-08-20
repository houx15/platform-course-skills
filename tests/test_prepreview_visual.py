import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from course_toolkit.instructional_audit import record_instructional_audit
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.prepreview_visual import (
    MAX_AUTONOMOUS_REPAIR_ROUNDS,
    VISUAL_REPORT_RELATIVE_PATH,
    VisualReportError,
    _current_context_at,
    _plan_bindings,
    expected_visual_states,
    record_visual_report,
    verify_prepreview_visual,
)
from tests.helpers import ROOT
from tests.test_instructional_audit import _candidate as _audit_candidate
from tests.test_instructional_audit import _write_root


PNG = b"\x89PNG\r\n\x1a\n" + b"visual-evidence"


class PrepreviewVisualTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        _write_root(self.root)
        record_instructional_audit(self.root, _audit_candidate(self.root))
        self.hashes, self.plan, self.course = _current_context_at(self.root)
        self.bindings = _plan_bindings(self.plan)
        self.payload = self._payload()

    def tearDown(self):
        self.temporary.cleanup()

    def _write_screenshot(self, index: int) -> tuple[str, str]:
        relative = f".course-work/visual-check/screenshots/state-{index:03d}.png"
        content = PNG + str(index).encode("ascii")
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return relative, hashlib.sha256(content).hexdigest()

    def _payload(self) -> dict:
        state_ids = expected_visual_states(self.course)
        slices = {
            (part["id"], slice_data["id"]): slice_data
            for part in self.course["course"]["parts"]
            for slice_data in part["slices"]
        }
        states = []
        index = 0
        for state_id in state_ids:
            part_id, slice_id, _kind = state_id.split("/", 2)
            slice_data = slices[(part_id, slice_id)]
            block_ids = [block["id"] for block in slice_data["blocks"]]
            block_types = {block["id"]: block["type"] for block in slice_data["blocks"]}
            for profile, content_width in (("desktop", 1320), ("desktop-sidebar", 1040)):
                screenshot_path, screenshot_sha = self._write_screenshot(index)
                rects = []
                for block_index, block_id in enumerate(block_ids):
                    rect = {
                        "blockId": block_id,
                        "x": 20 + block_index * (620 if profile == "desktop" else 480),
                        "y": 120,
                        "width": 560 if profile == "desktop" else 430,
                        "height": 360,
                        "intersectionRatio": 1.0,
                        "visible": True,
                        "clickable": True,
                        "occluded": False,
                    }
                    if block_types[block_id] in {"text", "singleChoice", "fillBlank"}:
                        rect["fontSizePx"] = 16
                    rects.append(rect)
                states.append(
                    {
                        "stateId": state_id,
                        "partId": part_id,
                        "sliceId": slice_id,
                        "viewportProfile": profile,
                        "viewport": {"width": 1440, "height": 900, "contentWidth": content_width, "contentHeight": 800},
                        "screenshotPath": screenshot_path,
                        "screenshotSha256": screenshot_sha,
                        "visibleBlockIds": block_ids,
                        "enabledBlockIds": (
                            slice_data["workflow"].get("initialState", {}).get("enabledBlockIds", block_ids)
                            if state_id.endswith("/initial")
                            else [block_id for block_id in block_ids if block_types[block_id] in {"singleChoice", "fillBlank", "video", "interactiveHtml"}]
                        ),
                        "domRects": rects,
                        "overflow": {"horizontal": False, "vertical": False, "clippedBlockIds": []},
                        "occlusion": {"occludedBlockIds": []},
                        "scroll": {"x": 0, "y": 0, "maxX": 0, "maxY": 0, "coreTaskRequiresUnexpectedScroll": False},
                        "focus": {"expectedTargetId": None, "actualTargetId": None, "visible": True},
                        "layout": {
                            "emptySlotIds": [],
                            "deadRegionRatio": 0.08,
                            "unreadableBlockIds": [],
                            "aspectDistortedBlockIds": [],
                            "readingOrderMatchesPlan": True,
                            "coVisibilitySatisfied": True,
                            "planMatchesScreenshot": True,
                            "unreachableBlockIds": [],
                        },
                        "runtimeErrors": [],
                        "planBindingIds": self.bindings[(part_id, slice_id)],
                        "findings": [],
                    }
                )
                index += 1
        return {
            "schemaVersion": "1.0",
            "artifactHashes": self.hashes,
            "captureAvailable": True,
            "repairRound": 0,
            "capturedAt": "2026-08-21T10:00:00Z",
            "states": states,
            "blockerCount": 0,
        }

    def test_expected_states_cover_base_assessment_branches_and_final(self):
        states = list(expected_visual_states(self.course))
        self.assertEqual(len(states), 7)
        self.assertTrue(states[0].endswith("/initial"))
        self.assertTrue(any(value.endswith("/narration-complete") for value in states))
        self.assertTrue(any(value.endswith("/action-ready") for value in states))
        self.assertTrue(any("answer:evidence-question:correct" in value for value in states))
        self.assertTrue(any("answer:evidence-question:incorrect" in value for value in states))
        self.assertTrue(any("answer:evidence-question:attempts-exhausted" in value for value in states))
        self.assertTrue(states[-1].endswith("/final-pre-completion"))

    def test_expected_states_cover_video_modals_and_html_lifecycle(self):
        coverage_course = load_json(ROOT / "packages/course-contract/test/fixtures/coverage-course.json")
        states = list(expected_visual_states(coverage_course))
        self.assertTrue(any("/video-modal:" in value for value in states))
        html_states = [value for value in states if "/html:comparison-sim:" in value]
        self.assertEqual(
            [value.rsplit(":", 1)[-1] for value in html_states],
            ["ready", "active", "completed", "error"],
        )

    def test_records_hash_bound_two_profile_evidence_and_verifies(self):
        report = record_visual_report(self.root, self.payload)

        self.assertEqual(report["schemaVersion"], "1.0")
        self.assertEqual(len(report["states"]), len(expected_visual_states(self.course)) * 2)
        self.assertEqual({item["viewportProfile"] for item in report["states"]}, {"desktop", "desktop-sidebar"})
        evidence = verify_prepreview_visual(self.root)
        self.assertEqual(evidence["courseDefinitionHash"], self.hashes["courseDefinitionHash"])
        self.assertIn("prepreviewVisualHash", evidence)
        stored = load_json(self.root / VISUAL_REPORT_RELATIVE_PATH)
        self.assertRegex(stored["reportHash"], r"^[0-9a-f]{64}$")

    def test_requires_every_state_and_both_student_shell_widths(self):
        missing = copy.deepcopy(self.payload)
        missing["states"].pop()
        with self.assertRaisesRegex(VisualReportError, "both desktop viewport profiles"):
            record_visual_report(self.root, missing)

        bad_width = copy.deepcopy(self.payload)
        sidebar = next(item for item in bad_width["states"] if item["viewportProfile"] == "desktop-sidebar")
        sidebar["viewport"]["contentWidth"] = 1320
        with self.assertRaisesRegex(VisualReportError, "narrower student content width"):
            record_visual_report(self.root, bad_width)

    def test_rejects_capture_unavailable_runtime_error_and_fourth_repair(self):
        for mutation, message in (
            (lambda value: value.update({"captureAvailable": False}), "screenshot capture"),
            (lambda value: value["states"][0].update({"runtimeErrors": ["renderer crashed"]}), "runtime error"),
            (lambda value: value.update({"repairRound": MAX_AUTONOMOUS_REPAIR_ROUNDS + 1}), "fourth"),
        ):
            candidate = copy.deepcopy(self.payload)
            mutation(candidate)
            with self.subTest(message=message), self.assertRaisesRegex(VisualReportError, message):
                record_visual_report(self.root, candidate)

    def test_rejects_missing_invalid_and_changed_screenshot_bytes(self):
        for mutate, message in (
            (lambda state: state.update({"screenshotSha256": "nope"}), "lowercase SHA-256"),
            (lambda state: state.update({"screenshotPath": ".course-work/visual-check/missing.png"}), "below .course-work/visual-check/screenshots"),
        ):
            candidate = copy.deepcopy(self.payload)
            mutate(candidate["states"][0])
            with self.subTest(message=message), self.assertRaisesRegex(VisualReportError, message):
                record_visual_report(self.root, candidate)

        changed = copy.deepcopy(self.payload)
        (self.root / changed["states"][0]["screenshotPath"]).write_bytes(PNG + b"changed")
        with self.assertRaisesRegex(VisualReportError, "do not match"):
            record_visual_report(self.root, changed)

    def test_rejects_symlink_screenshot_and_candidate(self):
        outside = self.root / "outside.png"
        outside.write_bytes(PNG)
        target = self.root / self.payload["states"][0]["screenshotPath"]
        target.unlink()
        target.symlink_to(outside)
        with self.assertRaisesRegex(VisualReportError, "symlink"):
            record_visual_report(self.root, self.payload)

        candidates = self.root / ".course-work/candidates"
        candidates.mkdir(parents=True, exist_ok=True)
        link = candidates / "visual.json"
        link.symlink_to(self.root / "outside.json")
        completed = subprocess.run(
            ["python3", str(ROOT / "scripts/record-prepreview-visual.py"), str(self.root), ".course-work/candidates/visual.json", "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["error"]["code"], "candidate-symlink")

    def test_rejects_offscreen_occluded_unreadable_and_visual_blocker(self):
        cases = []
        offscreen = copy.deepcopy(self.payload)
        offscreen["states"][0]["domRects"][0]["x"] = offscreen["states"][0]["viewport"]["contentWidth"] + 1
        offscreen["states"][0]["domRects"][0]["intersectionRatio"] = 0
        cases.append((offscreen, "outside the student content viewport"))
        occluded = copy.deepcopy(self.payload)
        occluded["states"][0]["domRects"][0]["occluded"] = True
        cases.append((occluded, "occluded"))
        unreadable = copy.deepcopy(self.payload)
        unreadable["states"][0]["domRects"][0]["fontSizePx"] = 9
        cases.append((unreadable, "too small"))
        blocker = copy.deepcopy(self.payload)
        blocker["states"][0]["findings"] = [{"code": "incorrect-reading-order", "severity": "blocker", "message": "题目先于必要证据出现。", "blockIds": ["evidence-question"]}]
        blocker["blockerCount"] = 1
        cases.append((blocker, "unresolved blockers"))
        for candidate, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(VisualReportError, message):
                record_visual_report(self.root, candidate)

    def test_rejects_stale_artifacts_and_tampered_commit(self):
        record_visual_report(self.root, self.payload)
        stale = copy.deepcopy(self.payload)
        stale["artifactHashes"]["rendererHash"] = "0" * 64
        with self.assertRaisesRegex(VisualReportError, "do not match"):
            record_visual_report(self.root, stale)

        stored = load_json(self.root / VISUAL_REPORT_RELATIVE_PATH)
        stored["capturedAt"] = "changed"
        write_json_atomic(self.root / VISUAL_REPORT_RELATIVE_PATH, stored)
        with self.assertRaisesRegex(VisualReportError, "outside its atomic commit"):
            verify_prepreview_visual(self.root)

    def test_invalid_candidate_does_not_replace_an_existing_report(self):
        record_visual_report(self.root, self.payload)
        report_path = self.root / VISUAL_REPORT_RELATIVE_PATH
        before = report_path.read_bytes()
        candidate_path = self.root / ".course-work/candidates/visual.json"
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        invalid = copy.deepcopy(self.payload)
        invalid["repairRound"] = 4
        write_json_atomic(candidate_path, invalid)

        completed = subprocess.run(
            ["python3", str(ROOT / "scripts/record-prepreview-visual.py"), str(self.root), ".course-work/candidates/visual.json", "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["error"]["code"], "repair-limit-exceeded")
        self.assertEqual(report_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
