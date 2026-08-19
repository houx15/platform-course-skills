import re
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Set, Tuple

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
ROOT_FONT_PX = 16.0
AUXILIARY_FONT_PX = 14.0


class _ContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.resources: List[Tuple[str, str]] = []
        self.inline_styles: List[Tuple[str, str]] = []
        self.control_selectors: Set[str] = set()
        self.control_elements: List[Set[str]] = []
        self.button_texts: List[str] = []
        self._button_depth = 0
        self._button_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        values = dict(attrs)
        if tag in {"button", "input", "select", "textarea"}:
            markers = {tag}
            markers.update(
                f".{name}" for name in (values.get("class") or "").split()
            )
            if values.get("id"):
                markers.add(f"#{values['id']}")
            self.control_selectors.update(markers)
            self.control_elements.append(markers)
        if values.get("style"):
            classes = "".join(
                f".{name}" for name in (values.get("class") or "").split()
            )
            role = (
                '[data-text-role="auxiliary"]'
                if values.get("data-text-role") == "auxiliary"
                else ""
            )
            self.inline_styles.append(
                (f"{tag}{classes}{role}", values["style"] or "")
            )
        if values.get("font-size"):
            self.inline_styles.append(
                (f"{tag}", f"font-size: {values['font-size']}")
            )
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


def _font_pixels(
    value: str,
    rem_pixels: Optional[float],
    inherited_pixels: Optional[float] = None,
) -> Optional[float]:
    normalized = re.sub(r"\s*!important\s*$", "", value.strip().lower())
    if normalized == "inherit":
        return inherited_pixels
    clamp = re.fullmatch(r"clamp\(\s*([^,]+),[^,]+,[^)]+\)", normalized)
    if clamp:
        normalized = clamp.group(1).strip()
    px = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)px", normalized)
    if px:
        return float(px.group(1))
    rem = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)rem", normalized)
    if rem and rem_pixels is not None:
        return float(rem.group(1)) * rem_pixels
    return None


def _selectors(selector: str) -> List[str]:
    return [item.strip().lower() for item in selector.split(",") if item.strip()]


def _direct_target(selector: str) -> str:
    targets = [part for part in re.split(r"\s+|[>+~]", selector.strip()) if part]
    return targets[-1] if targets else ""


def _targets_control(selector: str, markers: Set[str]) -> bool:
    target = _direct_target(selector)
    if target == "*":
        return True
    return any(
        re.search(re.escape(marker) + r"(?![\w-])", target) for marker in markers
    )


def _font_declaration(declarations: str) -> Optional[Tuple[str, bool]]:
    winner: Optional[Tuple[str, bool]] = None
    for match in re.finditer(
        r"(?:^|;)\s*(font-size|font)\s*:\s*([^;]+)",
        declarations,
        re.I,
    ):
        property_name = match.group(1).lower()
        raw_value = match.group(2).strip().lower()
        important = bool(re.search(r"\s*!important\s*$", raw_value))
        value = re.sub(r"\s*!important\s*$", "", raw_value).strip()
        if property_name == "font" and value != "inherit":
            value = "__unverifiable-font-shorthand__"
        if winner is None or important or not winner[1]:
            winner = (value, important)
    return winner


def _choose_cascade(
    current: Optional[Tuple[str, bool, int, int]],
    candidate: Tuple[str, bool, int, int],
) -> Tuple[str, bool, int, int]:
    if current is None:
        return candidate
    _, current_important, current_specificity, current_order = current
    _, important, specificity, order = candidate
    if important != current_important:
        return candidate if important else current
    if specificity != current_specificity:
        return candidate if specificity > current_specificity else current
    return candidate if order >= current_order else current


