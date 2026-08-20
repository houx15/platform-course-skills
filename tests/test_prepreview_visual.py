import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

from course_toolkit.hashing import canonical_json_hash
from course_toolkit.instructional_audit import record_instructional_audit
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.prepreview_visual import (
    MAX_AUTONOMOUS_REPAIR_ROUNDS,
    VIEWPORT_PROFILE_MANIFEST,
    VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH,
    VISUAL_REPORT_RELATIVE_PATH,
    VisualReportError,
    _current_context_at,
    _plan_bindings,
    _replay_workflow_trace,
    _root_expected_state_specs,
    _validate_media_measurements,
    _validate_payload,
    _visual_context_hash,
    expected_visual_states,
    record_visual_report,
    verify_prepreview_visual,
)
from tests.helpers import ROOT
from tests.test_instructional_audit import _candidate as _audit_candidate
from tests.test_instructional_audit import _write_root


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


_WHITE_1440_900 = zlib.compress((b"\x00" + b"\xff\xff\xff" * 1440) * 900, 9)


def _png(index: int, *, width: int = 1440, height: int = 900) -> bytes:
    raw = _WHITE_1440_900 if (width, height) == (1440, 900) else zlib.compress((b"\x00" + b"\xff\xff\xff" * width) * height, 9)
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _png_chunk(b"tEXt", f"capture\x00{index}".encode("ascii")),
            _png_chunk(b"IDAT", raw),
            _png_chunk(b"IEND", b""),
        )
    )


class PrepreviewVisualTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        _write_root(self.root)
        record_instructional_audit(self.root, _audit_candidate(self.root))
        self.hashes, self.plan, self.course = _current_context_at(self.root)
        self.bindings = _plan_bindings(self.plan)
        self.specs = _root_expected_state_specs(self.root, self.course)
        self.payload = self._payload()

    def tearDown(self):
        self.temporary.cleanup()

    def _write_screenshot(self, index: int, *, width: int = 1440, height: int = 900) -> tuple[str, str]:
        relative = f".course-work/visual-check/screenshots/state-{index:03d}.png"
        content = _png(index, width=width, height=height)
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return relative, hashlib.sha256(content).hexdigest()

    def _trace_for_spec(self, slice_data: dict, spec: dict) -> list[dict]:
        narration_id = slice_data["narrations"][0]["id"]
        base = [
            {
                "fromStepId": "introduce",
                "eventType": "narration.ended",
                "sourceId": narration_id,
                "interactionId": None,
                "toStepId": "answer",
            }
        ]
        if spec["kind"] == "initial":
            return []
        trace = base
        if spec["eventObserved"] and spec["kind"] != "narration-complete":
            action = spec["action"]
            trace = [
                *trace,
                {
                    "fromStepId": "answer",
                    "eventType": action["eventType"],
                    "sourceId": action["sourceId"],
                    "interactionId": action["interactionId"],
                    "toStepId": "answer",
                },
            ]
        return trace

    def _state(self, spec: dict, profile: str, index: int) -> dict:
        slices = {
            (part["id"], slice_data["id"]): slice_data
            for part in self.course["course"]["parts"]
            for slice_data in part["slices"]
        }
        slice_data = slices[(spec["partId"], spec["sliceId"])]
        trace = self._trace_for_spec(slice_data, spec)
        current, visible, enabled, focus, normalized_trace = _replay_workflow_trace(slice_data, trace, path="test.workflowTrace")
        screenshot_path, screenshot_sha = self._write_screenshot(index)
        rects = []
        for block_index, block in enumerate(slice_data["blocks"]):
            block_id = block["id"]
            is_visible = block_id in visible
            rect = {
                "blockId": block_id,
                "x": 20 + block_index * 540 if is_visible else 0,
                "y": 260 if is_visible else 0,
                "width": 500 if is_visible else 0,
                "height": 320 if is_visible else 0,
                "intersectionRatio": 1.0 if is_visible else 0.0,
                "visible": is_visible,
                "clickable": block_id in enabled,
                "occluded": False,
            }
            if block["type"] in {"text", "singleChoice", "fillBlank"}:
                rect["fontSizePx"] = 18
            rects.append(rect)
        protocol = None
        if spec["protocolStage"] is not None:
            protocol = {
                "handshakeReceived": True,
                "activateReceived": spec["protocolStage"] in {"active", "completed"},
                "enableReceived": spec["protocolStage"] in {"active", "completed"},
                "completionSent": spec["protocolStage"] == "completed",
                "sessionTokenEchoed": spec["protocolStage"] == "completed",
            }
        return {
            "stateId": spec["stateId"],
            "partId": spec["partId"],
            "sliceId": spec["sliceId"],
            "subjectBlockId": spec["blockId"],
            "action": spec["action"],
            "currentStepId": current,
            "workflowTrace": normalized_trace,
            "stateMarkers": list(spec["markers"]),
            "protocolStatus": protocol,
            "viewportProfile": profile,
            "viewport": {key: copy.deepcopy(value) for key, value in VIEWPORT_PROFILE_MANIFEST[profile].items() if key != "annotationPanelCollapsed"},
            "annotationPanelCollapsed": True,
            "rectCoordinateSpace": "viewport-css-pixels",
            "screenshotPath": screenshot_path,
            "screenshotSha256": screenshot_sha,
            "visibleBlockIds": sorted(visible),
            "enabledBlockIds": sorted(enabled),
            "domRects": rects,
            "mediaMeasurements": [],
            "overflow": {"horizontal": False, "vertical": False, "clippedBlockIds": []},
            "occlusion": {"occludedBlockIds": []},
            "scroll": {"x": 0, "y": 0, "maxX": 0, "maxY": 0, "coreTaskRequiresUnexpectedScroll": False},
            "focus": {"expectedTargetId": focus, "actualTargetId": focus, "visible": focus is None or focus in visible},
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
            "planBindingIds": self.bindings[(spec["partId"], spec["sliceId"])],
            "findings": [],
        }

    def _payload(self) -> dict:
        states = []
        index = 0
        for spec in self.specs:
            for profile in ("desktop", "desktop-sidebar"):
                states.append(self._state(spec, profile, index))
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

    def _assert_invalid(self, candidate: dict, message: str) -> None:
        with self.assertRaisesRegex(VisualReportError, message):
            _validate_payload(candidate, hashes=self.hashes, plan=self.plan, course=self.course, root=self.root)

    def test_expected_states_cover_base_assessment_branches_and_final(self):
        states = list(expected_visual_states(self.course))
        self.assertEqual(len(states), 7)
        self.assertTrue(states[0].endswith("/initial"))
        self.assertTrue(any("/narration-complete:" in value for value in states))
        self.assertTrue(any("/action-ready:" in value for value in states))
        self.assertTrue(any("answer:evidence-question:correct" in value for value in states))
        self.assertTrue(any("answer:evidence-question:incorrect" in value for value in states))
        self.assertTrue(any("answer:evidence-question:attempts-exhausted" in value for value in states))
        self.assertTrue(states[-1].split("/", 2)[-1].startswith("final-pre-completion:"))

    def test_root_expands_each_video_cue_and_html_only_declared_lifecycle(self):
        course = copy.deepcopy(self.course)
        slice_data = course["course"]["parts"][0]["slices"][0]
        slice_data["blocks"].append({"id": "cue-video", "type": "video", "source": "assets/cue-video.mp4", "interaction": {"source": "interactions/video/cues.json"}, "completion": {"rule": "video-ended-and-interactions-completed"}})
        slice_data["layout"]["slots"][0]["blockIds"].append("cue-video")
        slice_data["workflow"]["initialState"]["visibleBlockIds"].append("cue-video")
        cue_path = self.root / "course/interactions/video/cues.json"
        cue_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(cue_path, {"schemaVersion": "1.1", "video": {"blockId": "cue-video", "source": "assets/cue-video.mp4", "durationSeconds": 20, "cues": [{"id": "cue-a", "atSeconds": 5, "pauseVideo": True, "required": True, "prompt": "判断", "activity": {"type": "singleChoice", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}], "assessment": {"mode": "graded", "correctOptionId": "b"}, "completion": {"rule": "submit-correct-or-exhausted", "maxAttempts": 2}}}]}})
        root_states = [spec["stateId"] for spec in _root_expected_state_specs(self.root, course)]
        self.assertIn("part-evidence-check/slice-read-and-answer/video-modal:cue-video:cue-a", root_states)
        self.assertTrue(any(value.endswith(":cue-a:correct") for value in root_states))
        self.assertTrue(any(value.endswith(":cue-a:incorrect") for value in root_states))
        self.assertTrue(any(value.endswith(":cue-a:attempts-exhausted") for value in root_states))
        branch_specs = [spec for spec in _root_expected_state_specs(self.root, course) if spec["kind"].startswith("video-modal-")]
        self.assertEqual({spec["action"]["eventType"] for spec in branch_specs}, {"answer.correct", "answer.incorrect", "answer.attemptsExhausted"})
        self.assertEqual({spec["action"]["sourceId"] for spec in branch_specs}, {"cue-a"})
        self.assertFalse(any("/video-modal:" in value for value in expected_visual_states(course)))
        document = load_json(cue_path)
        document["video"]["cues"] = []
        write_json_atomic(cue_path, document)
        self.assertFalse(any("/video-modal:" in spec["stateId"] for spec in _root_expected_state_specs(self.root, course)))

        coverage_course = load_json(ROOT / "packages/course-contract/test/fixtures/coverage-course.json")
        public_states = list(expected_visual_states(coverage_course))
        html_states = [value for value in public_states if "/html:comparison-sim:" in value]
        self.assertEqual([value.rsplit(":", 1)[-1] for value in html_states], ["ready", "active", "completed"])
        self.assertFalse(any(value.endswith(":error") for value in public_states))
        html_block = next(block for part in coverage_course["course"]["parts"] for page in part["slices"] for block in page["blocks"] if block["id"] == "comparison-sim")
        html_block.pop("completion")
        self.assertFalse(any(value.endswith(":completed") and "comparison-sim" in value for value in expected_visual_states(coverage_course)))

    def test_records_hash_bound_two_profile_evidence_and_verifies(self):
        report = record_visual_report(self.root, self.payload)
        self.assertEqual(report["schemaVersion"], "1.0")
        self.assertEqual(len(report["states"]), len(self.specs) * 2)
        self.assertEqual({item["viewportProfile"] for item in report["states"]}, {"desktop", "desktop-sidebar"})
        evidence = verify_prepreview_visual(self.root)
        self.assertEqual(evidence["courseDefinitionHash"], self.hashes["courseDefinitionHash"])
        self.assertIn("prepreviewVisualHash", evidence)
        stored = load_json(self.root / VISUAL_REPORT_RELATIVE_PATH)
        self.assertRegex(stored["reportHash"], r"^[0-9a-f]{64}$")
        ledger = load_json(self.root / VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH)
        context = ledger["contexts"][_visual_context_hash(self.hashes)]
        self.assertEqual(context["nextRepairRound"], 1)
        self.assertEqual(context["successfulReportHash"], canonical_json_hash(report))

    def test_requires_exact_reachable_trace_state_and_two_canonical_profiles(self):
        missing = copy.deepcopy(self.payload)
        missing["states"].pop()
        self._assert_invalid(missing, "both desktop viewport profiles")
        bad_profile = copy.deepcopy(self.payload)
        sidebar = next(item for item in bad_profile["states"] if item["viewportProfile"] == "desktop-sidebar")
        sidebar["viewport"]["contentRect"]["width"] = 1440
        self._assert_invalid(bad_profile, "canonical student-shell profile")
        fake_branch = copy.deepcopy(self.payload)
        branch = next(item for item in fake_branch["states"] if "/answer:" in item["stateId"])
        branch["workflowTrace"].pop()
        branch["currentStepId"] = "answer"
        self._assert_invalid(fake_branch, "does not contain the event")
        disabled = copy.deepcopy(self.payload)
        ready = next(item for item in disabled["states"] if "/action-ready:" in item["stateId"])
        ready["enabledBlockIds"] = []
        self._assert_invalid(disabled, "contradict deterministic Workflow replay")

    def test_attempt_ledger_is_monotonic_allows_three_repairs_and_rejects_round_four(self):
        for repair_round in range(MAX_AUTONOMOUS_REPAIR_ROUNDS + 1):
            candidate = copy.deepcopy(self.payload)
            candidate["repairRound"] = repair_round
            candidate["captureAvailable"] = False
            with self.assertRaisesRegex(VisualReportError, "screenshot capture"):
                record_visual_report(self.root, candidate)
        ledger = load_json(self.root / VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH)
        context = ledger["contexts"][_visual_context_hash(self.hashes)]
        self.assertEqual(context["nextRepairRound"], 4)
        self.assertEqual([item["repairRound"] for item in context["failedAttempts"]], [0, 1, 2, 3])
        fourth = copy.deepcopy(self.payload)
        fourth["repairRound"] = 4
        with self.assertRaisesRegex(VisualReportError, "fourth"):
            record_visual_report(self.root, fourth)

    def test_failed_candidate_cannot_reset_counter_and_round_one_can_succeed(self):
        failed = copy.deepcopy(self.payload)
        failed["captureAvailable"] = False
        with self.assertRaisesRegex(VisualReportError, "screenshot capture"):
            record_visual_report(self.root, failed)
        with self.assertRaisesRegex(VisualReportError, "already counted"):
            record_visual_report(self.root, failed)
        reset = copy.deepcopy(self.payload)
        reset["capturedAt"] = "2026-08-21T10:01:00Z"
        with self.assertRaisesRegex(VisualReportError, "monotonic"):
            record_visual_report(self.root, reset)
        repaired = copy.deepcopy(self.payload)
        repaired["repairRound"] = 1
        report = record_visual_report(self.root, repaired)
        self.assertEqual(report["repairRound"], 1)
        self.assertIn("prepreviewVisualHash", verify_prepreview_visual(self.root))

    def test_failed_ledger_retains_normalized_blocker_summary_without_raw_message(self):
        blocked = copy.deepcopy(self.payload)
        blocked["states"][0]["findings"] = [{"code": " INCORRECT-READING-ORDER ", "severity": "blocker", "message": "题目先于证据。", "blockIds": ["evidence-question"]}]
        blocked["blockerCount"] = 1
        with self.assertRaisesRegex(VisualReportError, "unresolved blockers"):
            record_visual_report(self.root, blocked)
        ledger = load_json(self.root / VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH)
        attempt = ledger["contexts"][_visual_context_hash(self.hashes)]["failedAttempts"][0]
        self.assertEqual(attempt["blockerCodes"], ["incorrect-reading-order"])
        self.assertNotIn("题目先于证据", json.dumps(ledger, ensure_ascii=False))

    def test_rejects_fake_truncated_wrong_size_and_changed_screenshot_bytes(self):
        fake = copy.deepcopy(self.payload)
        fake_path = self.root / fake["states"][0]["screenshotPath"]
        fake_path.write_bytes(b"\x89PNG\r\n\x1a\nvisual-evidence")
        fake["states"][0]["screenshotSha256"] = hashlib.sha256(fake_path.read_bytes()).hexdigest()
        self._assert_invalid(fake, "truncated")
        one_pixel = copy.deepcopy(self.payload)
        one_path = self.root / one_pixel["states"][0]["screenshotPath"]
        one_path.write_bytes(_png(900, width=1, height=1))
        one_pixel["states"][0]["screenshotSha256"] = hashlib.sha256(one_path.read_bytes()).hexdigest()
        self._assert_invalid(one_pixel, "unsupported")
        wrong_size = copy.deepcopy(self.payload)
        wrong_path = self.root / wrong_size["states"][0]["screenshotPath"]
        wrong_path.write_bytes(_png(901, width=1280, height=720))
        wrong_size["states"][0]["screenshotSha256"] = hashlib.sha256(wrong_path.read_bytes()).hexdigest()
        self._assert_invalid(wrong_size, "dimensions do not match")
        changed = copy.deepcopy(self.payload)
        changed_path = self.root / changed["states"][0]["screenshotPath"]
        changed_path.write_bytes(_png(902))
        self._assert_invalid(changed, "do not match")

    def test_rejects_symlink_screenshot_and_candidate(self):
        outside = self.root / "outside.png"
        outside.write_bytes(_png(999))
        target = self.root / self.payload["states"][0]["screenshotPath"]
        target.unlink()
        target.symlink_to(outside)
        self._assert_invalid(self.payload, "symlink")
        candidates = self.root / ".course-work/candidates"
        candidates.mkdir(parents=True, exist_ok=True)
        link = candidates / "visual.json"
        link.symlink_to(self.root / "outside.json")
        completed = subprocess.run(["python3", str(ROOT / "scripts/record-prepreview-visual.py"), str(self.root), ".course-work/candidates/visual.json", "--json"], cwd=ROOT, text=True, capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["error"]["code"], "candidate-symlink")

    def test_rejects_offscreen_occluded_unreadable_visual_blockers_and_downgrades(self):
        offscreen = copy.deepcopy(self.payload)
        offscreen["states"][0]["domRects"][0].update({"x": 1500, "intersectionRatio": 0})
        self._assert_invalid(offscreen, "outside the student content viewport")
        occluded = copy.deepcopy(self.payload)
        occluded["states"][0]["domRects"][0]["occluded"] = True
        self._assert_invalid(occluded, "occluded")
        unreadable = copy.deepcopy(self.payload)
        unreadable["states"][0]["domRects"][0]["fontSizePx"] = 9
        self._assert_invalid(unreadable, "readable measured font size")
        blocker = copy.deepcopy(self.payload)
        blocker["states"][0]["findings"] = [{"code": "incorrect-reading-order", "severity": "blocker", "message": "题目先于必要证据出现。", "blockIds": ["evidence-question"]}]
        blocker["blockerCount"] = 1
        self._assert_invalid(blocker, "unresolved blockers")
        downgraded = copy.deepcopy(self.payload)
        downgraded["states"][0]["findings"] = [{"code": "  INCORRECT-READING-ORDER ", "severity": " warning ", "message": "问题", "blockIds": []}]
        self._assert_invalid(downgraded, "cannot be recorded at a lower severity")
        duplicated = copy.deepcopy(self.payload)
        duplicated["states"][0]["findings"] = [{"code": "note", "severity": "warning", "message": "same  note", "blockIds": []}, {"code": " NOTE ", "severity": "warning", "message": "same note", "blockIds": []}]
        self._assert_invalid(duplicated, "duplicates")

    def test_full_report_credential_scan_catches_nonmessage_fields(self):
        leaked = copy.deepcopy(self.payload)
        leaked["states"][0]["findings"] = [{"code": "oss" + "-admin-secretvalue", "severity": "warning", "message": "需要检查", "blockIds": []}]
        self._assert_invalid(leaked, "credentials")

    def test_type_specific_media_measurements_require_readable_unstretched_surfaces(self):
        slice_data = {
            "blocks": [
                {"id": "images", "type": "images", "items": [{"id": "one"}, {"id": "two"}]},
                {"id": "pdf", "type": "pdf"},
                {"id": "video", "type": "video"},
                {"id": "html", "type": "interactiveHtml", "aspectRatio": "4:3"},
            ]
        }
        measurements = [
            {"blockId": "images", "itemId": "one", "kind": "image", "width": 320, "height": 180, "intrinsicAspectRatio": 16 / 9, "renderedAspectRatio": 16 / 9, "pdfPagePortrait": None},
            {"blockId": "images", "itemId": "two", "kind": "image", "width": 320, "height": 240, "intrinsicAspectRatio": 4 / 3, "renderedAspectRatio": 4 / 3, "pdfPagePortrait": None},
            {"blockId": "pdf", "itemId": None, "kind": "pdf", "width": 420, "height": 594, "intrinsicAspectRatio": 420 / 594, "renderedAspectRatio": 420 / 594, "pdfPagePortrait": True},
            {"blockId": "video", "itemId": None, "kind": "video", "width": 640, "height": 360, "intrinsicAspectRatio": 16 / 9, "renderedAspectRatio": 16 / 9, "pdfPagePortrait": None},
            {"blockId": "html", "itemId": None, "kind": "interactiveHtml", "width": 640, "height": 480, "intrinsicAspectRatio": 4 / 3, "renderedAspectRatio": 4 / 3, "pdfPagePortrait": None},
        ]
        normalized = _validate_media_measurements(measurements, slice_data=slice_data, visible={"images", "pdf", "video", "html"}, path="measurements")
        self.assertEqual(len(normalized), 5)
        distorted_pdf = copy.deepcopy(measurements)
        distorted_pdf[2]["renderedAspectRatio"] = 1.2
        with self.assertRaisesRegex(VisualReportError, "portrait page/viewer"):
            _validate_media_measurements(distorted_pdf, slice_data=slice_data, visible={"images", "pdf", "video", "html"}, path="measurements")
        missing_image = copy.deepcopy(measurements)
        missing_image.pop(1)
        with self.assertRaisesRegex(VisualReportError, "every visible media surface"):
            _validate_media_measurements(missing_image, slice_data=slice_data, visible={"images", "pdf", "video", "html"}, path="measurements")

    def test_rejects_stale_artifacts_and_tampered_report_or_ledger(self):
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
        write_json_atomic(self.root / VISUAL_REPORT_RELATIVE_PATH, {**self.payload, "reportHash": canonical_json_hash(self.payload)})
        ledger = load_json(self.root / VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH)
        ledger["contexts"][_visual_context_hash(self.hashes)]["successfulReportHash"] = "0" * 64
        write_json_atomic(self.root / VISUAL_ATTEMPT_LEDGER_RELATIVE_PATH, ledger)
        with self.assertRaisesRegex(VisualReportError, "outside its atomic commit"):
            verify_prepreview_visual(self.root)

    def test_invalid_cli_candidate_does_not_replace_existing_report(self):
        record_visual_report(self.root, self.payload)
        report_path = self.root / VISUAL_REPORT_RELATIVE_PATH
        before = report_path.read_bytes()
        candidate_path = self.root / ".course-work/candidates/visual.json"
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        invalid = copy.deepcopy(self.payload)
        invalid["repairRound"] = 4
        write_json_atomic(candidate_path, invalid)
        completed = subprocess.run(["python3", str(ROOT / "scripts/record-prepreview-visual.py"), str(self.root), ".course-work/candidates/visual.json", "--json"], cwd=ROOT, text=True, capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["error"]["code"], "repair-limit-exceeded")
        self.assertEqual(report_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
