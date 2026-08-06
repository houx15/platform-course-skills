from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str
    message: str

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "code": self.code,
            "message": self.message,
        }
