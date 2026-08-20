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


def _write_two_slice_root(root: Path) -> None:
    _write_root(root)
    plan = load_json(root / ".course-work/course-storyboard.json")
    second = copy.deepcopy(plan["parts"][0]["slices"][0])
    second["sliceId"] = "slice-second"
    second["title"] = "第二个证据判断"
    second["sourceUses"][0].update({"sourceId": "source-2", "locator": "paragraph:2"})
    second["learnerAction"] = {
        "kind": "answer",
        "description": "参考第二段证据，选择下一步检查。",
        "referencePolicy": "co-visible",
        "referenceSourceIds": ["source-2"],
        "targetId": "question:question-two",
    }
    second["coVisibleRequirements"] = [
        {"sourceId": "source-2", "targetId": "question:question-two", "reason": "作答时需要阅读第二段证据。"}
    ]
    second["imageRelationships"] = [
        {"sourceId": "source-2", "targetType": "claim", "targetId": "claim:claim-two", "relationship": "该材料支持第二个主张的核验。"}
    ]
    plan["parts"][0]["slices"].append(second)
    coverage = load_json(root / ".course-work/source-coverage.json")
    coverage["items"].append(
        {
            "sourceId": "source-2",
            "sourceFile": "materials/source-two.txt",
            "location": "paragraph:2",
            "summary": "第二个 Slice 的独立证据。",
            "disposition": "required-core",
            "bindings": [
                {
                    "partId": PART,
                    "sliceId": "slice-second",
                    "blockId": "claim-two",
                    "role": "claim",
                    "supportsIds": ["claim-two", "question-two"],
                }
            ],
        }
    )
    inventory = load_json(root / ".course-work/materials-extracted.json")
    inventory["items"].append(
        {
            "sourceId": "source-2",
            "sourceFile": "materials/source-two.txt",
            "location": "paragraph:2",
            "kind": "file",
            "text": "第二个 Slice 的独立证据。",
        }
    )
    write_json_atomic(root / ".course-work/course-storyboard.json", plan)
    write_json_atomic(root / ".course-work/source-coverage.json", coverage)
    write_json_atomic(root / ".course-work/materials-extracted.json", inventory)
    (root / "materials/source-two.txt").write_text("第二个 Slice 的独立证据。", encoding="utf-8")
    approve_plan(root, decision_id="decision-plan-two", approved_at="2026-08-21T00:00:00Z")

    blueprint = load_json(root / ".course-work/course-blueprint.json")
    first = blueprint["course"]["parts"][0]["slices"][0]
    second_course_slice = json.loads(
        json.dumps(first)
        .replace("slice-read-and-answer", "slice-second")
        .replace("claim-text", "claim-two")
        .replace("evidence-question", "question-two")
        .replace("introduce-check", "introduce-two")
    )
    blueprint["course"]["parts"][0]["slices"].append(second_course_slice)
    blueprint["provenance"].extend(
        [
            {"targetId": "block:claim-two", "sourceIds": ["source-2"], "decisionIds": [], "status": "source-backed"},
            {"targetId": "block:question-two", "sourceIds": ["source-2"], "decisionIds": [], "status": "source-backed"},
        ]
    )
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


def _two_slice_candidate(root: Path) -> dict:
    hashes, _plan_data, _coverage_data, _blueprint, _course = _current_artifact_hashes(root)
    entries = []
    for slice_id, source_id, target_id in (
        (SLICE, "source-1", "block:evidence-question"),
        ("slice-second", "source-2", "block:question-two"),
    ):
        for check in SEMANTIC_CHECKS:
            entries.append(
                {
                    "partId": PART,
                    "sliceId": slice_id,
                    "check": check,
                    "status": "pass",
                    "sourceIds": [source_id],
                    "targetIds": [target_id],
                    "evidence": "该 Slice 的来源与题目在当前课程定义中一一对应。",
                }
            )
    second_entries = [entry for entry in entries if entry["sliceId"] == "slice-second"]
    second_entries[0]["targetIds"] = ["question:question-two"]
    second_entries[1]["targetIds"] = ["claim:claim-two"]
    return {"schemaVersion": "1.0", "artifactHashes": hashes, "entries": entries}


class InstructionalAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        _write_root(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def resolve_first_review(self) -> dict:
        review = _candidate(self.root)
        review["entries"][0].update(
            {
                "status": "review",
                "plausibleArrangements": ["保留当前左右并列安排。", "将主张置于题目上方后继续同屏呈现。"],
            }
        )
        record_instructional_audit(self.root, review)
        old_entry = load_json(self.root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH)["entries"][0]
        store = DecisionStore(self.root / ".course-work/decisions.json")
        store.request(
            "decision-semantic-layout",
            "选择两种可行语义安排之一",
            _review_context_hash(old_entry, review["artifactHashes"]),
        )
        store.confirm("decision-semantic-layout", "保留当前左右并列安排。", "2026-08-21T01:00:00Z")
        store.save()
        resolved = _candidate(self.root)
        resolved["entries"][0]["decisionId"] = "decision-semantic-layout"
        return record_instructional_audit(self.root, resolved)

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
            (lambda entry: entry.update(sourceIds=["missing"]), "source-not-in-slice"),
            (lambda entry: entry.update(targetIds=["block:missing"]), "target-not-in-slice"),
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

    def test_resolved_pass_can_escalate_to_new_blocker_or_review(self):
        self.resolve_first_review()
        blocker = _candidate(self.root, status="blocker")
        record_instructional_audit(self.root, blocker)
        stored = load_json(self.root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH)
        self.assertEqual(stored["entries"][0]["status"], "blocker")
        self.assertNotIn("decisionId", stored["entries"][0])
        with self.assertRaises(InstructionalAuditError) as caught:
            verify_instructional_audit(self.root)
        self.assertEqual(caught.exception.code, "semantic-audit-blocked")

        # A new root proves a previous resolution may also return to a genuine
        # two-option review rather than being forced to remain a stale pass.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_root(root)
            review = _candidate(root)
            review["entries"][0].update(
                {
                    "status": "review",
                    "plausibleArrangements": ["保留当前左右并列安排。", "将主张置于题目上方后继续同屏呈现。"],
                }
            )
            record_instructional_audit(root, review)
            old = load_json(root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH)["entries"][0]
            store = DecisionStore(root / ".course-work/decisions.json")
            store.request("decision-semantic-layout", "选择两种可行语义安排之一", _review_context_hash(old, review["artifactHashes"]))
            store.confirm("decision-semantic-layout", "保留当前左右并列安排。", "2026-08-21T01:00:00Z")
            store.save()
            resolved = _candidate(root)
            resolved["entries"][0]["decisionId"] = "decision-semantic-layout"
            record_instructional_audit(root, resolved)
            escalated_review = _candidate(root)
            escalated_review["entries"][0].update(
                {
                    "status": "review",
                    "plausibleArrangements": ["保留当前左右并列安排。", "把题目移到主张之下。"],
                }
            )
            record_instructional_audit(root, escalated_review)
            stored = load_json(root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH)
            self.assertEqual(stored["entries"][0]["status"], "review")
            self.assertNotIn("decisionId", stored["entries"][0])
            self.assertIn("instructionalAuditHash", verify_instructional_audit(root))

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
        store.confirm("decision-semantic-layout", "保留当前左右并列安排。", "2026-08-21T01:00:00Z")
        store.save()
        resolved = _candidate(self.root)
        resolved["entries"][0]["decisionId"] = "decision-semantic-layout"
        stored = record_instructional_audit(self.root, resolved)
        entry = stored["entries"][0]
        self.assertEqual(entry["status"], "pass")
        self.assertEqual(entry["decisionId"], "decision-semantic-layout")
        self.assertEqual(entry["plausibleArrangements"], review["entries"][0]["plausibleArrangements"])
        self.assertIn("reviewContextHash", entry)
        self.assertIn("decisionRecordHash", entry)
        self.assertIn("instructionalAuditHash", verify_instructional_audit(self.root))

        # A later recorder must keep the exact resolution, not turn it into a
        # generic pass after the decision has disappeared from the candidate.
        record_instructional_audit(self.root, stored)
        stripped = copy.deepcopy(stored)
        for field in ("decisionId", "plausibleArrangements", "reviewContextHash", "decisionRecordHash"):
            stripped["entries"][0].pop(field)
        with self.assertRaises(InstructionalAuditError) as caught:
            record_instructional_audit(self.root, stripped)
        self.assertEqual(caught.exception.code, "review-provenance-lost")
        different = copy.deepcopy(stored)
        different["entries"][0]["decisionId"] = "different-decision"
        with self.assertRaises(InstructionalAuditError) as caught:
            record_instructional_audit(self.root, different)
        self.assertEqual(caught.exception.code, "review-provenance-lost")

    def test_review_decision_requires_substantive_confirmed_record_and_verify_rechecks_it(self):
        review = _candidate(self.root)
        review["entries"][0].update(
            {
                "status": "review",
                "plausibleArrangements": ["保留当前左右并列安排。", "将主张置于题目上方后继续同屏呈现。"],
            }
        )
        record_instructional_audit(self.root, review)
        old_entry = load_json(self.root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH)["entries"][0]
        context_hash = _review_context_hash(old_entry, review["artifactHashes"])
        store = DecisionStore(self.root / ".course-work/decisions.json")
        store.request("decision-semantic-layout", "选择两种可行语义安排之一", context_hash)
        store.save()

        for field, value, code in (
            ("question", "", "review-decision-invalid"),
            ("answer", None, "review-decision-invalid"),
            ("decidedAt", None, "review-decision-invalid"),
            ("answer", "与两个方案都不同", "review-decision-answer-invalid"),
            ("contextHash", "not-the-review-context", "review-decision-stale"),
        ):
            with self.subTest(field=field, value=value):
                document = load_json(self.root / ".course-work/decisions.json")
                decision = document["decisions"][0]
                decision.update({"status": "confirmed", "question": "选择两种可行语义安排之一", "answer": "保留当前左右并列安排。", "decidedAt": "2026-08-21T01:00:00Z"})
                decision[field] = value
                write_json_atomic(self.root / ".course-work/decisions.json", document)
                candidate = _candidate(self.root)
                candidate["entries"][0]["decisionId"] = "decision-semantic-layout"
                with self.assertRaises(InstructionalAuditError) as caught:
                    record_instructional_audit(self.root, candidate)
                self.assertEqual(caught.exception.code, code)

        document = load_json(self.root / ".course-work/decisions.json")
        decision = document["decisions"][0]
        decision.update({"status": "confirmed", "question": "选择两种可行语义安排之一", "answer": "保留当前左右并列安排。", "decidedAt": "2026-08-21T01:00:00Z", "contextHash": context_hash})
        write_json_atomic(self.root / ".course-work/decisions.json", document)
        resolved = _candidate(self.root)
        resolved["entries"][0]["decisionId"] = "decision-semantic-layout"
        stored = record_instructional_audit(self.root, resolved)
        document = load_json(self.root / ".course-work/decisions.json")
        document["decisions"][0]["status"] = "invalidated"
        write_json_atomic(self.root / ".course-work/decisions.json", document)
        # Simulate an attacker rehashing the report: the persisted decision
        # record hash and concrete status still make verification fail.
        stored["artifactHashes"] = _current_artifact_hashes(self.root)[0]
        write_json_atomic(self.root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH, stored)
        with self.assertRaises(InstructionalAuditError) as caught:
            verify_instructional_audit(self.root)
        self.assertEqual(caught.exception.code, "review-decision-unconfirmed")

        document["decisions"][0].update({"status": "confirmed", "answer": "将主张置于题目上方后继续同屏呈现。", "decidedAt": "2026-08-21T01:00:00Z"})
        write_json_atomic(self.root / ".course-work/decisions.json", document)
        stored["artifactHashes"] = _current_artifact_hashes(self.root)[0]
        write_json_atomic(self.root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH, stored)
        with self.assertRaises(InstructionalAuditError) as caught:
            verify_instructional_audit(self.root)
        self.assertEqual(caught.exception.code, "review-decision-changed")

    def test_source_and_target_ids_cannot_cross_slice_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_two_slice_root(root)
            candidate = _two_slice_candidate(root)
            first = candidate["entries"][0]
            first["sourceIds"] = ["source-2"]
            with self.assertRaises(InstructionalAuditError) as caught:
                record_instructional_audit(root, candidate)
            self.assertEqual(caught.exception.code, "source-not-in-slice")
            candidate = _two_slice_candidate(root)
            candidate["entries"][0]["targetIds"] = ["block:question-two"]
            with self.assertRaises(InstructionalAuditError) as caught:
                record_instructional_audit(root, candidate)
            self.assertEqual(caught.exception.code, "target-not-in-slice")
            report = record_instructional_audit(root, _two_slice_candidate(root))
            self.assertEqual(len(report["entries"]), 2 * len(SEMANTIC_CHECKS))

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
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "candidate-outside-root")

        candidates = self.root / ".course-work/candidates"
        candidates.mkdir()
        candidate_path = candidates / "audit.json"
        write_json_atomic(candidate_path, _candidate(self.root))
        result = subprocess.run(
            ["python3", str(script), str(self.root), ".course-work/candidates/audit.json", "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        with tempfile.TemporaryDirectory(dir="/tmp", prefix="link-parent-") as temporary:
            container = Path(temporary)
            real_parent = container / "real-parent"
            linked_parent = container / "link-parent"
            linked_root = real_parent / "course"
            _write_root(linked_root)
            (linked_root / ".course-work/candidates").mkdir()
            write_json_atomic(linked_root / ".course-work/candidates/audit.json", _candidate(linked_root))
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            result = subprocess.run(
                ["python3", str(script), str(linked_parent / "course"), ".course-work/candidates/audit.json", "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((linked_root / INSTRUCTIONAL_AUDIT_RELATIVE_PATH).is_file())
        for raw in (
            str(candidate_path),
            ".course-work/candidates/./audit.json",
            ".course-work/candidates//audit.json",
            ".course-work/candidates/../audit.json",
            ".course-work/candidates\\audit.json",
        ):
            with self.subTest(raw=raw):
                result = subprocess.run(
                    ["python3", str(script), str(self.root), raw, "--json"],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["error"]["code"], "candidate-invalid-path")
        target = candidates / "target.json"
        write_json_atomic(target, _candidate(self.root))
        link = candidates / "linked.json"
        link.symlink_to(target)
        result = subprocess.run(
            ["python3", str(script), str(self.root), ".course-work/candidates/linked.json", "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "candidate-symlink")
        with tempfile.TemporaryDirectory() as path_fixture:
            fixture = Path(path_fixture)
            root_link = fixture / "root-link"
            root_link.symlink_to(self.root, target_is_directory=True)
            result = subprocess.run(
                ["python3", str(script), str(root_link), ".course-work/candidates/audit.json", "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["error"]["code"], "symlink-root")
            for kind in ("course-work", "candidates"):
                with self.subTest(kind=kind):
                    candidate_root = fixture / f"{kind}-root"
                    candidate_root.mkdir()
                    real = fixture / f"{kind}-real"
                    (real / "candidates").mkdir(parents=True)
                    if kind == "course-work":
                        (candidate_root / ".course-work").symlink_to(real, target_is_directory=True)
                    else:
                        (candidate_root / ".course-work").mkdir()
                        (candidate_root / ".course-work/candidates").symlink_to(real / "candidates", target_is_directory=True)
                    result = subprocess.run(
                        ["python3", str(script), str(candidate_root), ".course-work/candidates/audit.json", "--json"],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(json.loads(result.stdout)["error"]["code"], "candidate-directory-required")
        real = candidates / "real"
        real.mkdir()
        write_json_atomic(real / "audit.json", _candidate(self.root))
        nested = candidates / "nested"
        nested.symlink_to(real, target_is_directory=True)
        result = subprocess.run(
            ["python3", str(script), str(self.root), ".course-work/candidates/nested/audit.json", "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "candidate-symlink")
        with tempfile.TemporaryDirectory(dir=self.root.parent, prefix="sibling-course-") as sibling_path:
            sibling = Path(sibling_path)
            (sibling / ".course-work/candidates").mkdir(parents=True)
            write_json_atomic(sibling / ".course-work/candidates/audit.json", {"candidate": "live sibling"})
            result = subprocess.run(
                ["python3", str(script), str(self.root), f".course-work/candidates/../../../{sibling.name}/.course-work/candidates/audit.json", "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["error"]["code"], "candidate-invalid-path")


if __name__ == "__main__":
    unittest.main()
