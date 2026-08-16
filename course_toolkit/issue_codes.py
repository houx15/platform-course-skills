from dataclasses import dataclass
from typing import Dict, Optional


ISSUE_POLICY_VERSION = "1.0"


@dataclass(frozen=True)
class IssuePolicy:
    code: str
    severity: str
    default_gate_id: str
    warning_policy: Optional[str] = None


ISSUE_POLICIES: Dict[str, IssuePolicy] = {
    "workflow-gate-prerequisite": IssuePolicy(
        "workflow-gate-prerequisite", "blocker", "G0"
    ),
    "workflow-active-blocker": IssuePolicy(
        "workflow-active-blocker", "blocker", "G0"
    ),
    "workflow-pending-decision": IssuePolicy(
        "workflow-pending-decision", "decision-required", "G0"
    ),
    "workflow-artifact-changed": IssuePolicy(
        "workflow-artifact-changed",
        "warning",
        "G0",
        "no-acknowledgement-required",
    ),
    "workflow-missing-source": IssuePolicy(
        "workflow-missing-source", "blocker", "G1"
    ),
}


def get_issue_policy(code: str) -> IssuePolicy:
    try:
        return ISSUE_POLICIES[code]
    except KeyError as exc:
        raise ValueError(f"Unknown issue code: {code}") from exc
