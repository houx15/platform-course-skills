from pathlib import Path
from typing import List

from .errors import ValidationIssue


def validate_pdf_file(path: Path) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if path.suffix.lower() != ".pdf":
        return [
            ValidationIssue(
                "$",
                "invalid-pdf-extension",
                "PDF source must use a .pdf extension",
            )
        ]
    if not path.is_file():
        return issues
    try:
        content = path.read_bytes()
    except OSError as exc:
        return [ValidationIssue("$", "unreadable-pdf", str(exc))]
    if b"%PDF-" not in content[:1024]:
        issues.append(
            ValidationIssue("$", "invalid-pdf-header", "PDF header marker is missing")
        )
    if b"%%EOF" not in content[-4096:]:
        issues.append(
            ValidationIssue("$", "invalid-pdf-eof", "PDF EOF marker is missing")
        )
    return issues
