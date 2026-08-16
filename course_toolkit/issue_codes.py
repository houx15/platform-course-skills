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
    "blueprint-invalid": IssuePolicy("blueprint-invalid", "blocker", "G3"),
    "blueprint-unconfirmed": IssuePolicy(
        "blueprint-unconfirmed", "decision-required", "G3"
    ),
    "legacy-migration-confirmation-required": IssuePolicy(
        "legacy-migration-confirmation-required", "decision-required", "G3"
    ),
    "legacy-missing-objective-alignment": IssuePolicy(
        "legacy-missing-objective-alignment", "blocker", "G3"
    ),
    "course-contract-invalid": IssuePolicy(
        "course-contract-invalid", "blocker", "G5"
    ),
    "course-package-invalid": IssuePolicy(
        "course-package-invalid", "blocker", "G6"
    ),
    "course-package-density-warning": IssuePolicy(
        "course-package-density-warning",
        "warning",
        "G6",
        "no-acknowledgement-required",
    ),
    "course-package-estimate-warning": IssuePolicy(
        "course-package-estimate-warning",
        "warning",
        "G6",
        "acknowledgement-required",
    ),
    "course-package-media-warning": IssuePolicy(
        "course-package-media-warning",
        "warning",
        "G6",
        "acknowledgement-required",
    ),
    "preview-required-annotation": IssuePolicy(
        "preview-required-annotation", "blocker", "G7"
    ),
    "preview-orphaned-annotation": IssuePolicy(
        "preview-orphaned-annotation", "blocker", "G7"
    ),
    "preview-runtime-bug": IssuePolicy(
        "preview-runtime-bug", "blocker", "G7"
    ),
    "publication-identity-conflict": IssuePolicy(
        "publication-identity-conflict", "blocker", "G9"
    ),
    "publication-review-stale": IssuePolicy(
        "publication-review-stale", "blocker", "G9"
    ),
    "publication-asset-state-stale": IssuePolicy(
        "publication-asset-state-stale", "blocker", "G9"
    ),
}


def get_issue_policy(code: str) -> IssuePolicy:
    try:
        return ISSUE_POLICIES[code]
    except KeyError as exc:
        raise ValueError(f"Unknown issue code: {code}") from exc
