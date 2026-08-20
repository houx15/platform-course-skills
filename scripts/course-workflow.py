#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.decisions import DecisionStore
from course_toolkit.issues import IssueStore
from course_toolkit.workflow import (
    GATE_BY_ID,
    SESSION_RELATIVE_PATH,
    WorkflowError,
    complete_gate,
    load_session,
    new_session,
    reconcile_artifacts,
    resolve_completed_evidence_issues,
    save_session,
    set_phase_status,
    verify_g3_plan,
    verify_g4_media_design,
    verify_g5_compilation,
    verify_g6_validation,
    verify_g9_publication_preflight,
    workflow_summary,
)


EXIT_SUCCESS = 0
EXIT_WORKFLOW_BLOCKED = 2
EXIT_TOOL_ERROR = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def course_root(path: Path, *, create: bool = False) -> Path:
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists() or not path.is_dir():
        raise WorkflowError(f"Course root is not a directory: {path}")
    root = path.absolute()
    if root.is_symlink():
        raise WorkflowError("Course root may not be a symlink")
    work_dir = root / ".course-work"
    if work_dir.is_symlink():
        raise WorkflowError(".course-work must not be a symlink")
    return root


def require_session(root: Path):
    if not (root / SESSION_RELATIVE_PATH).is_file():
        raise WorkflowError("No course workflow session exists; run init first")
    return load_session(root)


def sync_pending_decisions(root: Path, session) -> None:
    decisions = DecisionStore.load(root / ".course-work" / "decisions.json")
    session.pending_decision_ids = [
        decision.id
        for decision in decisions.all()
        if decision.status in {"pending", "invalidated"}
    ]


def result_payload(root: Path, session) -> dict:
    summary = workflow_summary(session)
    issues = IssueStore.load(root / ".course-work" / "issues.json")
    decisions = DecisionStore.load(root / ".course-work" / "decisions.json")
    summary["issues"] = [
        {
            "id": issue.id,
            "code": issue.code,
            "severity": issue.severity,
            "status": issue.status,
            "gateId": issue.gate_id,
            "message": issue.message,
            "target": issue.target,
            "remediation": issue.remediation,
        }
        for issue in issues.all()
        if issue.status == "active"
    ]
    pending_decisions = [
        {
            "id": decision.id,
            "question": decision.question,
            "status": decision.status,
            "options": list(decision.options),
        }
        for decision in decisions.all()
        if decision.status in {"pending", "invalidated"}
    ]
    summary["pendingDecisions"] = pending_decisions
    if pending_decisions:
        summary["nextAction"] = "wait for teacher decision"
    return {"ok": True, **summary}


def error_payload(code: str, message: str, status: str) -> dict:
    return {
        "ok": False,
        "phase": None,
        "status": status,
        "completedGates": [],
        "invalidatedGates": [],
        "issues": [],
        "pendingDecisions": [],
        "nextAction": "resolve error",
        "error": {"code": code, "message": message},
    }


def persisted_error_payload(args: argparse.Namespace, code: str, message: str, status: str) -> dict:
    """Return saved reconciliation state when a later gate check is blocked."""
    try:
        root = course_root(args.root)
        session = load_session(root)
        payload = result_payload(root, session)
    except (OSError, ValueError, WorkflowError):
        return error_payload(code, message, status)
    payload.update(
        {
            "ok": False,
            "status": status,
            "error": {"code": code, "message": message},
        }
    )
    return payload


