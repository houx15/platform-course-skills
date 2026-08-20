import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_compiler import compile_blueprint, write_compilation_outputs_atomic
from course_toolkit.course_package_validation import build_course_validation_report
from course_toolkit.decisions import DecisionStore
from course_toolkit.instructional_audit import (
    INSTRUCTIONAL_AUDIT_RELATIVE_PATH,
    SEMANTIC_CHECKS,
    InstructionalAuditError,
    _current_artifact_hashes,
    _review_context_hash,
    record_instructional_audit,
    verify_instructional_audit,
)
from course_toolkit.instructional_plan import approve_plan
from course_toolkit.jsonio import load_json, write_json_atomic
from tests.helpers import ROOT


BLUEPRINT = ROOT / "tests/fixtures/course-blueprint/approved-blueprint.json"
PART = "part-evidence-check"
SLICE = "slice-read-and-answer"


def _coverage():
    return {
        "schemaVersion": "2.0",
        "items": [
            {
                "sourceId": "source-1",
                "sourceFile": "materials/source.txt",
                "location": "paragraph:1",
                "summary": "原始主张和证据方法。",
                "disposition": "required-core",
                "bindings": [
                    {
                        "partId": PART,
                        "sliceId": SLICE,
                        "blockId": "claim-text",
                        "role": "claim",
                        "supportsIds": ["evidence-question"],
                    }
                ],
            }
        ],
    }


def _plan():
    return {
        "schemaVersion": "2.0",
        "title": "证据判断",
        "parts": [
            {
                "partId": PART,
                "title": "检查证据",
                "slices": [
                    {
                        "partId": PART,
                        "sliceId": SLICE,
                        "title": "读主张并作答",
                        "teachingPurpose": "让学生先检查来源和方法，再接受主张。",
                        "sourceUses": [
                            {
                                "sourceId": "source-1",
                                "locator": "paragraph:1",
                                "materialRole": "待检验主张",
                            }
                        ],
                        "learnerSees": "主张和选择题。",
                        "learnerAction": {
                            "kind": "answer",
                            "description": "选择首先应检查的内容。",
                            "referencePolicy": "none",
                            "referenceSourceIds": [],
                        },
                        "completionEvidence": {"event": "block.completed"},
                        "layoutIntent": {"preset": "split-horizontal", "ratio": "1:1"},
                        "coVisibleRequirements": [],
                        "imageRelationships": [],
                        "unresolvedBlockers": [],
                        "proposedExclusions": [],
                    }
                ],
            }
        ],
    }


def _inventory():
    return {
        "schemaVersion": "1.0",
        "items": [
            {
                "sourceId": "source-1",
                "sourceFile": "materials/source.txt",
                "location": "paragraph:1",
                "kind": "file",
                "text": "原始主张和证据方法。",
            }
        ],
        "ignored": [],
        "unsupported": [],
        "errors": [],
    }


def _write_root(root: Path) -> None:
    write_json_atomic(root / ".course-work/source-coverage.json", _coverage())
    write_json_atomic(root / ".course-work/materials-extracted.json", _inventory())
    write_json_atomic(root / ".course-work/course-storyboard.json", _plan())
    (root / "materials").mkdir(parents=True, exist_ok=True)
    (root / "materials/source.txt").write_text("原始主张和证据方法。", encoding="utf-8")
    approve_plan(root, decision_id="decision-plan", approved_at="2026-08-21T00:00:00Z")
    blueprint = load_json(BLUEPRINT)
    write_json_atomic(root / ".course-work/course-blueprint.json", blueprint)
    write_compilation_outputs_atomic(root, compile_blueprint(blueprint))
    report = build_course_validation_report(root)
    if report["status"] == "blocked":
        raise AssertionError(report["issues"])
    write_json_atomic(root / ".course-work/course-validation-report.json", report)


def _candidate(root: Path, *, status: str = "pass") -> dict:
    hashes, _plan_data, _coverage_data, _blueprint, _course = _current_artifact_hashes(root)
    entries = []
    for check in SEMANTIC_CHECKS:
        entry = {
            "partId": PART,
            "sliceId": SLICE,
            "check": check,
            "status": status,
            "sourceIds": ["source-1"],
            "targetIds": ["block:evidence-question"],
            "evidence": "源材料、页面计划和当前题目共同支持本项判断。",
        }
        if status == "review":
            entry["plausibleArrangements"] = ["保留当前左右并列安排。", "将主张置于题目上方后继续同屏呈现。"]
        entries.append(entry)
    return {"schemaVersion": "1.0", "artifactHashes": hashes, "entries": entries}


class InstructionalAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        _write_root(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_semantic_check_tuple_and_deterministic_root_independent_report(self):
        self.assertEqual(
            SEMANTIC_CHECKS,
            (
                "image-supports-assigned-claim",
                "question-answerable-from-declared-evidence",
                "deictic-reference-resolves",
                "required-reference-co-visible",
                "teacher-correctness-preserved",
                "source-claim-not-over-reduced",
            ),
        )
        first = record_instructional_audit(self.root, _candidate(self.root))
        with tempfile.TemporaryDirectory() as other:
            other_root = Path(other)
            _write_root(other_root)
            second = record_instructional_audit(other_root, _candidate(other_root))
        self.assertEqual(first, second)
        self.assertIn("instructionalAuditHash", verify_instructional_audit(self.root))

    def test_every_slice_check_is_required_exactly_once(self):
        for mutate, code in (
            (lambda value: value["entries"].pop(), "slice-check-coverage"),
            (lambda value: value["entries"].append(copy.deepcopy(value["entries"][0])), "duplicate-check-coverage"),
        ):
            with self.subTest(code=code):
                candidate = _candidate(self.root)
                mutate(candidate)
                with self.assertRaises(InstructionalAuditError) as caught:
                    record_instructional_audit(self.root, candidate)
                self.assertEqual(caught.exception.code, code)

    def test_source_target_evidence_status_and_closed_schema_are_strict(self):
        cases = (
            (lambda entry: entry.update(sourceIds=["missing"]), "unknown-source"),
            (lambda entry: entry.update(targetIds=["block:missing"]), "unknown-target"),
            (lambda entry: entry.update(evidence=" "), "evidence-required"),
            (lambda entry: entry.update(status="waived"), "unsupported-status"),
            (lambda entry: entry.update(waived=True), "unknown-field"),
        )
        for mutate, code in cases:
            with self.subTest(code=code):
                candidate = _candidate(self.root)
                mutate(candidate["entries"][0])
                with self.assertRaises(InstructionalAuditError) as caught:
                    record_instructional_audit(self.root, candidate)
                self.assertEqual(caught.exception.code, code)

    def test_all_current_hashes_are_required_and_staleness_fails_closed(self):
        for field in ("planContentHash", "blueprintHash", "courseDefinitionHash", "sourceMapHash", "assetSetHash"):
            with self.subTest(field=field):
                candidate = _candidate(self.root)
                candidate["artifactHashes"][field] = "0" * 64
                with self.assertRaises(InstructionalAuditError) as caught:
                    record_instructional_audit(self.root, candidate)
                self.assertEqual(caught.exception.code, "audit-stale")
        candidate = _candidate(self.root)
        plan = load_json(self.root / ".course-work/course-storyboard.json")
        plan["title"] = "已变更的教学计划"
        write_json_atomic(self.root / ".course-work/course-storyboard.json", plan)
        with self.assertRaises(InstructionalAuditError) as caught:
            record_instructional_audit(self.root, candidate)
        self.assertEqual(caught.exception.code, "approval-stale")

    def test_blocker_blocks_verification_and_cannot_be_downgraded_without_new_artifacts(self):
        blocker = _candidate(self.root, status="blocker")
        record_instructional_audit(self.root, blocker)
        with self.assertRaises(InstructionalAuditError) as caught:
            verify_instructional_audit(self.root)
        self.assertEqual(caught.exception.code, "semantic-audit-blocked")
        with self.assertRaises(InstructionalAuditError) as caught:
            record_instructional_audit(self.root, _candidate(self.root))
        self.assertEqual(caught.exception.code, "blocker-downgrade-forbidden")

    def test_review_needs_two_arrangements_and_confirmed_bound_teacher_decision_before_pass(self):
        invalid = _candidate(self.root, status="review")
        invalid["entries"][0]["plausibleArrangements"] = ["只有一个方案"]
        with self.assertRaises(InstructionalAuditError) as caught:
            record_instructional_audit(self.root, invalid)
        self.assertEqual(caught.exception.code, "review-arrangements-required")

        review = _candidate(self.root)
        review["entries"][0]["status"] = "review"
        review["entries"][0]["plausibleArrangements"] = [
            "保留当前左右并列安排。",
            "将主张置于题目上方后继续同屏呈现。",
        ]
        record_instructional_audit(self.root, review)
        self.assertIn("instructionalAuditHash", verify_instructional_audit(self.root))
        old_entry = load_json(self.root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH)["entries"][0]
        context_hash = _review_context_hash(old_entry, review["artifactHashes"])
        store = DecisionStore(self.root / ".course-work/decisions.json")
        store.request("decision-semantic-layout", "选择两种可行语义安排之一", context_hash)
        store.confirm("decision-semantic-layout", "保留当前左右并列安排", "2026-08-21T01:00:00Z")
        store.save()
        resolved = _candidate(self.root)
        resolved["entries"][0]["decisionId"] = "decision-semantic-layout"
        record_instructional_audit(self.root, resolved)
        self.assertEqual(load_json(self.root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH)["entries"][0]["status"], "pass")

    def test_failed_candidate_preserves_old_valid_report_and_symlinked_destination_fails(self):
        expected = record_instructional_audit(self.root, _candidate(self.root))
        candidate = _candidate(self.root)
        candidate["entries"][0]["evidence"] = ""
        with self.assertRaises(InstructionalAuditError):
            record_instructional_audit(self.root, candidate)
        self.assertEqual(load_json(self.root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH), expected)

        path = self.root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH
        backup = self.root / ".course-work/audit-backup.json"
        path.rename(backup)
        path.symlink_to(backup)
        with self.assertRaises(InstructionalAuditError) as caught:
            record_instructional_audit(self.root, _candidate(self.root))
        self.assertEqual(caught.exception.code, "symlink-evidence")

    def test_cli_requires_confined_candidate_file_and_emits_json_errors(self):
        script = ROOT / "scripts/record-instructional-audit.py"
        result = subprocess.run(
            ["python3", str(script), str(self.root), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "candidate-required")
        result = subprocess.run(
            ["python3", str(script), str(self.root), "outside.json", "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "candidate-directory-required")

        candidates = self.root / ".course-work/candidates"
        candidates.mkdir()
        candidate_path = candidates / "audit.json"
        write_json_atomic(candidate_path, _candidate(self.root))
        result = subprocess.run(
            ["python3", str(script), str(self.root), str(candidate_path), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        target = candidates / "target.json"
        write_json_atomic(target, _candidate(self.root))
        link = candidates / "linked.json"
        link.symlink_to(target)
        result = subprocess.run(
            ["python3", str(script), str(self.root), str(link), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "candidate-symlink")


if __name__ == "__main__":
    unittest.main()
