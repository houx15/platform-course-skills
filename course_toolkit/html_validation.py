import re
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple

from .errors import ValidationIssue


RESOURCE_ATTRS = {
    "audio": "src",
    "iframe": "src",
    "img": "src",
    "link": "href",
    "script": "src",
    "source": "src",
    "video": "src",
}


class _ContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.resources: List[Tuple[str, str]] = []
        self.button_texts: List[str] = []
        self._button_depth = 0
        self._button_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        values = dict(attrs)
        attribute = RESOURCE_ATTRS.get(tag)
        if attribute and values.get(attribute):
            self.resources.append((f"{tag}.{attribute}", values[attribute] or ""))
        if tag == "button":
            self._button_depth += 1
            if self._button_depth == 1:
                self._button_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._button_depth:
            self._button_depth -= 1
            if self._button_depth == 0:
                self.button_texts.append("".join(self._button_parts).strip())

    def handle_data(self, data: str) -> None:
        if self._button_depth:
            self._button_parts.append(data)


def _external(url: str) -> bool:
    lowered = url.strip().lower()
    return lowered.startswith(
        ("http:", "https:", "//", "file:", "ftp:", "ws:", "wss:")
    )


def validate_interactive_html(path: Path) -> List[ValidationIssue]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [ValidationIssue(str(path), "unreadable-file", str(exc))]

    issues: List[ValidationIssue] = []
    lowered = text.lower()
    if not re.search(r"<!doctype\s+html\s*>", lowered):
        issues.append(
            ValidationIssue(str(path), "missing-doctype", "HTML5 doctype is required")
        )

    parser = _ContractParser()
    try:
        parser.feed(text)
    except Exception as exc:
        issues.append(ValidationIssue(str(path), "invalid-html", str(exc)))

    if not re.search(
        r"aspect-ratio\s*:\s*(?:1\s*/\s*1|4\s*/\s*3|1(?:\.0+)?|1\.333+)",
        lowered,
    ):
        issues.append(
            ValidationIssue(
                str(path),
                "missing-canvas",
                "a 1:1 or horizontal 4:3 aspect-ratio canvas is required",
            )
        )

    if not any(label in {"完成", "完成任务"} for label in parser.button_texts):
        issues.append(
            ValidationIssue(
                str(path),
                "missing-complete-button",
                "button text must be 完成 or 完成任务",
            )
        )

    if not re.search(r"window\s*\.\s*parent\s*\.\s*postMessage\s*\(", text):
        issues.append(
            ValidationIssue(
                str(path),
                "missing-post-message",
                "window.parent.postMessage is required",
            )
        )

    required_tokens = (
        "INTERACTION_COMPLETE",
        "version",
        "1.0",
        "payload",
        "lessonId",
        "duration",
        "interactions",
        "interactionId",
        "type",
        "answer",
    )
    missing = [token for token in required_tokens if token not in text]
    if missing:
        issues.append(
            ValidationIssue(
                str(path),
                "invalid-message-contract",
                "message contract is missing: " + ", ".join(missing),
            )
        )

    for location, url in parser.resources:
        if _external(url):
            issues.append(
                ValidationIssue(
                    location,
                    "external-resource",
                    f"external resource is not allowed: {url}",
                )
            )
    for match in re.finditer(r"url\(\s*['\"]?([^'\")]+)", text, re.IGNORECASE):
        if _external(match.group(1)):
            issues.append(
                ValidationIssue(
                    str(path),
                    "external-resource",
                    f"external CSS resource is not allowed: {match.group(1)}",
                )
            )

    if re.search(r"overflow-x\s*:\s*(?:auto|scroll)", lowered):
        issues.append(
            ValidationIssue(
                str(path),
                "horizontal-overflow-risk",
                "horizontal scrolling is not allowed",
            )
        )
    for width in re.findall(r"\bwidth\s*:\s*(\d+)px", lowered):
        if int(width) > 1024:
            issues.append(
                ValidationIssue(
                    str(path),
                    "horizontal-overflow-risk",
                    f"fixed width exceeds supported canvas: {width}px",
                )
            )
            break
    return issues
