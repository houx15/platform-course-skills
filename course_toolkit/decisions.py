from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from course_toolkit.jsonio import load_json, write_json_atomic


DECISION_STORE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class TeacherDecision:
    id: str
    question: str
    context: Optional[dict]
    context_hash: str
    options: Tuple[str, ...]
    answer: Optional[Any]
    status: str
    affected_artifact_ids: Tuple[str, ...]
    requested_at: Optional[str]
    decided_at: Optional[str]
    invalidated_at: Optional[str]

    def as_dict(self) -> dict:
        data = asdict(self)
        data["contextHash"] = data.pop("context_hash")
        data["affectedArtifactIds"] = list(data.pop("affected_artifact_ids"))
        data["requestedAt"] = data.pop("requested_at")
        data["decidedAt"] = data.pop("decided_at")
        data["invalidatedAt"] = data.pop("invalidated_at")
        data["options"] = list(self.options)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TeacherDecision":
        status = data["status"]
        if status not in {"pending", "confirmed", "invalidated"}:
            raise ValueError(f"Unknown decision status: {status}")
        return cls(
            id=data["id"],
            question=data["question"],
            context=data.get("context"),
            context_hash=data["contextHash"],
            options=tuple(data.get("options", [])),
            answer=data.get("answer"),
            status=status,
            affected_artifact_ids=tuple(data.get("affectedArtifactIds", [])),
            requested_at=data.get("requestedAt"),
            decided_at=data.get("decidedAt"),
            invalidated_at=data.get("invalidatedAt"),
        )


class DecisionStore:
    def __init__(
        self,
        path: Path,
        decisions: Optional[List[TeacherDecision]] = None,
    ) -> None:
        self.path = path
        self._decisions: Dict[str, TeacherDecision] = {
            decision.id: decision for decision in (decisions or [])
        }

    @classmethod
    def load(cls, path: Path) -> "DecisionStore":
        if not path.exists():
            return cls(path)
        data = load_json(path)
        if data.get("schemaVersion") != DECISION_STORE_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported decision store schemaVersion: "
                f"{data.get('schemaVersion')}"
            )
        return cls(
            path,
            [TeacherDecision.from_dict(item) for item in data["decisions"]],
        )

    def save(self) -> None:
        write_json_atomic(
            self.path,
            {
                "schemaVersion": DECISION_STORE_SCHEMA_VERSION,
                "decisions": [decision.as_dict() for decision in self.all()],
            },
        )

    def all(self) -> List[TeacherDecision]:
        return sorted(self._decisions.values(), key=lambda decision: decision.id)

    def get(self, decision_id: str) -> TeacherDecision:
        try:
            return self._decisions[decision_id]
        except KeyError as exc:
            raise ValueError(f"Unknown decision: {decision_id}") from exc

    def request(
        self,
        decision_id: str,
        question: str,
        context_hash: str,
        *,
        context: Optional[dict] = None,
        options: Tuple[str, ...] = (),
        affected_artifact_ids: Tuple[str, ...] = (),
        requested_at: Optional[str] = None,
    ) -> TeacherDecision:
        if not decision_id or not question or not context_hash:
            raise ValueError("Decision id, question, and context hash are required")
        existing = self._decisions.get(decision_id)
        if existing is not None and existing.status == "confirmed":
            if existing.question == question and existing.context_hash == context_hash:
                return existing
            raise ValueError(
                f"Decision {decision_id} is already confirmed; invalidate it first"
            )
        decision = TeacherDecision(
            id=decision_id,
            question=question,
            context=context,
            context_hash=context_hash,
            options=tuple(options),
            answer=None,
            status="pending",
            affected_artifact_ids=tuple(affected_artifact_ids),
            requested_at=requested_at,
            decided_at=None,
            invalidated_at=None,
        )
        self._decisions[decision_id] = decision
        return decision

    def confirm(
        self,
        decision_id: str,
        answer: Any,
        decided_at: str,
    ) -> TeacherDecision:
        decision = self.get(decision_id)
        if answer is None or (isinstance(answer, str) and not answer.strip()):
            raise ValueError("A teacher decision answer is required")
        if decision.status == "confirmed":
            raise ValueError(f"Decision {decision_id} is already confirmed")
        if decision.status == "invalidated":
            raise ValueError(f"Decision {decision_id} is invalidated; request it again")
        updated = replace(
            decision,
            answer=answer,
            status="confirmed",
            decided_at=decided_at,
            invalidated_at=None,
        )
        self._decisions[decision_id] = updated
        return updated

    def reconcile_context(
        self,
        decision_id: str,
        context_hash: str,
        invalidated_at: str,
    ) -> bool:
        decision = self.get(decision_id)
        if decision.context_hash == context_hash:
            return False
        updated = replace(
            decision,
            context_hash=context_hash,
            status="invalidated",
            invalidated_at=invalidated_at,
        )
        self._decisions[decision_id] = updated
        return True
