import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.decisions import DecisionStore
from course_toolkit.issues import IssueStore, make_registered_issue
from course_toolkit.workflow import (
    G3_EVIDENCE_KEYS,
    G4_EVIDENCE_KEYS,
    G4_PREREQUISITE_COVERAGE_KEY,
    G5_EVIDENCE_KEYS,
    G6_EVIDENCE_KEYS,
    G7_EVIDENCE_KEYS,
    G8_EVIDENCE_KEYS,
    G9_EVIDENCE_KEYS,
    complete_gate,
    load_session,
    save_session,
    verify_g3_plan,
    verify_g4_media_design,
)
from course_toolkit.instructional_plan import approve_plan
from tests.test_instructional_plan import write_root, write_valid_media_design


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "course-workflow.py"
COMPILER = REPOSITORY_ROOT / "scripts" / "compile-course.py"
VALIDATOR = REPOSITORY_ROOT / "scripts" / "validate-course-v2.py"
APPROVED = (
    REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "course-blueprint"
    / "approved-blueprint.json"
)


def approved_blueprint_coverage():
    return {
        "schemaVersion": "2.0",
        "items": [
            {
                "sourceId": "source-1",
                "sourceFile": "materials/evidence.pdf",
                "location": "page:1",
                "summary": "Source-and-method evidence for the claim.",
                "disposition": "required-evidence",
                "bindings": [
                    {
                        "partId": "part-evidence-check",
                        "sliceId": "slice-read-and-answer",
                        "blockId": "claim-text",
                    }
                ],
            }
        ],
    }


def approved_blueprint_plan():
    return {
        "schemaVersion": "2.0",
        "title": "Evidence check",
        "parts": [
            {
                "partId": "part-evidence-check",
                "title": "Check the evidence",
                "slices": [
                    {
                        "partId": "part-evidence-check",
                        "sliceId": "slice-read-and-answer",
                        "title": "Read and answer",
                        "teachingPurpose": "Have the learner apply a source-and-method check.",
                        "sourceUses": [
                            {"sourceId": "source-1", "locator": "page:1", "materialRole": "claim evidence"}
                        ],
                        "learnerSees": "A claim and a question.",
                        "learnerAction": {
                            "kind": "answer",
                            "description": "Read the claim, then choose the first evidence check.",
                            "referencePolicy": "co-visible",
                            "referenceSourceIds": ["source-1"],
                            "targetId": "question:evidence-question",
                        },
                        "completionEvidence": {"event": "block.completed"},
                        "layoutIntent": {"preset": "split-horizontal", "ratio": "1:1"},
                        "coVisibleRequirements": [
                            {
                                "sourceId": "source-1",
                                "targetId": "question:evidence-question",
                                "reason": "The claim remains visible while the learner answers.",
                            }
                        ],
                        "imageRelationships": [],
                        "unresolvedBlockers": [],
                        "proposedExclusions": [],
                    }
                ],
            }
        ],
    }


def approved_blueprint_extracted():
    coverage = approved_blueprint_coverage()
    return {
        "schemaVersion": "1.0",
        "items": [
            {
                "sourceId": "source-1",
                "sourceFile": coverage["items"][0]["sourceFile"],
                "location": "page:1",
                "kind": "file",
                "text": "Source-and-method evidence for the claim.",
            }
        ],
        "ignored": [],
        "unsupported": [],
        "errors": [],
    }


class WorkflowCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "course"
        self.root.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def json_result(self, *arguments):
        completed = self.run_cli(*arguments)
        return completed, json.loads(completed.stdout)

    def init(self, *extra):
        return self.json_result(
            "init",
            self.root,
            "--course-local-id",
            "demo",
            *extra,
            "--json",
        )

    def prepare_approved_page_plan(self, *, media: bool = True, approved_blueprint: bool = False) -> None:
        if approved_blueprint:
            write_root(
                self.root,
                plan=approved_blueprint_plan(),
                coverage=approved_blueprint_coverage(),
                extracted=approved_blueprint_extracted(),
            )
        else:
            write_root(self.root)
        approve_plan(
            self.root,
            decision_id="decision-plan-1",
            approved_at="2026-08-21T00:00:00Z",
        )
        if media:
            write_valid_media_design(self.root)

    def test_init_creates_session_and_stable_json_summary(self):
        material = self.root / "materials" / "a.md"
        material.parent.mkdir()
        material.write_text("source", encoding="utf-8")

        completed, payload = self.init("--source", "materials/a.md")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["phase"], "intake")
        self.assertEqual(payload["status"], "in-progress")
        self.assertEqual(payload["completedGates"], [])
        self.assertEqual(payload["invalidatedGates"], [])
        self.assertEqual(payload["issues"], [])
        self.assertEqual(payload["pendingDecisions"], [])
        self.assertEqual(payload["nextAction"], "complete G0")
        self.assertTrue((self.root / ".course-work" / "session.json").is_file())

    def test_status_restores_existing_session(self):
        self.init()

        completed, payload = self.json_result("status", self.root, "--json")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["courseLocalId"], "demo")

    def test_status_explicitly_reconciles_legacy_page_plan_proof(self):
        self.init()
        self.prepare_approved_page_plan()
        for gate_id in ("G0", "G1", "G2", "G3", "G4"):
            completed = self.run_cli("complete-gate", self.root, gate_id, "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
        session = load_session(self.root)
        session.artifact_hashes.pop(".course-work/source-coverage.json")
        save_session(self.root, session)

        completed, payload = self.json_result("status", self.root, "--json")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["completedGates"], ["G0", "G1", "G2"])
        self.assertEqual(payload["invalidatedGates"][:2], ["G3", "G4"])
        self.assertTrue(
            any(
                issue["code"] == "workflow-page-plan-evidence-unproved"
                for issue in payload["issues"]
            )
        )
        self.assertEqual(load_session(self.root).completed_gate_ids, ["G0", "G1", "G2"])

    def test_reconcile_reports_missing_source_as_readable_issue(self):
        self.init("--source", "materials/missing.md")

        completed, payload = self.json_result("reconcile", self.root, "--json")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["issues"][0]["code"], "workflow-missing-source")
        self.assertEqual(payload["issues"][0]["severity"], "blocker")

    def test_complete_gate_enforces_prerequisite_with_exit_two(self):
        self.init()

        completed, payload = self.json_result(
            "complete-gate", self.root, "G1", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertIn("G1 requires G0", payload["error"]["message"])
        self.assertNotIn("Traceback", completed.stderr)

    def test_complete_gate_reconciles_then_persists(self):
        self.init()

        completed, payload = self.json_result(
            "complete-gate", self.root, "G0", "--json"
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["completedGates"], ["G0"])
        self.assertEqual(payload["phase"], "material-review")

    def test_g3_and_g4_complete_from_current_plan_evidence(self):
        self.init()
        write_root(self.root)
        for gate_id in ("G0", "G1", "G2"):
            completed = self.run_cli("complete-gate", self.root, gate_id, "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)

        missing_plan, missing_plan_payload = self.json_result(
            "complete-gate", self.root, "G3", "--json"
        )
        self.assertEqual(missing_plan.returncode, 0, missing_plan.stderr)
        self.assertEqual(missing_plan_payload["completedGates"][-1], "G3")

        missing_approval, missing_approval_payload = self.json_result(
            "complete-gate", self.root, "G4", "--json"
        )
        self.assertEqual(missing_approval.returncode, 2)
        self.assertIn("approval-missing", missing_approval_payload["error"]["message"])
        self.assertNotIn(str(self.root), missing_approval_payload["error"]["message"])

        approve_plan(
            self.root,
            decision_id="decision-plan-1",
            approved_at="2026-08-21T00:00:00Z",
        )
        missing_media, missing_media_payload = self.json_result(
            "complete-gate", self.root, "G4", "--json"
        )
        self.assertEqual(missing_media.returncode, 2)
        self.assertIn("media-design.json", missing_media_payload["error"]["message"])

        write_valid_media_design(self.root)
        completed, payload = self.json_result("complete-gate", self.root, "G4", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["completedGates"][-1], "G4")

    def test_g4_reports_stale_approval_with_stable_error(self):
        self.init()
        self.prepare_approved_page_plan()
        for gate_id in ("G0", "G1", "G2", "G3"):
            completed = self.run_cli("complete-gate", self.root, gate_id, "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
        storyboard_path = self.root / ".course-work" / "course-storyboard.json"
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
        storyboard["parts"][0]["slices"][0]["teachingPurpose"] = "审批后更新"
        storyboard_path.write_text(json.dumps(storyboard), encoding="utf-8")

        completed, payload = self.json_result("complete-gate", self.root, "G4", "--json")

        self.assertEqual(completed.returncode, 2)
        self.assertIn("approval-stale", payload["error"]["message"])
        self.assertNotIn(str(self.root), payload["error"]["message"])

    def test_g4_requires_recompleted_g3_and_resolves_changed_evidence_issues(self):
        self.init()
        self.prepare_approved_page_plan()
        for gate_id in ("G0", "G1", "G2", "G3", "G4"):
            completed = self.run_cli("complete-gate", self.root, gate_id, "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)

        storyboard_path = self.root / ".course-work" / "course-storyboard.json"
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
        storyboard["parts"][0]["slices"][0]["teachingPurpose"] = "重新审批后的页面目标"
        storyboard_path.write_text(json.dumps(storyboard), encoding="utf-8")
        approve_plan(
            self.root,
            decision_id="decision-plan-2",
            approved_at="2026-08-22T00:00:00Z",
        )
        write_valid_media_design(self.root)

        blocked, blocked_payload = self.json_result(
            "complete-gate", self.root, "G4", "--json"
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("G4 requires G3", blocked_payload["error"]["message"])
        self.assertEqual(blocked_payload["phase"], "course-design")
        self.assertEqual(blocked_payload["completedGates"], ["G0", "G1", "G2"])
        self.assertTrue(blocked_payload["issues"])
        self.assertNotIn(str(self.root), blocked_payload["error"]["message"])
        invalidated = load_session(self.root)
        self.assertEqual(invalidated.completed_gate_ids, ["G0", "G1", "G2"])
        self.assertTrue(
            any(
                issue.code == "workflow-artifact-changed"
                for issue in IssueStore.load(self.root / ".course-work" / "issues.json").all()
                if issue.status == "active"
            )
        )

        completed_g3, g3_payload = self.json_result(
            "complete-gate", self.root, "G3", "--json"
        )
        self.assertEqual(completed_g3.returncode, 0, completed_g3.stderr)
        self.assertEqual(g3_payload["completedGates"][-1], "G3")
        self.assertFalse(
            any(
                issue["target"] == {"path": ".course-work/course-storyboard.json"}
                for issue in g3_payload["issues"]
            )
        )

        completed_g4, g4_payload = self.json_result(
            "complete-gate", self.root, "G4", "--json"
        )
        self.assertEqual(completed_g4.returncode, 0, completed_g4.stderr)
        self.assertEqual(g4_payload["completedGates"][-1], "G4")
        self.assertEqual(g4_payload["issues"], [])

        repeated, repeated_payload = self.json_result(
            "complete-gate", self.root, "G4", "--json"
        )
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(repeated_payload["issues"], [])

    def test_set_status_persists_waiting_for_teacher(self):
        self.init()

        completed, payload = self.json_result(
            "set-status", self.root, "waiting-for-teacher", "--json"
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["status"], "waiting-for-teacher")

    def test_set_publish_status_cannot_bypass_gate(self):
        self.init()

        completed, payload = self.json_result(
            "set-status", self.root, "ready-to-publish", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires G8", payload["error"]["message"])

    def test_init_refuses_to_overwrite_existing_session(self):
        self.init()

        completed, payload = self.init()

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["error"]["code"], "workflow-blocked")

    def test_g10_cannot_be_manually_completed_without_publication_adapter(self):
        self.init()
        self.prepare_approved_page_plan()
        for index in range(10):
            session = load_session(self.root)
            if index == 3:
                evidence = verify_g3_plan(self.root)
            elif index == 4:
                evidence = verify_g4_media_design(self.root)
            elif index == 5:
                evidence = {key: "a" * 64 for key in G5_EVIDENCE_KEYS}
            elif index == 6:
                evidence = {key: "b" * 64 for key in G6_EVIDENCE_KEYS}
            elif index == 7:
                evidence = {key: "d" * 64 for key in G7_EVIDENCE_KEYS}
            elif index == 8:
                evidence = {key: "e" * 64 for key in G8_EVIDENCE_KEYS}
            elif index == 9:
                evidence = {key: "c" * 64 for key in G9_EVIDENCE_KEYS}
            else:
                evidence = None
            complete_gate(
                session,
                f"G{index}",
                "2026-08-16T00:00:00Z",
                gate_evidence=evidence,
            )
            save_session(self.root, session)

        completed, payload = self.json_result(
            "complete-gate", self.root, "G10", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("publication adapter", payload["error"]["message"])

    def test_g9_cannot_be_manually_completed_without_current_evidence(self):
        self.init()
        self.prepare_approved_page_plan()
        session = load_session(self.root)
        for index in range(9):
            if index == 3:
                evidence = verify_g3_plan(self.root)
            elif index == 4:
                evidence = verify_g4_media_design(self.root)
            elif index == 5:
                evidence = {key: "a" * 64 for key in G5_EVIDENCE_KEYS}
            elif index == 6:
                evidence = {key: "b" * 64 for key in G6_EVIDENCE_KEYS}
            elif index == 7:
                evidence = {key: "d" * 64 for key in G7_EVIDENCE_KEYS}
            elif index == 8:
                evidence = {key: "e" * 64 for key in G8_EVIDENCE_KEYS}
            else:
                evidence = None
            complete_gate(
                session,
                f"G{index}",
                "2026-08-16T00:00:00Z",
                gate_evidence=evidence,
            )
        save_session(self.root, session)

        completed, payload = self.json_result(
            "complete-gate", self.root, "G9", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertNotIn("G9", payload["completedGates"])
        self.assertIn("requires completed G8", payload["error"]["message"])

    def test_g7_cannot_be_manually_completed_without_renderer_preview(self):
        self.init()
        session = load_session(self.root)
        for index in range(7):
            if index == 3:
                evidence = {key: "3" * 64 for key in G3_EVIDENCE_KEYS}
            elif index == 4:
                evidence = {
                    key: (
                        "3" * 64
                        if key in {".course-work/course-storyboard.json", G4_PREREQUISITE_COVERAGE_KEY}
                        else "4" * 64
                    )
                    for key in (*G4_EVIDENCE_KEYS, G4_PREREQUISITE_COVERAGE_KEY)
                }
            elif index == 5:
                evidence = {key: "a" * 64 for key in G5_EVIDENCE_KEYS}
            elif index == 6:
                evidence = {key: "b" * 64 for key in G6_EVIDENCE_KEYS}
            else:
                evidence = None
            complete_gate(
                session,
                f"G{index}",
                "2026-08-16T00:00:00Z",
                gate_evidence=evidence,
            )
        save_session(self.root, session)

        completed, payload = self.json_result(
            "complete-gate", self.root, "G7", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("G7 preview manifest is missing", payload["error"]["message"])

    def test_g5_cannot_complete_without_current_compilation_outputs(self):
        self.init()
        self.prepare_approved_page_plan()
        for index in range(5):
            completed = self.run_cli(
                "complete-gate", self.root, f"G{index}", "--json"
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

        completed, payload = self.json_result(
            "complete-gate", self.root, "G5", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("compilation evidence is missing", payload["error"]["message"])

    def test_g6_cannot_complete_without_current_validation_report(self):
        self.init()
        self.prepare_approved_page_plan()
        blueprint = self.root / ".course-work/course-blueprint.json"
        blueprint.write_bytes(APPROVED.read_bytes())
        for index in range(6):
            if index == 5:
                compilation = subprocess.run(
                    [sys.executable, str(COMPILER), str(self.root), "--json"],
                    cwd=REPOSITORY_ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(compilation.returncode, 0, compilation.stderr)
            completed = self.run_cli(
                "complete-gate", self.root, f"G{index}", "--json"
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

        completed, payload = self.json_result(
            "complete-gate", self.root, "G6", "--json"
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("validation report is missing", payload["error"]["message"])

    def test_g6_completes_from_current_validator_evidence(self):
        self.init()
        self.prepare_approved_page_plan(approved_blueprint=True)
        blueprint = self.root / ".course-work/course-blueprint.json"
        blueprint.write_bytes(APPROVED.read_bytes())
        for index in range(6):
            if index == 5:
                subprocess.run(
                    [sys.executable, str(COMPILER), str(self.root), "--json"],
                    cwd=REPOSITORY_ROOT,
                    text=True,
                    capture_output=True,
                    check=True,
                )
            completed = self.run_cli(
                "complete-gate", self.root, f"G{index}", "--json"
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
        validation = subprocess.run(
            [sys.executable, str(VALIDATOR), str(self.root), "--json"],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(validation.returncode, 0, validation.stderr)

        completed, payload = self.json_result(
            "complete-gate", self.root, "G6", "--json"
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["completedGates"][-1], "G6")

    def test_nonblocking_warning_rejects_redundant_acknowledgement(self):
        self.init()
        store = IssueStore(self.root / ".course-work/issues.json")
        warning = store.upsert(
            make_registered_issue(
                code="course-package-estimate-warning",
                source="validator",
                message="Review the estimate",
                seen_at="2026-08-16T00:00:00Z",
                target={
                    "path": "course.estimatedMinutes",
                    "validationCode": "estimated-time-drift",
                },
            )
        )
        store.save()

        completed, payload = self.json_result(
            "accept-warning",
            self.root,
            warning.id,
            "--rationale",
            "Teacher reviewed the intended pacing",
            "--json",
        )

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(payload["error"]["code"], "workflow-blocked")
        restored = IssueStore.load(self.root / ".course-work/issues.json")
        self.assertEqual(restored.get(warning.id).status, "active")

    def test_pending_teacher_decision_is_confirmed_only_with_choice_and_rationale(self):
        self.init()
        store = DecisionStore(self.root / ".course-work/decisions.json")
        store.request(
            "decision-annotation-copy-1",
            "Approve this semantic revision?",
            "a" * 64,
            options=("approve", "revise"),
            requested_at="2026-08-16T00:00:00Z",
        )
        store.save()

        completed, payload = self.json_result(
            "confirm-decision",
            self.root,
            "decision-annotation-copy-1",
            "--choice",
            "approve",
            "--rationale",
            "The intended learning meaning is preserved.",
            "--json",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["pendingDecisions"], [])
        decision = DecisionStore.load(
            self.root / ".course-work/decisions.json"
        ).get("decision-annotation-copy-1")
        self.assertEqual(decision.status, "confirmed")
        self.assertEqual(decision.answer["choice"], "approve")

    def test_malformed_session_is_tool_error_without_traceback(self):
        work = self.root / ".course-work"
        work.mkdir()
        (work / "session.json").write_text("not json", encoding="utf-8")

        completed = self.run_cli("status", self.root)

        self.assertEqual(completed.returncode, 3)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertIn("Workflow tool error", completed.stderr)


if __name__ == "__main__":
    unittest.main()
