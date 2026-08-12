import hashlib
from pathlib import Path
from typing import List

from .errors import ValidationIssue
from .html_validation import validate_interactive_html


CHECKS = (
    (
        "html-self-contained",
        "HTML5 与自包含资源",
        {"missing-doctype", "invalid-html", "external-resource", "unreadable-file"},
    ),
    ("canvas-overflow", "画布与横向溢出", {"missing-canvas", "horizontal-overflow-risk"}),
    (
        "base-font-size",
        "基础字号",
        {"missing-font-contract", "base-font-too-small"},
    ),
    (
        "body-prompts",
        "正文与题目",
        {"content-font-too-small", "unmarked-small-text", "unverifiable-font-size"},
    ),
    ("options-inputs", "选项与输入控件", {"control-font-too-small"}),
    ("buttons", "按钮", {"control-font-too-small", "missing-complete-button"}),
    ("auxiliary-text", "辅助说明", {"auxiliary-font-too-small"}),
    ("completion", "完成条件", {"missing-complete-button"}),
    ("message-contract", "消息协议", {"missing-post-message", "invalid-message-contract"}),
    ("browser-boundary", "浏览器复核边界", set()),
)


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def build_html_report(block_id: str, source: str, path: Path) -> dict:
    issues = validate_interactive_html(path)
    issue_codes = {issue.code for issue in issues}
    checks = []
    for check_id, label, codes in CHECKS:
        matching = [issue for issue in issues if issue.code in codes]
        if check_id == "browser-boundary":
            evidence = "静态检查已完成；仍需在真实 iframe 中完成浏览器检查"
        elif matching:
            evidence = "；".join(f"[{issue.code}] {issue.message}" for issue in matching)
        else:
            evidence = "静态检查通过"
        checks.append(
            {
                "code": check_id,
                "label": label,
                "status": (
                    "required"
                    if check_id == "browser-boundary"
                    else "revise" if matching else "pass"
                ),
                "evidence": evidence,
            }
        )
    return {
        "schemaVersion": "1.0",
        "blockId": block_id,
        "source": source,
        "sha256": _sha256(path),
        "checks": checks,
        "issues": [issue.as_dict() for issue in issues],
        "finalStatus": "revise" if issue_codes else "pass",
        "browserCheckRequired": True,
    }


def render_html_report(report: dict) -> str:
    lines = [
        f"# HTML 检查报告：{report.get('blockId', '')}",
        "",
        f"- 课程资源：`{report.get('source', '')}`",
        f"- 文件摘要：`{report.get('sha256', '')}`",
        f"- 静态结论：{report.get('finalStatus', 'invalid')}",
        "- 浏览器复核：仍需在真实 iframe 中完成浏览器检查",
        "",
        "| 检查项 | 结果 | 证据与修改建议 |",
        "|---|---|---|",
    ]
    for check in report.get("checks", []):
        label = str(check.get("label", "")).replace("|", "\\|")
        status = str(check.get("status", "invalid"))
        evidence = str(check.get("evidence", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {label} | {status} | {evidence} |")
    final_status = str(report.get("finalStatus", "invalid"))
    final_evidence = (
        "静态合同通过" if final_status == "pass" else "存在阻止上传的静态问题"
    )
    lines.append(f"| 最终结论 | {final_status} | {final_evidence} |")
    lines.append("")
    return "\n".join(lines)


def validate_html_report(
    report: object,
    block_id: str,
    source: str,
    path: Path,
) -> List[ValidationIssue]:
    if not isinstance(report, dict):
        return [
            ValidationIssue(
                str(path),
                "invalid-html-report",
                "HTML report must be an object",
            )
        ]
    issues: List[ValidationIssue] = []
    expected = build_html_report(block_id, source, path)
    for key in ("schemaVersion", "blockId", "source", "browserCheckRequired"):
        if report.get(key) != expected[key]:
            issues.append(
                ValidationIssue(
                    str(path),
                    "invalid-html-report",
                    f"HTML report field differs from current contract: {key}",
                )
            )
    if report.get("sha256") != expected["sha256"]:
        issues.append(
            ValidationIssue(
                str(path),
                "stale-html-report",
                "HTML report SHA-256 does not match the current HTML file",
            )
        )
    for key in ("checks", "issues", "finalStatus"):
        if report.get(key) != expected[key]:
            issues.append(
                ValidationIssue(
                    str(path),
                    "stale-html-report",
                    f"HTML report no longer matches current static checks: {key}",
                )
            )
    return issues