def _font_contract_issues(
    path: Path,
    text: str,
    inline_styles: List[Tuple[str, str]],
    control_selectors: Set[str],
    control_elements: List[Set[str]],
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    css = "\n".join(
        match.group(1) for match in re.finditer(r"<style\b[^>]*>(.*?)</style>", text, re.I | re.S)
    )
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules = [
        (match.group(1).strip(), match.group(2))
        for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css, re.S)
    ]
    rules.extend(inline_styles)
    html_winner: Optional[Tuple[str, bool, int, int]] = None
    body_winner: Optional[Tuple[str, bool, int, int]] = None
    for order, (selector, declarations) in enumerate(rules):
        declaration = _font_declaration(declarations)
        if declaration is None:
            continue
        value, important = declaration
        for item in _selectors(selector):
            if item in {"html", ":root"}:
                specificity = 10 if item == ":root" else 1
                html_winner = _choose_cascade(
                    html_winner,
                    (value, important, specificity, order),
                )
            if item in {"body", "html body"}:
                specificity = 2 if item == "html body" else 1
                body_winner = _choose_cascade(
                    body_winner,
                    (value, important, specificity, order),
                )
    if html_winner is None and body_winner is None:
        issues.append(
            ValidationIssue(
                str(path),
                "missing-font-contract",
                "html or body must declare a verifiable font-size of at least 16px",
            )
        )
    html_root_pixels: Optional[float] = None
    if html_winner is not None:
        html_value = html_winner[0]
        html_root_pixels = (
            None
            if html_value == "inherit"
            else _font_pixels(html_value, ROOT_FONT_PX)
        )
    effective_html_root = (
        html_root_pixels if html_root_pixels is not None else ROOT_FONT_PX
    )
    root_values: List[Tuple[str, Optional[float]]] = []
    if html_winner is not None:
        root_values.append(("html/:root", html_root_pixels))
    if body_winner is not None:
        body_value = body_winner[0]
        body_pixels = (
            html_root_pixels
            if body_value == "inherit" and html_winner is not None
            else _font_pixels(body_value, effective_html_root)
        )
        root_values.append(("body", body_pixels))
    for selector, pixels in root_values:
        if pixels is None:
            issues.append(
                ValidationIssue(
                    str(path),
                    "unverifiable-font-size",
                    f"root font-size cannot be verified statically: {selector}",
                )
            )
        elif pixels < ROOT_FONT_PX:
            issues.append(
                ValidationIssue(
                    str(path),
                    "base-font-too-small",
                    f"html and body font-size must be at least 16px: {selector}",
                )
            )

    effective_root = effective_html_root
    if body_winner is not None and root_values:
        body_pixels = root_values[-1][1]
        if body_pixels is not None:
            effective_root = body_pixels
    content_rules = {}
    for order, (selector, declarations) in enumerate(rules):
        declaration = _font_declaration(declarations)
        if declaration is None:
            continue
        value, important = declaration
        for item in _selectors(selector):
            if item in {"html", "body", ":root", "html body"}:
                continue
            previous = content_rules.get(item)
            content_rules[item] = _choose_cascade(
                previous,
                (value, important, 1, order),
            )
    for selector, candidate in content_rules.items():
        selector_items = [selector]
        value = candidate[0]
        pixels = _font_pixels(value, effective_html_root, effective_root)
        is_auxiliary = any(
            re.search(r"\.auxiliary(?![\w-])", item)
            or 'data-text-role="auxiliary"' in item
            or "data-text-role='auxiliary'" in item
            or "data-text-role=auxiliary" in item
            for item in selector_items
        )
        is_control = any(
            _targets_control(item, control_selectors)
            for item in selector_items
        )
        if is_control:
            continue
        if pixels is None:
            issues.append(
                ValidationIssue(
                    str(path),
                    "unverifiable-font-size",
                    f"font-size '{value}' cannot be verified for selector: {selector}",
                )
            )
        elif is_auxiliary and pixels < AUXILIARY_FONT_PX:
            issues.append(
                ValidationIssue(
                    str(path),
                    "auxiliary-font-too-small",
                    f"auxiliary text must be at least 14px: {selector}",
                )
            )
        elif not is_auxiliary and pixels < ROOT_FONT_PX:
            issues.append(
                ValidationIssue(
                    str(path),
                    (
                        "content-font-too-small"
                        if pixels < AUXILIARY_FONT_PX
                        else "unmarked-small-text"
                    ),
                    f"visible text must be at least 16px unless marked auxiliary: {selector}",
                )
            )
    for markers in control_elements:
        selector_values = {}
        for order, (selector, declarations) in enumerate(rules):
            declaration = _font_declaration(declarations)
            if declaration is None:
                continue
            value, important = declaration
            for item in _selectors(selector):
                if not _targets_control(item, markers):
                    continue
                previous = selector_values.get(item)
                candidate = (value, important, 1, order)
                selector_values[item] = _choose_cascade(previous, candidate)
        pixels_by_selector = {
            item: _font_pixels(
                candidate[0],
                effective_html_root,
                effective_root,
            )
            for item, candidate in selector_values.items()
        }
        unique_pixels = set(pixels_by_selector.values())
        if not pixels_by_selector or None in unique_pixels or len(unique_pixels) > 1:
            issues.append(
                ValidationIssue(
                    str(path),
                    "unverifiable-font-size",
                    "a visible control has no verifiable 16px font rule: "
                    + ", ".join(sorted(markers)),
                )
            )
        elif next(iter(unique_pixels)) < ROOT_FONT_PX:
            issues.append(
                ValidationIssue(
                    str(path),
                    "control-font-too-small",
                    "a visible control resolves below 16px: "
                    + ", ".join(sorted(markers)),
                )
            )
    return issues


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
    issues.extend(
        _font_contract_issues(
            path,
            text,
            parser.inline_styles,
            parser.control_selectors,
            parser.control_elements,
        )
    )
    return issues


