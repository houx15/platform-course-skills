import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_package_validation import (
    VALIDATION_REPORT_RELATIVE_PATH,
    build_course_validation_report,
    iter_asset_references,
    sync_validation_issues,
    validate_asset_references,
    write_current_validation_report,
)
from course_toolkit.course_compiler import compile_blueprint, write_compilation_outputs_atomic
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.issues import IssueStore, make_registered_issue
from tests.helpers import ROOT, write_test_mp4, write_test_pdf
from tests.test_html_validation import VALID_HTML, VALID_HTML_V2


BASE = (
    ROOT
    / "tests"
    / "fixtures"
    / "course-blueprint"
    / "expected-course-definition.json"
)


def full_asset_document():
    data = load_json(BASE)
    course = data["course"]
    course["opening"]["fallback"]["audio"] = "assets/audio/open.mp3"
    course["closing"]["fallback"]["audio"] = "assets/audio/close.mp3"
    slice_data = course["parts"][0]["slices"][0]
    slice_data["blocks"].extend(
        [
            {
                "id": "diagram",
                "type": "images",
                "presentation": "single",
                "items": [
                    {
                        "id": "diagram-item",
                        "source": "assets/images/diagram.png",
                        "alt": "Diagram",
                    }
                ],
            },
            {
                "id": "source-paper",
                "type": "pdf",
                "title": "Source paper",
                "source": "assets/pdfs/source.pdf",
            },
            {
                "id": "case-video",
                "type": "video",
                "source": "assets/videos/case.mp4",
                "poster": "assets/images/case-poster.jpg",
                "captions": "assets/captions/case.en.vtt",
                "interaction": {"source": "interactions/video/case.json"},
            },
            {
                "id": "simulation",
                "type": "interactiveHtml",
                "source": "interactions/html/simulation.html",
                "protocolVersion": "1.0",
                "aspectRatio": "4:3",
            },
        ]
    )
    slice_data["layout"] = {
        "preset": "full",
        "slots": [
            {"id": "main", "blockIds": [block["id"] for block in slice_data["blocks"]]}
        ],
    }
    return data


EXPECTED = {
    "assets/audio/open.mp3",
    "assets/audio/close.mp3",
    "assets/audio/introduce-check.mp3",
    "assets/images/diagram.png",
    "assets/pdfs/source.pdf",
    "assets/videos/case.mp4",
    "assets/images/case-poster.jpg",
    "assets/captions/case.en.vtt",
    "interactions/video/case.json",
    "interactions/html/simulation.html",
}


class CoursePackageAssetTests(unittest.TestCase):
    def test_index_covers_every_asset_bearing_contract_field(self):
        references = list(iter_asset_references(full_asset_document()))

        self.assertEqual({reference.source for reference in references}, EXPECTED)
        self.assertEqual(
            {reference.role for reference in references},
            {
                "opening-audio",
                "closing-audio",
                "narration-audio",
                "image",
                "pdf",
                "video",
                "video-poster",
                "captions",
                "video-interaction",
                "interactive-html",
            },
        )
        video = next(item for item in references if item.role == "video")
        self.assertEqual(video.block_id, "case-video")
        self.assertEqual(video.slice_id, "slice-read-and-answer")
        self.assertIn("blocks[4].source", video.runtime_path)

    def test_complete_safe_inventory_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for raw in EXPECTED:
                path = root / raw
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"asset")
            result = validate_asset_references(
                root,
                full_asset_document(),
                sorted(EXPECTED),
            )

        self.assertEqual(result.issues, ())
        self.assertEqual([item.source for item in result.references], [
            item.source for item in iter_asset_references(full_asset_document())
        ])

    def test_tts_output_paths_are_validated_but_not_required_as_local_assets(self):
        data = full_asset_document()
        delivery_assets = sorted(
            source for source in EXPECTED if not source.startswith("assets/audio/")
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for raw in delivery_assets:
                path = root / raw
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"asset")

            result = validate_asset_references(root, data, delivery_assets)

        self.assertEqual(result.issues, ())

    def test_missing_file_and_inventory_drift_are_distinct(self):
        data = full_asset_document()
        with tempfile.TemporaryDirectory() as temporary:
            result = validate_asset_references(
                Path(temporary),
                data,
                ["assets/unowned.bin", *sorted(EXPECTED - {"assets/images/diagram.png"})],
            )

        codes = [issue.code for issue in result.issues]
        self.assertIn("missing-asset", codes)
        self.assertEqual(codes.count("asset-inventory-mismatch"), 2)

    def test_unsafe_absolute_parent_and_backslash_paths_are_rejected(self):
        for source in ("/tmp/file.pdf", "../file.pdf", "assets\\file.pdf"):
            with self.subTest(source=source):
                data = full_asset_document()
                data["course"]["parts"][0]["slices"][0]["blocks"][3][
                    "source"
                ] = source
                with tempfile.TemporaryDirectory() as temporary:
                    result = validate_asset_references(Path(temporary), data, [])
                self.assertIn("unsafe-asset-path", {i.code for i in result.issues})

    def test_symlink_traversal_is_rejected_even_when_target_stays_inside_root(self):
        data = full_asset_document()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            (root / "assets").symlink_to(real, target_is_directory=True)

            result = validate_asset_references(root, data, sorted(EXPECTED))

        self.assertIn("symlink-asset-path", {issue.code for issue in result.issues})

    def test_case_mismatch_is_reported_deterministically(self):
        data = full_asset_document()
        source = "assets/images/diagram.png"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "assets" / "images" / "Diagram.PNG"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"image")

            result = validate_asset_references(root, data, sorted(EXPECTED))

        matching = [
            issue
            for issue in result.issues
            if issue.path.endswith("blocks[2].items[0].source")
        ]
        self.assertEqual(matching[0].code, "asset-case-mismatch")

    def test_role_extension_mismatch_is_rejected(self):
        data = full_asset_document()
        data["course"]["parts"][0]["slices"][0]["blocks"][3][
            "source"
        ] = "assets/pdfs/source.txt"

        with tempfile.TemporaryDirectory() as temporary:
            result = validate_asset_references(Path(temporary), data, [])

        self.assertIn("asset-extension-mismatch", {i.code for i in result.issues})


