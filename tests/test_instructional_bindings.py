import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.jsonio import write_json_atomic


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


def source_map_for(course: dict, *, runtime_pointer="/course/parts/0/slices/0/blocks/0"):
    return {
        "courseDefinitionHash": canonical_json_hash(course),
        "mappings": [
            {
                "targetId": "block:evidence-pdf",
                "runtimePointer": runtime_pointer,
                "sourceIds": ["source-evidence"],
            }
        ],
    }


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

    def test_valid_real_binding_passes_when_source_map_binds_source_to_target(self):
        coverage = {
            "schemaVersion": "2.0",
            "items": [required_evidence(source_file="materials/original.pdf")],
        }
        course = course_document()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage, course=course, source_map=source_map_for(course))

            audit = self.api().audit_instructional_bindings(root)

        self.assertEqual(audit.blockers, ())

    def test_stale_source_map_cannot_satisfy_binding(self):
        coverage = {
            "schemaVersion": "2.0",
            "items": [required_evidence(source_file="materials/original.pdf")],
        }
        course = course_document()
        source_map = source_map_for(course)
        source_map["courseDefinitionHash"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage, course=course, source_map=source_map)

            audit = self.api().audit_instructional_bindings(root)

        codes = {issue.code for issue in audit.blockers}
        self.assertIn("source-map-stale", codes)
        self.assertIn("binding-source-unreferenced", codes)

    def test_wrong_source_map_runtime_pointer_cannot_satisfy_binding(self):
        coverage = {
            "schemaVersion": "2.0",
            "items": [required_evidence(source_file="materials/original.pdf")],
        }
        course = course_document()
        source_map = source_map_for(course, runtime_pointer="/course/parts/0/slices/0")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage, course=course, source_map=source_map)

            audit = self.api().audit_instructional_bindings(root)

        codes = {issue.code for issue in audit.blockers}
        self.assertIn("source-map-pointer-mismatch", codes)
        self.assertIn("binding-source-unreferenced", codes)

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

    def test_unknown_coverage_version_is_rejected(self):
        coverage = {"schemaVersion": "3.0", "items": []}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, coverage)

            with self.assertRaisesRegex(ValueError, "schemaVersion"):
                self.api().load_instructional_coverage(root)
            audit = self.api().audit_instructional_bindings(root)

        self.assertIn("coverage-unavailable", {issue.code for issue in audit.blockers})

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

    def test_package_review_destinations_use_slice_collector(self):
        from course_toolkit.package_review import _course_destinations

        destinations = _course_destinations(course_document())

        self.assertEqual(destinations, {"part-evidence/slice-compare/evidence-pdf"})


if __name__ == "__main__":
    unittest.main()