V2_PROTOCOL_ISSUE_CODES = {"missing-post-message", "invalid-message-contract"}
PROHIBITED_V2_APIS = (
    (r"\bfetch\s*\(", "fetch"),
    (r"\bXMLHttpRequest\b", "XMLHttpRequest"),
    (r"\bWebSocket\b", "WebSocket"),
    (r"\bEventSource\b", "EventSource"),
    (r"\bsendBeacon\s*\(", "sendBeacon"),
    (r"\blocalStorage\b", "localStorage"),
    (r"\bsessionStorage\b", "sessionStorage"),
    (r"\bindexedDB\b", "indexedDB"),
    (r"\bdocument\s*\.\s*cookie\b", "document.cookie"),
    (r"\b(?:window\s*\.\s*)?parent\s*\.\s*document\b", "parent.document"),
    (r"\b(?:window\s*\.\s*)?top\s*\.", "window.top"),
    (r"\b(?:window\s*\.\s*)?opener\b", "window.opener"),
)


def _completion_window(text: str) -> str:
    match = re.search(r"[\"']completed[\"']", text, re.I)
    if match is None:
        return ""
    end = text.find(");", match.end())
    if end < 0:
        end = min(len(text), match.end() + 1200)
    return text[match.start() : end]


def validate_interactive_html_v2(path: Path) -> List[ValidationIssue]:
    """Validate the CourseDefinition 2.0 iframe handshake and authoring policy.

    Match the pinned student contract: the host owns the Block interaction ID,
    while the frame may send a resultId and must send correct and/or value as
    learning evidence.
    """
    issues = [
        issue
        for issue in validate_interactive_html(path)
        if issue.code not in V2_PROTOCOL_ISSUE_CODES
    ]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return issues

    listener = re.search(
        r"(?:window\s*\.\s*)?addEventListener\s*\(\s*[\"']message[\"']",
        text,
        re.I,
    )
    reads_message = re.search(r"\b[a-z_$][\w$]*\s*\.\s*data\b", text, re.I)
    protocol_tokens = all(
        token in text
        for token in (
            "mind-course-interaction",
            "1.0",
            "sessionToken",
        )
    )
    if listener is None or reads_message is None or not protocol_tokens:
        issues.append(
            ValidationIssue(
                str(path),
                "missing-host-handshake",
                "HTML must receive the mind-course-interaction 1.0 host message and sessionToken",
            )
        )

    receives_token = re.search(
        r"\bsessionToken\s*=\s*[a-z_$][\w$]*\s*\.\s*sessionToken\b",
        text,
        re.I,
    )
    posts_token = re.search(
        r"postMessage\s*\(\s*\{[\s\S]{0,1200}?\bsessionToken\b",
        text,
        re.I,
    )
    if receives_token is None or posts_token is None:
        issues.append(
            ValidationIssue(
                str(path),
                "missing-session-token-echo",
                "HTML must store the host sessionToken and echo it in every frame message",
            )
        )

    silent_pre_handshake_drop = re.search(
        r"if\s*\(\s*!\s*sessionToken\s*\)\s*(?:\{\s*)?return\b",
        text,
        re.I,
    )
    if silent_pre_handshake_drop is not None:
        issues.append(
            ValidationIssue(
                str(path),
                "missing-pre-handshake-queue",
                "frame messages created before the host handshake must be queued, not silently dropped",
            )
        )

    envelope_fields = all(
        re.search(rf"\b{field}\s*(?::|,|\}})", text)
        for field in ("protocol", "version", "sessionToken", "type", "payload")
    )
    has_ready = re.search(r"[\"']ready[\"']", text) is not None
    has_completed = re.search(r"[\"']completed[\"']", text) is not None
    if (
        "mind-course-interaction" not in text
        or not envelope_fields
        or not has_ready
        or not has_completed
    ):
        issues.append(
            ValidationIssue(
                str(path),
                "invalid-frame-message-contract",
                "frame messages require protocol, version, sessionToken, type, payload, ready, and completed",
            )
        )

    completion = _completion_window(text)
    if not completion or re.search(
        r"\b(?:correct|value)\s*(?::|,|\})",
        completion,
    ) is None:
        issues.append(
            ValidationIssue(
                str(path),
                "missing-completion-evidence",
                "completed payload must include correct and/or value learning evidence; the host owns interactionId",
            )
        )

    for pattern, api_name in PROHIBITED_V2_APIS:
        if re.search(pattern, text, re.I):
            issues.append(
                ValidationIssue(
                    str(path),
                    "prohibited-html-api",
                    f"self-contained sandboxed HTML must not use {api_name}",
                )
            )
    return issues