def print_result(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if payload["ok"]:
        print(f"Course workflow: {payload['phase']} ({payload['status']})")
        print(f"Next action: {payload['nextAction']}")
        for issue in payload["issues"]:
            print(f"- [{issue['severity']}] {issue['code']}: {issue['message']}")
    else:
        print(
            f"Course workflow blocked: {payload['error']['message']}",
            file=sys.stderr,
        )


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local course production state")
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init", help="Create a workflow session")
    add_common_arguments(init_parser)
    init_parser.add_argument("--course-local-id", required=True)
    init_parser.add_argument("--source", action="append", default=[])

    status_parser = commands.add_parser("status", help="Read workflow state")
    add_common_arguments(status_parser)

    reconcile_parser = commands.add_parser(
        "reconcile", help="Reconcile tracked course artifacts"
    )
    add_common_arguments(reconcile_parser)

    gate_parser = commands.add_parser("complete-gate", help="Complete one gate")
    add_common_arguments(gate_parser)
    gate_parser.add_argument("gate_id", choices=tuple(GATE_BY_ID))

    accept_parser = commands.add_parser(
        "accept-warning", help="Accept one acknowledgement-required warning"
    )
    add_common_arguments(accept_parser)
    accept_parser.add_argument("issue_id")
    accept_parser.add_argument("--rationale", required=True)

    confirm_parser = commands.add_parser(
        "confirm-decision", help="Record one explicit teacher decision"
    )
    add_common_arguments(confirm_parser)
    confirm_parser.add_argument("decision_id")
    confirm_parser.add_argument("--choice", required=True)
    confirm_parser.add_argument("--rationale", required=True)

    status_update_parser = commands.add_parser(
        "set-status", help="Set a non-terminal workflow status"
    )
    add_common_arguments(status_update_parser)
    status_update_parser.add_argument(
        "workflow_status",
        choices=(
            "in-progress",
            "waiting-for-teacher",
            "blocked",
            "ready-to-publish",
            "publishing",
        ),
    )
    return parser


def execute(args: argparse.Namespace) -> tuple:
    now = utc_now()
    root = course_root(args.root, create=args.command == "init")
    if args.command == "init":
        if (root / SESSION_RELATIVE_PATH).exists():
            raise WorkflowError("A course workflow session already exists")
        session = new_session(args.course_local_id, args.source, now)
        reconcile_artifacts(root, session, now)
        sync_pending_decisions(root, session)
        save_session(root, session)
    elif args.command == "status":
        session = require_session(root)
    elif args.command == "reconcile":
        session = require_session(root)
        reconcile_artifacts(root, session, now)
        sync_pending_decisions(root, session)
        save_session(root, session)
    elif args.command == "complete-gate":
        session = require_session(root)
        if args.gate_id == "G10":
            raise WorkflowError(
                "G10 requires remote verification by the publication adapter"
            )
        if args.gate_id == "G9":
            verify_g9_publication_preflight(root)
            raise WorkflowError(
                "G9 requires handoff to the live publication adapter; "
                "the local dry-run CLI cannot complete it"
            )
        reconciliation = reconcile_artifacts(root, session, now)
        sync_pending_decisions(root, session)
        # Preserve reconciliation invalidation and its issues even when the
        # requested gate is then blocked by stale or missing evidence.
        save_session(root, session)
        if args.gate_id == "G3":
            gate_evidence = verify_g3_plan(root)
        elif args.gate_id == "G4":
            gate_evidence = verify_g4_media_design(root)
        elif args.gate_id == "G5":
            gate_evidence = verify_g5_compilation(root)
        elif args.gate_id == "G6":
            gate_evidence = verify_g6_validation(root)
        elif args.gate_id == "G7":
            from course_toolkit.preview_evidence import verify_g7_preview

            try:
                gate_evidence = verify_g7_preview(root)
            except ValueError as exc:
                raise WorkflowError(str(exc)) from exc
        elif args.gate_id == "G8":
            from course_toolkit.package_review import verify_g8_review

            try:
                gate_evidence = verify_g8_review(root)
            except ValueError as exc:
                raise WorkflowError(str(exc)) from exc
        else:
            gate_evidence = None
        complete_gate(
            session,
            args.gate_id,
            now,
            active_issues=reconciliation.active_issues,
            pending_decision_ids=session.pending_decision_ids,
            gate_evidence=gate_evidence,
        )
        resolve_completed_evidence_issues(root, session, args.gate_id, now)
        if args.gate_id == "G8":
            from course_toolkit.package_review import write_publication_review_evidence_v2

            write_publication_review_evidence_v2(root)
        save_session(root, session)
    elif args.command == "accept-warning":
        session = require_session(root)
        issues = IssueStore.load(root / ".course-work/issues.json")
        try:
            issues.accept(args.issue_id, args.rationale)
        except ValueError as exc:
            raise WorkflowError(str(exc)) from exc
        issues.save()
        reconciliation = reconcile_artifacts(root, session, now)
        session.active_issue_ids = [
            issue.id for issue in reconciliation.active_issues
        ]
        save_session(root, session)
    elif args.command == "confirm-decision":
        session = require_session(root)
        decisions = DecisionStore.load(root / ".course-work/decisions.json")
        try:
            decision = decisions.get(args.decision_id)
            if decision.options and args.choice not in decision.options:
                raise ValueError(
                    f"Decision choice must be one of: {', '.join(decision.options)}"
                )
            decisions.confirm(
                args.decision_id,
                {"choice": args.choice, "rationale": args.rationale},
                now,
            )
        except ValueError as exc:
            raise WorkflowError(str(exc)) from exc
        decisions.save()
        sync_pending_decisions(root, session)
        save_session(root, session)
    elif args.command == "set-status":
        session = require_session(root)
        set_phase_status(session, args.workflow_status, now)
        save_session(root, session)
    else:
        raise WorkflowError(f"Unknown command: {args.command}")
    return root, session


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root, session = execute(args)
        print_result(result_payload(root, session), args.json)
        return EXIT_SUCCESS
    except WorkflowError as exc:
        print_result(
            persisted_error_payload(args, "workflow-blocked", str(exc), "blocked"),
            args.json,
        )
        return EXIT_WORKFLOW_BLOCKED
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    persisted_error_payload(args, "tool-error", str(exc), "failed"),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"Workflow tool error: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
