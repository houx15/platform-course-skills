#!/usr/bin/env python3
"""Manage the teacher-approved Part/Slice page plan."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_toolkit.instructional_plan import (
    PlanApprovalError,
    PlanValidationError,
    approve_plan,
    current_timestamp,
    render_plan_at_root,
    validate_plan_at_root,
    verify_plan_approval,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage a teacher-approved course page plan")
    parser.add_argument("root", type=Path, help="course root")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    commands.add_parser("render")
    approve = commands.add_parser("approve")
    approve.add_argument("--decision-id", required=True)
    commands.add_parser("status")
    return parser


def print_issues(issues) -> None:
    for issue in issues:
        print(f"[{issue.code}] {issue.path}: {issue.message}", file=sys.stderr)


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "validate":
            issues = validate_plan_at_root(args.root)
            if issues:
                print_issues(issues)
                return 2
            print("页面计划可供教师审批。")
            return 0
        if args.command == "render":
            render_plan_at_root(args.root)
            print(".course-work/course-storyboard.md")
            return 0
        if args.command == "approve":
            approval = approve_plan(args.root, decision_id=args.decision_id, approved_at=current_timestamp())
            print(f"页面计划已审批：{approval['decisionId']}")
            return 0

        issues = validate_plan_at_root(args.root)
        if issues:
            print("状态：blocked。请先修复页面计划或课程素材证据。")
            return 2
        try:
            verify_plan_approval(args.root)
        except PlanApprovalError as exc:
            if exc.code == "approval-missing":
                print("状态：ready-for-approval。请在确认教学设计后执行 approve 并提供 decision ID。")
                return 0
            if exc.code == "approval-stale":
                print("状态：approval-stale。页面计划或素材证据已变化，请重新审批。")
                return 1
            print("状态：blocked。审批记录无效，请修复后重新审批。")
            return 2
        print("状态：approved-current。教师审批与当前页面计划、素材证据一致。")
        return 0
    except PlanValidationError as exc:
        print_issues(exc.issues)
        return 2
    except PlanApprovalError as exc:
        print(f"[{exc.code}] {exc.path}: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"页面计划工具失败：{exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
