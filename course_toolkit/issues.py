import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from course_toolkit.issue_codes import get_issue_policy
from course_toolkit.jsonio import load_json, write_json_atomic


ISSUE_STORE_SCHEMA_VERSION = "1.0"
ISSUE_SOURCES = frozenset(
    {"workflow", "compiler", "validator", "preview", "review", "publisher"}
)


@dataclass(frozen=True)
class CourseProductionIssue:
    id: str
    fingerprint: str
    code: str
    severity: str
    status: str
    gate_id: str
    source: str
    message: str
    first_seen_at: str
    last_seen_at: str
    target: Optional[dict] = None
    evidence: Tuple[str, ...] = ()
    remediation: Optional[str] = None
    warning_policy: Optional[str] = None
    teacher_decision_id: Optional[str] = None
    rationale: Optional[str] = None
    resolved_at: Optional[str] = None

    def as_dict(self) -> dict:
        data = asdict(self)
        data["gateId"] = data.pop("gate_id")
        data["firstSeenAt"] = data.pop("first_seen_at")
        data["lastSeenAt"] = data.pop("last_seen_at")
        data["warningPolicy"] = data.pop("warning_policy")
        data["teacherDecisionId"] = data.pop("teacher_decision_id")
        data["resolvedAt"] = data.pop("resolved_at")
        data["evidence"] = list(self.evidence)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "CourseProductionIssue":
        policy = get_issue_policy(data["code"])
        if data["severity"] != policy.severity:
            raise ValueError(f"Issue {data['id']} does not match registered severity")
        if data.get("warningPolicy") != policy.warning_policy:
            raise ValueError(f"Issue {data['id']} does not match registered warning policy")
        if data["source"] not in ISSUE_SOURCES:
            raise ValueError(f"Unknown issue source: {data['source']}")
        return cls(
            id=data["id"],
            fingerprint=data["fingerprint"],
            code=data["code"],
            severity=data["severity"],
            status=data["status"],
            gate_id=data["gateId"],
            source=data["source"],
            message=data["message"],
            first_seen_at=data["firstSeenAt"],
            last_seen_at=data["lastSeenAt"],
            target=data.get("target"),
            evidence=tuple(data.get("evidence", [])),
            remediation=data.get("remediation"),
            warning_policy=data.get("warningPolicy"),
            teacher_decision_id=data.get("teacherDecisionId"),
            rationale=data.get("rationale"),
            resolved_at=data.get("resolvedAt"),
        )


def _fingerprint(code: str, gate_id: str, source: str, target: Optional[dict]) -> str:
    identity = {
        "code": code,
        "gateId": gate_id,
        "source": source,
        "target": target,
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_registered_issue(
    *,
    code: str,
    source: str,
    message: str,
    seen_at: str,
    gate_id: Optional[str] = None,
    target: Optional[dict] = None,
    evidence: Tuple[str, ...] = (),
    remediation: Optional[str] = None,
    teacher_decision_id: Optional[str] = None,
) -> CourseProductionIssue:
    policy = get_issue_policy(code)
    if source not in ISSUE_SOURCES:
        raise ValueError(f"Unknown issue source: {source}")
    effective_gate = gate_id or policy.default_gate_id
    if effective_gate not in {f"G{index}" for index in range(11)}:
        raise ValueError(f"Unknown workflow gate: {effective_gate}")
    fingerprint = _fingerprint(code, effective_gate, source, target)
    return CourseProductionIssue(
        id=f"issue-{fingerprint[:16]}",
        fingerprint=fingerprint,
        code=code,
        severity=policy.severity,
        status="active",
        gate_id=effective_gate,
        source=source,
        message=message,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        target=target,
        evidence=evidence,
        remediation=remediation,
        warning_policy=policy.warning_policy,
        teacher_decision_id=teacher_decision_id,
    )


class IssueStore:
    def __init__(
        self,
        path: Path,
        issues: Optional[List[CourseProductionIssue]] = None,
    ) -> None:
        self.path = path
        self._issues: Dict[str, CourseProductionIssue] = {
            issue.id: issue for issue in (issues or [])
        }

    @classmethod
    def load(cls, path: Path) -> "IssueStore":
        if not path.exists():
            return cls(path)
        data = load_json(path)
        if data.get("schemaVersion") != ISSUE_STORE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported issue store schemaVersion: {data.get('schemaVersion')}"
            )
        return cls(
            path,
            [CourseProductionIssue.from_dict(item) for item in data["issues"]],
        )

    def save(self) -> None:
        write_json_atomic(
            self.path,
            {
                "schemaVersion": ISSUE_STORE_SCHEMA_VERSION,
                "issues": [issue.as_dict() for issue in self.all()],
            },
        )

    def all(self) -> List[CourseProductionIssue]:
        return sorted(self._issues.values(), key=lambda issue: issue.id)

    def get(self, issue_id: str) -> CourseProductionIssue:
        try:
            return self._issues[issue_id]
        except KeyError as exc:
            raise ValueError(f"Unknown issue: {issue_id}") from exc

    def upsert(self, issue: CourseProductionIssue) -> CourseProductionIssue:
        existing = next(
            (
                candidate
                for candidate in self._issues.values()
                if candidate.fingerprint == issue.fingerprint
            ),
            None,
        )
        if existing is None:
            updated = issue
        else:
            updated = replace(
                issue,
                id=existing.id,
                first_seen_at=existing.first_seen_at,
                status="active",
                rationale=None,
                resolved_at=None,
            )
        self._issues[updated.id] = updated
        return updated

    def resolve(self, issue_id: str, resolved_at: str) -> CourseProductionIssue:
        issue = self.get(issue_id)
        updated = replace(issue, status="resolved", resolved_at=resolved_at)
        self._issues[issue_id] = updated
        return updated

    def dismiss(self, issue_id: str, rationale: str) -> CourseProductionIssue:
        issue = self.get(issue_id)
        if issue.severity == "blocker":
            raise ValueError(f"Blocker {issue_id} cannot be dismissed")
        updated = replace(issue, status="dismissed", rationale=rationale)
        self._issues[issue_id] = updated
        return updated

    def accept(self, issue_id: str, rationale: str) -> CourseProductionIssue:
        issue = self.get(issue_id)
        if (
            issue.severity != "warning"
            or issue.warning_policy != "acknowledgement-required"
        ):
            raise ValueError(f"Issue {issue_id} cannot be accepted")
        updated = replace(issue, status="accepted", rationale=rationale)
        self._issues[issue_id] = updated
        return updated
