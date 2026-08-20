import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.workflow import WorkflowError, verify_g5_compilation
from tests.test_course_package_validation import build_minimal_package


def course_document(*, asset_source="assets/pdfs/evidence.pdf"):
    return {
        "schemaVersion": "2.0",
        "course": {
            "id": "binding-course",
            "parts": [
                {
                    "id": "part-evidence",
                    "slices": [
                        {
                            "id": "slice-compare",
                            "blocks": [
                                {
                                    "id": "evidence-pdf",
                                    "type": "pdf",
                                    "source": asset_source,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    }


def required_evidence(*, bindings=None, source_file="assets/pdfs/evidence.pdf"):
    return {
        "sourceId": "source-evidence",
        "sourceFile": source_file,
        "location": "page:7/figure:2",
        "summary": "Comparison diagram",
        "disposition": "required-evidence",
        "bindings": bindings
        if bindings is not None
        else [
            {
                "partId": "part-evidence",
                "sliceId": "slice-compare",
                "blockId": "evidence-pdf",
                "role": "question-reference",
            }
        ],
    }


def write_root(root: Path, coverage: dict, course=None, source_map=None) -> None:
    write_json_atomic(root / ".course-work/source-coverage.json", coverage)
    write_json_atomic(root / "course/course.json", course or course_document())
    if source_map is not None:
        write_json_atomic(root / ".course-work/course-runtime-source-map.json", source_map)


def write_provenance_package(root: Path) -> None:
    build_minimal_package(root)
    write_json_atomic(
        root / ".course-work/source-coverage.json",
        {
            "schemaVersion": "2.0",
            "items": [
                {
                    "sourceId": "source-1",
                    "sourceFile": "materials/original.pdf",
                    "location": "page:7/figure:2",
                    "summary": "Source-backed claim",
                    "disposition": "required-core",
                    "bindings": [
                        {
                            "partId": "part-evidence-check",
                            "sliceId": "slice-read-and-answer",
                            "blockId": "claim-text",
                            "role": "concept",
                        }
                    ],
                }
            ],
        },
    )


class InstructionalBindingTests(unittest.TestCase):
    def api(self):
        return importlib.import_module("course_toolkit.instructional_bindings")

    def test_module_is_available(self):
        self.assertIsNotNone(importlib.util.find_spec("course_toolkit.instructional_bindings"))

    def test_collector_uses_course_definition_two_slices_not_legacy_pieces(self):
        course = course_document()
        course["course"]["parts"][0]["pieces"] = [
            {"id": "legacy-piece", "blocks": [{"id": "legacy-block"}]}
        ]

        destinations = self.api().collect_course_destinations(course)

        self.assertEqual(
            set(destinations),
            {("part-evidence", "slice-compare", "evidence-pdf")},
        )

    def test_required_evidence_binding_to_missing_target_blocks(self):
        item = required_evidence()
        item["bindings"][0]["blockId"] = "missing-block"
        coverage = {"schemaVersion": "2.0", "items": [item]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            audit = self.api().audit_instructional_bindings(root)

        self.assertIn("binding-target-missing", {issue.code for issue in audit.blockers})

    def test_required_material_without_bindings_blocks(self):
        coverage = {"schemaVersion": "2.0", "items": [required_evidence(bindings=[])]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            audit = self.api().audit_instructional_bindings(root)

        self.assertIn("required-binding-missing", {issue.code for issue in audit.blockers})

    def test_optional_support_without_reason_blocks(self):
        coverage = {
            "schemaVersion": "2.0",
            "items": [
                {
                    "sourceId": "source-support",
                    "sourceFile": "materials/extra.pdf",
                    "location": "page:2",
                    "summary": "Extra context",
                    "disposition": "optional-support",
                    "bindings": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            audit = self.api().audit_instructional_bindings(root)

        self.assertIn(
            "optional-support-reason-missing", {issue.code for issue in audit.blockers}
        )

    def test_loader_preserves_pdf_locator(self):
        coverage = {"schemaVersion": "2.0", "items": [required_evidence()]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            loaded = self.api().load_instructional_coverage(root)

        self.assertEqual(loaded["items"][0]["location"], "page:7/figure:2")

    def test_binding_support_ids_are_an_additive_stable_provenance_field(self):
        coverage = {"schemaVersion": "2.0", "items": [required_evidence()]}
        coverage["items"][0]["bindings"][0]["supportsIds"] = ["answer-target", "answer-target"]

        issues = self.api().validate_instructional_coverage(coverage)

        self.assertIn("binding-supports-invalid", {issue.code for issue in issues})

    def test_binding_support_ids_must_resolve_in_the_same_part_and_slice(self):
        course = course_document()
        course["course"]["parts"][0]["slices"].append(
            {"id": "slice-other", "blocks": [{"id": "cross-slice-target", "type": "text", "content": "other"}]}
        )
        coverage = {"schemaVersion": "2.0", "items": [required_evidence()]}
        coverage["items"][0]["bindings"][0]["supportsIds"] = ["missing-target", "cross-slice-target"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage, course=course)

            audit = self.api().audit_instructional_bindings(root)

        findings = {(issue.path, issue.code) for issue in audit.blockers}
        self.assertIn(("source-coverage.json.items[0].bindings[0].supportsIds[0]", "binding-support-target-missing"), findings)
        self.assertIn(("source-coverage.json.items[0].bindings[0].supportsIds[1]", "binding-support-target-missing"), findings)

    def test_valid_real_binding_passes_when_source_map_binds_source_to_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provenance_package(root)

            audit = self.api().audit_instructional_bindings(root)

        self.assertEqual(audit.blockers, ())

    def test_stale_source_map_cannot_satisfy_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provenance_package(root)
            path = root / ".course-work/course-runtime-source-map.json"
            source_map = load_json(path)
            source_map["courseDefinitionHash"] = "0" * 64
            write_json_atomic(path, source_map)

            audit = self.api().audit_instructional_bindings(root)

        codes = {issue.code for issue in audit.blockers}
        self.assertIn("source-map-derivation-mismatch", codes)
        self.assertIn("binding-source-unreferenced", codes)

    def test_wrong_source_map_runtime_pointer_cannot_satisfy_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provenance_package(root)
            coverage_path = root / ".course-work/source-coverage.json"
            coverage = load_json(coverage_path)
            coverage["items"][0]["sourceId"] = "source-added-after-compile"
            write_json_atomic(coverage_path, coverage)
            path = root / ".course-work/course-runtime-source-map.json"
            source_map = load_json(path)
            mapping = next(
                item
                for item in source_map["mappings"]
                if item["targetId"] == "block:claim-text"
            )
            mapping["runtimePointer"] = "/course/parts/0/slices/0"
            write_json_atomic(path, source_map)

            audit = self.api().audit_instructional_bindings(root)

        codes = {issue.code for issue in audit.blockers}
        self.assertIn("source-map-derivation-mismatch", codes)
        self.assertNotIn("source-map-pointer-mismatch", codes)
        self.assertIn("binding-source-unreferenced", codes)

    def test_changed_provenance_cannot_reuse_a_definition_matched_source_map(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provenance_package(root)
            path = root / ".course-work/course-runtime-source-map.json"
            source_map = load_json(path)
            mapping = next(
                item
                for item in source_map["mappings"]
                if item["targetId"] == "block:claim-text"
            )
            mapping["sourceIds"].append("source-added-after-compile")
            write_json_atomic(path, source_map)
            report_path = root / ".course-work/compilation-report.json"
            report = load_json(report_path)
            report["sourceMapHash"] = canonical_json_hash(source_map)
            write_json_atomic(report_path, report)

            audit = self.api().audit_instructional_bindings(root)

        self.assertIn(
            "source-map-derivation-mismatch",
            {issue.code for issue in audit.blockers},
        )

    def test_compilation_report_source_map_hash_must_match_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provenance_package(root)
            path = root / ".course-work/compilation-report.json"
            report = load_json(path)
            report["sourceMapHash"] = "0" * 64
            write_json_atomic(path, report)

            audit = self.api().audit_instructional_bindings(root)

        self.assertIn(
            "compilation-report-source-map-mismatch",
            {issue.code for issue in audit.blockers},
        )

    def test_stale_blueprint_cannot_certify_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provenance_package(root)
            path = root / ".course-work/course-blueprint.json"
            blueprint = load_json(path)
            blueprint["course"]["title"] = "Changed after compilation"
            write_json_atomic(path, blueprint)

            audit = self.api().audit_instructional_bindings(root)

        self.assertIn(
            "course-definition-derivation-mismatch",
            {issue.code for issue in audit.blockers},
        )

    def test_source_map_schema_and_compiler_identity_must_be_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provenance_package(root)
            path = root / ".course-work/course-runtime-source-map.json"
            source_map = load_json(path)
            source_map.update(schemaVersion="9.0", compilerVersion="old")
            write_json_atomic(path, source_map)

            audit = self.api().audit_instructional_bindings(root)

        self.assertIn(
            "source-map-derivation-mismatch", {issue.code for issue in audit.blockers}
        )

    def test_rehashed_course_artifacts_cannot_bypass_blueprint_derivation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provenance_package(root)
            course_path = root / "course/course.json"
            course = load_json(course_path)
            course["course"]["title"] = "Forged course title"
            write_json_atomic(course_path, course)
            source_map_path = root / ".course-work/course-runtime-source-map.json"
            source_map = load_json(source_map_path)
            source_map["courseDefinitionHash"] = canonical_json_hash(course)
            write_json_atomic(source_map_path, source_map)
            report_path = root / ".course-work/compilation-report.json"
            report = load_json(report_path)
            report["courseDefinitionHash"] = canonical_json_hash(course)
            report["sourceMapHash"] = canonical_json_hash(source_map)
            write_json_atomic(report_path, report)

            audit = self.api().audit_instructional_bindings(root)
            with self.assertRaisesRegex(WorkflowError, "does not match compilation"):
                verify_g5_compilation(root)

        self.assertIn(
            "course-definition-derivation-mismatch",
            {issue.code for issue in audit.blockers},
        )

    def test_invalid_g5_evidence_is_reported_once_before_mapping_diagnosis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_provenance_package(root)
            coverage_path = root / ".course-work/source-coverage.json"
            coverage = load_json(coverage_path)
            duplicate = dict(coverage["items"][0])
            duplicate["sourceId"] = "source-2"
            coverage["items"].append(duplicate)
            write_json_atomic(coverage_path, coverage)
            source_map_path = root / ".course-work/course-runtime-source-map.json"
            source_map = load_json(source_map_path)
            mapping = next(
                item
                for item in source_map["mappings"]
                if item["targetId"] == "block:claim-text"
            )
            mapping["runtimePointer"] = "/course/parts/0/slices/0"
            write_json_atomic(source_map_path, source_map)

            audit = self.api().audit_instructional_bindings(root)

        codes = [issue.code for issue in audit.blockers]
        self.assertEqual(codes.count("source-map-derivation-mismatch"), 1)
        self.assertNotIn("source-map-pointer-mismatch", codes)

    def test_text_mentions_do_not_count_as_asset_or_provenance_bindings(self):
        course = course_document(asset_source="assets/pdfs/other.pdf")
        course["course"]["parts"][0]["slices"][0]["blocks"] = [
            {
                "id": "evidence-pdf",
                "type": "text",
                "content": "materials/original.pdf source-evidence",
            }
        ]
        coverage = {
            "schemaVersion": "2.0",
            "items": [required_evidence(source_file="materials/original.pdf")],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage, course=course)

            audit = self.api().audit_instructional_bindings(root)

        self.assertIn("binding-source-unreferenced", {issue.code for issue in audit.blockers})

    def test_real_asset_bearing_block_fields_satisfy_direct_bindings(self):
        course = course_document()
        blocks = course["course"]["parts"][0]["slices"][0]["blocks"]
        blocks.extend(
            [
                {
                    "id": "evidence-image",
                    "type": "images",
                    "items": [{"id": "image-1", "source": "assets/images/a.png"}],
                },
                {"id": "evidence-video", "type": "video", "source": "assets/videos/a.mp4"},
                {
                    "id": "evidence-html",
                    "type": "interactiveHtml",
                    "source": "interactions/html/a.html",
                },
            ]
        )
        assets = {
            "evidence-pdf": "assets/pdfs/evidence.pdf",
            "evidence-image": "assets/images/a.png",
            "evidence-video": "assets/videos/a.mp4",
            "evidence-html": "interactions/html/a.html",
        }
        items = []
        for index, (block_id, source_file) in enumerate(assets.items()):
            item = required_evidence(source_file=source_file)
            item["sourceId"] = f"source-{index}"
            item["bindings"][0]["blockId"] = block_id
            items.append(item)
        coverage = {"schemaVersion": "2.0", "items": items}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage, course=course)

            audit = self.api().audit_instructional_bindings(root)

        self.assertEqual(audit.blockers, ())

    def test_existing_target_that_does_not_reference_source_blocks(self):
        coverage = {
            "schemaVersion": "2.0",
            "items": [required_evidence(source_file="materials/original.pdf")],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            audit = self.api().audit_instructional_bindings(root)

        self.assertIn("binding-source-unreferenced", {issue.code for issue in audit.blockers})

    def test_exclude_approved_requires_reason_decision_and_teacher_confirmation(self):
        item = required_evidence(bindings=[])
        item["disposition"] = "exclude-approved"
        item.pop("bindings")
        coverage = {"schemaVersion": "2.0", "items": [item]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            audit = self.api().audit_instructional_bindings(root)

        codes = {issue.code for issue in audit.blockers}
        self.assertTrue(
            {
                "exclude-approved-reason-missing",
                "exclude-approved-decision-missing",
                "exclude-approved-teacher-confirmation-missing",
            }.issubset(codes)
        )

    def test_authoring_only_never_requires_learner_binding(self):
        item = required_evidence(bindings=[])
        item["disposition"] = "authoring-only"
        coverage = {"schemaVersion": "2.0", "items": [item]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            audit = self.api().audit_instructional_bindings(root)

        self.assertEqual(audit.blockers, ())

    def test_proposed_exclusion_is_a_warning_before_preview(self):
        item = required_evidence(bindings=[])
        item.update(disposition="exclude-proposed", reason="Duplicate figure")
        coverage = {"schemaVersion": "2.0", "items": [item]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            audit = self.api().audit_instructional_bindings(root)

        self.assertEqual(audit.blockers, ())
        self.assertIn("exclude-proposed", {issue.code for issue in audit.warnings})

    def test_migrates_current_v1_records_to_slice_bindings(self):
        document = course_document()
        v1 = {
            "schemaVersion": "1.0",
            "items": [
                {
                    "sourceId": "source-evidence",
                    "sourceFile": "assets/pdfs/evidence.pdf",
                    "location": "page:7/figure:2",
                    "summary": "Comparison diagram",
                    "status": "mapped",
                    "destinations": ["part-evidence/slice-compare/evidence-pdf"],
                },
                {
                    "sourceId": "source-excluded",
                    "sourceFile": "materials/extra.pdf",
                    "location": "page:9",
                    "summary": "Duplicate",
                    "status": "discard-approved",
                    "reason": "Duplicate",
                    "teacherConfirmed": True,
                    "decisionId": "decision-omit-extra",
                },
            ],
        }

        migrated = self.api().migrate_coverage_v1(v1, document)

        self.assertEqual(migrated["schemaVersion"], "2.0")
        self.assertEqual(migrated["items"][0]["disposition"], "required-core")
        self.assertEqual(migrated["items"][0]["location"], "page:7/figure:2")
        self.assertEqual(
            migrated["items"][0]["bindings"][0],
            {
                "partId": "part-evidence",
                "sliceId": "slice-compare",
                "blockId": "evidence-pdf",
                "role": "migrated-legacy-destination",
            },
        )
        self.assertEqual(migrated["items"][1]["disposition"], "exclude-approved")
        self.assertEqual(migrated["items"][1]["decisionId"], "decision-omit-extra")

    def test_v1_incomplete_discard_approval_migrates_to_explicit_proposal(self):
        document = course_document()
        v1 = {
            "schemaVersion": "1.0",
            "items": [
                {
                    "sourceId": "source-extra",
                    "sourceFile": "materials/extra.pdf",
                    "location": "page:9",
                    "summary": "Duplicate",
                    "status": "discard-approved",
                    "reason": "Duplicate",
                    "teacherConfirmed": True,
                }
            ],
        }

        migrated = self.api().migrate_coverage_v1(v1, document)

        item = migrated["items"][0]
        self.assertEqual(item["disposition"], "exclude-proposed")
        self.assertEqual(item["legacyStatus"], "discard-approved")
        self.assertIn("migrationReason", item)

    def test_v1_unresolved_record_gets_a_traceable_migration_reason(self):
        document = course_document()
        v1 = {
            "schemaVersion": "1.0",
            "items": [
                {
                    "sourceId": "source-unresolved",
                    "sourceFile": "materials/unknown.pdf",
                    "location": "page:10",
                    "summary": "Needs a decision",
                    "status": "unresolved",
                }
            ],
        }

        migrated = self.api().migrate_coverage_v1(v1, document)

        item = migrated["items"][0]
        self.assertEqual(item["disposition"], "exclude-proposed")
        self.assertEqual(item["legacyStatus"], "unresolved")
        self.assertTrue(item["reason"])

    def test_migration_preserves_metadata_unmatched_destinations_and_retries(self):
        document = course_document()
        v1 = {
            "schemaVersion": "1.0",
            "metadata": {"author": "teacher", "labels": ["case"]},
            "items": [
                {
                    "sourceId": "source-evidence",
                    "sourceFile": "assets/pdfs/evidence.pdf",
                    "location": "page:7/figure:2",
                    "summary": "Comparison diagram",
                    "kind": "figure",
                    "unknownField": {"keep": True},
                    "status": "mapped",
                    "destinations": ["part-evidence/slice-compare/missing"],
                }
            ],
        }

        migrated = self.api().migrate_coverage_v1(v1, document)

        item = migrated["items"][0]
        self.assertEqual(migrated["metadata"], v1["metadata"])
        self.assertEqual(item["kind"], "figure")
        self.assertEqual(item["unknownField"], {"keep": True})
        self.assertEqual(item["destinations"], v1["items"][0]["destinations"])
        self.assertEqual(item["migrationIssues"][0]["code"], "unmatched-legacy-destination")
        self.assertEqual(self.api().migrate_coverage_v1(migrated, document), migrated)

    def test_migration_rejects_invalid_v1_items_shape(self):
        with self.assertRaisesRegex(ValueError, "items"):
            self.api().migrate_coverage_v1({"schemaVersion": "1.0", "items": {}}, course_document())

    def test_unknown_coverage_version_is_rejected(self):
        coverage = {"schemaVersion": "3.0", "items": []}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            with self.assertRaisesRegex(ValueError, "schemaVersion"):
                self.api().load_instructional_coverage(root)
            audit = self.api().audit_instructional_bindings(root)

        self.assertIn("invalid-version", {issue.code for issue in audit.blockers})

    def test_v2_items_require_complete_source_traceability(self):
        coverage = {
            "schemaVersion": "2.0",
            "items": [
                {
                    "sourceId": "source-support",
                    "disposition": "optional-support",
                    "reason": "Outside the planned task",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            audit = self.api().audit_instructional_bindings(root)

        self.assertIn("source-field-required", {issue.code for issue in audit.blockers})

    def test_missing_course_blocks_with_a_logical_path(self):
        coverage = {"schemaVersion": "2.0", "items": []}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json_atomic(root / ".course-work/source-coverage.json", coverage)

            audit = self.api().audit_instructional_bindings(root)

        self.assertEqual(
            [(issue.path, issue.code) for issue in audit.blockers],
            [("course/course.json", "missing-file")],
        )

    def test_malformed_course_blocks_with_a_stable_shape_issue(self):
        coverage = {"schemaVersion": "2.0", "items": []}
        malformed = {"schemaVersion": "2.0", "course": {"parts": None}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage, course=malformed)

            audit = self.api().audit_instructional_bindings(root)

        self.assertEqual(
            [(issue.path, issue.code) for issue in audit.blockers],
            [("course/course.json", "invalid-shape")],
        )

    def test_coverage_course_and_source_map_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            coverage = {"schemaVersion": "2.0", "items": []}
            coverage_target = root / "coverage-target.json"
            write_json_atomic(coverage_target, coverage)
            work = root / ".course-work"
            work.mkdir()
            (work / "source-coverage.json").symlink_to(coverage_target)
            coverage_audit = self.api().audit_instructional_bindings(root)

            write_root(root, coverage)
            course_path = root / "course/course.json"
            course_target = root / "course-target.json"
            course_path.replace(course_target)
            course_path.symlink_to(course_target)
            course_audit = self.api().audit_instructional_bindings(root)

            course_path.unlink()
            write_json_atomic(course_path, course_document())
            source_target = root / "source-map-target.json"
            write_json_atomic(source_target, {"schemaVersion": "1.0"})
            (root / ".course-work/course-runtime-source-map.json").symlink_to(source_target)
            source_map_audit = self.api().audit_instructional_bindings(root)

        self.assertEqual(
            [(issue.path, issue.code) for issue in coverage_audit.blockers],
            [(".course-work/source-coverage.json", "symlink-file")],
        )
        self.assertEqual(
            [(issue.path, issue.code) for issue in course_audit.blockers],
            [("course/course.json", "symlink-file")],
        )
        self.assertIn(
            (".course-work/course-runtime-source-map.json", "symlink-file"),
            [(issue.path, issue.code) for issue in source_map_audit.blockers],
        )

    def test_invalid_json_is_root_independent_and_has_a_logical_message(self):
        audits = []
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for temporary in (first, second):
                root = Path(temporary)
                path = root / ".course-work/source-coverage.json"
                path.parent.mkdir()
                path.write_text("{invalid", encoding="utf-8")
                audits.append(self.api().audit_instructional_bindings(root))

        evidence = [
            [(issue.path, issue.code, issue.message) for issue in audit.blockers]
            for audit in audits
        ]
        self.assertEqual(evidence[0], evidence[1])
        self.assertEqual(
            evidence[0],
            [
                (
                    ".course-work/source-coverage.json",
                    "invalid-json",
                    "JSON evidence is invalid",
                )
            ],
        )

    def test_package_review_destinations_use_slice_collector(self):
        from course_toolkit.package_review import _course_destinations

        destinations = _course_destinations(course_document())

        self.assertEqual(destinations, {"part-evidence/slice-compare/evidence-pdf"})


if __name__ == "__main__":
    unittest.main()
