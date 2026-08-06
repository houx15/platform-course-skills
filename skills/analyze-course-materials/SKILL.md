---
name: analyze-course-materials
description: Use when converting teacher-provided Word, HTML, Markdown, text, PDF, presentation, or mixed-format materials into a platform course, before proposing course structure or when source coverage and missing information must be audited.
---

# Analyze Course Materials

## Purpose

Build a source-grounded inventory before course design. Preserve what the teacher supplied, expose unreadable inputs and conflicts, and make every later inclusion, merge, or approved discard traceable.

## Locate the runtime

Resolve paths relative to this `SKILL.md` directory:

1. Use sibling `../_course-toolkit/` when installed.
2. Otherwise use the toolkit source root at `../../`.
3. Stop and report a broken installation if neither contains `scripts/extract-materials.py`.

## Workflow

1. Inventory every teacher-selected input without modifying it. Ignore `*.zip` and record it as ignored.
2. Run `scripts/extract-materials.py` against DOCX, HTML, Markdown, and text inputs and persist the exact result at `.course-work/materials-extracted.json`.
3. Use available document-reading capabilities for PDF and presentations. If reliable extraction is unavailable, report the file and ask for DOCX, HTML, Markdown, or text. 不得静默跳过任何输入文件。
4. Summarize the extracted evidence with source file and location. Separate facts, examples, activities, questions, answers, media, and teacher notes.
5. Identify duplicate claims, conflicting claims, and information that is required by the platform but absent from the source.
6. Create or update `.course-work/source-coverage.json` using [source-coverage.md](references/source-coverage.md). It must contain exactly one entry for every item in `materials-extracted.json`. Start every extracted item as `unresolved`; never mark it resolved merely because a draft exists.
7. Scan for 长视频, MP4, timed pauses, video questions, simulations, experiments, drag, match, exploration, clicks, webpages, and HTML 交互.
8. Report detected video and HTML candidates with the source evidence that triggered each candidate.
9. 即使材料没有提到长视频或 HTML 交互，也 require the caller to ask the teacher explicitly whether either element is planned.

## Return to the caller

Return:

- input inventory with extracted, ignored, unsupported, and failed files;
- concise material understanding;
- conflicts and missing information;
- initial source-coverage path;
- detected video and HTML candidates;
- the two explicit media-intent questions if no candidate was found.

Do not propose final Part/Piece structure in this skill. Material understanding and complex-media intent must be confirmed first.