def video_interaction_document():
    return {
        "schemaVersion": "1.1",
        "video": {
            "blockId": "case-video",
            "source": "assets/videos/case.mp4",
            "durationSeconds": 32.533333,
            "cues": [
                {
                    "id": "prediction-check",
                    "atSeconds": 10,
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
            ],
        },
    }


def build_full_package(root: Path):
    document = full_asset_document()
    video = next(
        block
        for block in document["course"]["parts"][0]["slices"][0]["blocks"]
        if block["id"] == "case-video"
    )
    video["durationSeconds"] = 32.533333
    video["completion"] = {"rule": "video-ended-and-interactions-completed"}
    blueprint = load_json(
        ROOT
        / "tests"
        / "fixtures"
        / "course-blueprint"
        / "approved-blueprint.json"
    )
    blueprint["course"] = document["course"]
    write_json_atomic(root / ".course-work/course-blueprint.json", blueprint)
    result = compile_blueprint(blueprint)
    write_compilation_outputs_atomic(root, result)

    for source in (
        "assets/images/diagram.png",
        "assets/images/case-poster.jpg",
    ):
        path = root / "course" / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.encode("utf-8"))
    write_test_pdf(root / "course/assets/pdfs/source.pdf")
    write_test_mp4(root / "course/assets/videos/case.mp4")
    captions = root / "course/assets/captions/case.en.vtt"
    captions.parent.mkdir(parents=True, exist_ok=True)
    captions.write_text("WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n", encoding="utf-8")
    interaction = root / "course/interactions/video/case.json"
    interaction.parent.mkdir(parents=True, exist_ok=True)
    interaction.write_text(
        json.dumps(video_interaction_document()),
        encoding="utf-8",
    )
    html = root / "course/interactions/html/simulation.html"
    html.parent.mkdir(parents=True, exist_ok=True)
    html.write_text(VALID_HTML_V2, encoding="utf-8")
    return result


def build_minimal_package(root: Path):
    blueprint = load_json(
        ROOT
        / "tests"
        / "fixtures"
        / "course-blueprint"
        / "approved-blueprint.json"
    )
    write_json_atomic(root / ".course-work/course-blueprint.json", blueprint)
    result = compile_blueprint(blueprint)
    write_compilation_outputs_atomic(root, result)
    return result


class CourseDefinitionTwoValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.compilation = build_full_package(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def codes(self, key="issues"):
        return {
            finding["code"]
            for finding in build_course_validation_report(self.root)[key]
        }

    def test_valid_full_package_has_only_fixed_dense_slice_warning(self):
        report = build_course_validation_report(self.root)

        self.assertEqual(report["status"], "warnings")
        self.assertEqual(report["issues"], [])
        self.assertEqual(
            {item["code"] for item in report["warnings"]},
            {"dense-slice"},
        )
        self.assertEqual(report["summary"]["partCount"], 1)
        self.assertEqual(report["summary"]["sliceCount"], 1)
        self.assertEqual(report["summary"]["blockCount"], 6)
        self.assertEqual(report["summary"]["assetCount"], 7)
        self.assertEqual(len(report["assets"]), 7)
        video = report["mediaEvidence"]["videos"][0]
        self.assertEqual(video["cueCount"], 1)
        self.assertEqual(video["requiredCueCount"], 1)
        self.assertEqual(video["autoPauseCueCount"], 1)

    def test_validation_report_is_deterministic(self):
        first = build_course_validation_report(self.root)
        second = build_course_validation_report(self.root)

        self.assertEqual(first, second)
        self.assertNotIn("timestamp", json.dumps(first))

    def test_report_keeps_existing_findings_and_adds_instructional_layers(self):
        report = build_course_validation_report(self.root)

        self.assertEqual(
            set(report["layers"]),
            {"instructionalBinding", "planCorrespondence", "layoutWorkflow"},
        )
        self.assertEqual(report["layers"]["instructionalBinding"]["status"], "not-applicable")
        self.assertEqual(report["layers"]["planCorrespondence"]["status"], "not-applicable")
        self.assertEqual(report["layers"]["layoutWorkflow"]["issues"], [])

    def test_report_is_independent_of_absolute_course_root(self):
        first = build_course_validation_report(self.root)
        with tempfile.TemporaryDirectory() as temporary:
            other = Path(temporary)
            build_full_package(other)
            second = build_course_validation_report(other)

        self.assertEqual(first, second)

    def test_pdf_signature_and_caption_header_are_required(self):
        (self.root / "course/assets/pdfs/source.pdf").write_bytes(b"not pdf")
        (self.root / "course/assets/captions/case.en.vtt").write_text(
            "not vtt", encoding="utf-8"
        )

        codes = self.codes()

        self.assertIn("invalid-pdf-header", codes)
        self.assertIn("invalid-pdf-eof", codes)
        self.assertIn("invalid-webvtt", codes)

    def test_video_profile_and_declared_duration_are_checked(self):
        write_test_mp4(
            self.root / "course/assets/videos/case.mp4",
            video_codec=b"vp09",
            faststart=False,
        )

        codes = self.codes()

        self.assertIn("unsupported-video-codec", codes)
        self.assertIn("missing-faststart", codes)

    def test_shared_video_interaction_and_actual_timing_are_checked(self):
        path = self.root / "course/interactions/video/case.json"
        data = load_json(path)
        duplicate = copy.deepcopy(data["video"]["cues"][0])
        duplicate["atSeconds"] = 10
        data["video"]["cues"].append(duplicate)
        path.write_text(json.dumps(data), encoding="utf-8")

        self.assertIn("video-interaction-contract-invalid", self.codes())

    def test_required_cues_require_combined_video_completion(self):
        document_path = self.root / "course" / "course.json"
        document = load_json(document_path)
        video = next(
            block
            for block in document["course"]["parts"][0]["slices"][0]["blocks"]
            if block["id"] == "case-video"
        )
        video["completion"] = {"rule": "video-ended"}
        # Rebuild a self-consistent G5 set so this test reaches media semantics.
        blueprint_path = self.root / ".course-work" / "course-blueprint.json"
        blueprint = load_json(blueprint_path)
        blueprint["course"] = document["course"]
        write_json_atomic(blueprint_path, blueprint)
        write_compilation_outputs_atomic(self.root, compile_blueprint(blueprint))

        self.assertIn("video-completion-inconsistent", self.codes())

    def test_estimated_time_drift_is_a_fixed_warning(self):
        blueprint_path = self.root / ".course-work/course-blueprint.json"
        blueprint = load_json(blueprint_path)
        blueprint["course"]["estimatedMinutes"] = 10
        write_json_atomic(blueprint_path, blueprint)
        write_compilation_outputs_atomic(self.root, compile_blueprint(blueprint))

        self.assertIn("estimated-time-drift", self.codes("warnings"))

    def test_g6_blocks_a_split_layout_with_an_empty_slot(self):
        blueprint_path = self.root / ".course-work/course-blueprint.json"
        blueprint = load_json(blueprint_path)
        slice_data = blueprint["course"]["parts"][0]["slices"][0]
        block_ids = [block["id"] for block in slice_data["blocks"]]
        slice_data["layout"] = {
            "preset": "split-horizontal",
            "ratio": "3:1",
            "slots": [
                {"id": "left", "blockIds": block_ids},
                {"id": "right", "blockIds": []},
            ],
        }
        write_json_atomic(blueprint_path, blueprint)
        write_compilation_outputs_atomic(self.root, compile_blueprint(blueprint))

        report = build_course_validation_report(self.root)

        self.assertEqual(report["status"], "blocked")
        self.assertIn("layout-empty-slot", self.codes())

    def test_legacy_html_protocol_is_blocked(self):
        (self.root / "course/interactions/html/simulation.html").write_text(
            VALID_HTML,
            encoding="utf-8",
        )

        codes = self.codes()

        self.assertIn("missing-host-handshake", codes)
        self.assertIn("missing-completion-evidence", codes)

    def test_blocked_attempt_does_not_replace_previous_current_report(self):
        first = build_course_validation_report(self.root)
        write_current_validation_report(self.root, first)
        current_path = self.root / VALIDATION_REPORT_RELATIVE_PATH
        before = current_path.read_bytes()
        (self.root / "course/assets/pdfs/source.pdf").write_bytes(b"broken")
        blocked = build_course_validation_report(self.root)

        write_current_validation_report(self.root, blocked)

        self.assertEqual(current_path.read_bytes(), before)
        self.assertTrue(
            (self.root / ".course-work/course-validation-attempt.json").is_file()
        )


class ValidationIssueSynchronizationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        build_full_package(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def store(self):
        return IssueStore.load(self.root / ".course-work/issues.json")

    def test_report_findings_use_stable_registered_workflow_codes(self):
        report = build_course_validation_report(self.root)

        active_ids = sync_validation_issues(self.root, report, "2026-08-16T00:00:00Z")

        issues = self.store().all()
        self.assertEqual(active_ids, (issues[0].id,))
        self.assertEqual(issues[0].code, "course-package-density-warning")
        self.assertEqual(issues[0].target["validationCode"], "dense-slice")
        self.assertEqual(
            issues[0].warning_policy,
            "no-acknowledgement-required",
        )

    def test_disappeared_validator_findings_resolve_without_touching_other_sources(self):
        warning_report = build_course_validation_report(self.root)
        sync_validation_issues(self.root, warning_report, "2026-08-16T00:00:00Z")
        store = self.store()
        unrelated = store.upsert(
            make_registered_issue(
                code="workflow-artifact-changed",
                source="workflow",
                message="changed",
                gate_id="G6",
                seen_at="2026-08-16T00:00:00Z",
                target={"path": "course/assets/"},
            )
        )
        store.save()

        clear_report = {**warning_report, "status": "clear", "warnings": []}
        sync_validation_issues(self.root, clear_report, "2026-08-16T01:00:00Z")

        restored = self.store()
        validator_issue = next(
            issue for issue in restored.all() if issue.source == "validator"
        )
        self.assertEqual(validator_issue.status, "resolved")
        self.assertEqual(restored.get(unrelated.id).status, "active")

    def test_nonblocking_warning_remains_current_without_acknowledgement(self):
        report = build_course_validation_report(self.root)
        report["warnings"] = [
            {
                "path": "course.estimatedMinutes",
                "code": "estimated-time-drift",
                "message": "review estimate",
            }
        ]
        sync_validation_issues(self.root, report, "2026-08-16T00:00:00Z")
        store = self.store()
        issue = store.all()[0]

        sync_validation_issues(self.root, report, "2026-08-16T01:00:00Z")

        restored = self.store().get(issue.id)
        self.assertEqual(restored.status, "active")
        self.assertEqual(restored.warning_policy, "no-acknowledgement-required")


class CourseDefinitionTwoValidationCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        build_full_package(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "validate-course-v2.py"),
                str(self.root),
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_warning_exit_one_and_report_written(self):
        completed = self.run_cli()

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "warnings")
        self.assertTrue((self.root / VALIDATION_REPORT_RELATIVE_PATH).is_file())

    def test_clear_exit_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_minimal_package(root)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "validate-course-v2.py"),
                    str(root),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "clear")

    def test_blocked_exit_two(self):
        (self.root / "course/assets/pdfs/source.pdf").write_bytes(b"broken")

        completed = self.run_cli()

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "blocked")

    def test_tool_failure_exit_three_without_traceback(self):
        (self.root / ".course-work/compilation-report.json").write_text(
            "not json", encoding="utf-8"
        )

        completed = self.run_cli()

        self.assertEqual(completed.returncode, 3)
        self.assertNotIn("Traceback", completed.stderr)


if __name__ == "__main__":
    unittest.main()
