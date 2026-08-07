---
name: analyze-course-materials
description: Use when converting teacher-provided Word, HTML, Markdown, text, PDF, presentation, or mixed-format materials into a platform course, before proposing course structure or when source coverage and missing information must be audited.
---

# Analyze Course Materials

## Purpose

Build a source-grounded inventory and decide who each source item is for before designing the student course. Preserve the originals, surface unreadable inputs and conflicts, and prevent teacher notes or system instructions from leaking into learner content.

## Locate the runtime

Resolve paths relative to this `SKILL.md` directory:

1. Use sibling `../_course-toolkit/` when installed.
2. Otherwise use the toolkit source root at `../../`.
3. Stop and report a broken installation if neither contains `scripts/extract-materials.py`.

## Workflow

1. Inventory every teacher-selected input without modifying it. Ignore `*.zip` and record it as ignored.
2. Run `scripts/extract-materials.py` against DOCX, HTML, Markdown, and text inputs. Persist the exact result at `.course-work/materials-extracted.json`.
3. Use available document-reading capabilities for PDF and presentations. If reliable extraction is unavailable, report the exact file and request DOCX, HTML, Markdown, or text. 不得静默跳过任何输入文件。
4. Summarize evidence with source file, stable source ID, and original location. Preserve DOCX table row/cell structure. Separate concepts, facts, examples, evidence, activities, questions, answers, media notes, teacher notes, and system rules.
5. Identify duplicate claims, conflicts, unsupported claims, and missing information that would change the learning goal, correct answer, feedback, or media behavior.
6. Create `.course-work/source-coverage.json` using [source-coverage.md](references/source-coverage.md). It must contain exactly one entry for every extracted item.
7. Create `.course-work/audience-classification.json`. Classify every source ID exactly once into:

   - `student-core`: concepts, explanations, tasks, or conclusions that students need;
   - `student-evidence`: examples, cases, data, quotations, or sources students need to inspect;
   - `teacher-design`: teaching intent, facilitation notes, lesson planning, or teacher-only explanations;
   - `ai-system`: AI role, system behavior, platform fields, generation rules, or implementation notes;
   - `reference`: provenance or background material that supports authoring but should not be copied into the course;
   - `proposed-exclusion`: redundant, obsolete, contradictory, or unsuitable content proposed for omission.

8. Present a concise grouped summary. Ask for one 分组确认 covering `teacher-design`, `ai-system`, `reference`, and `proposed-exclusion`; do not burden the teacher with one question per source item. Record `teacherConfirmed: true` only after the teacher approves the grouped classification.
9. Scan the student material for 长视频, MP4, timed pauses, video questions, simulations, experiments, drag, match, exploration, clicks, webpages, and HTML 交互.
10. Report detected video and HTML candidates with source evidence. 即使材料没有提到长视频或 HTML 交互, require the caller to ask explicitly whether either element is planned.

## Audience record

Use this shape:

```json
{
  "schemaVersion": "1.0",
  "teacherConfirmed": true,
  "groups": [
    {
      "audience": "student-core",
      "sourceIds": ["source-..."],
      "summary": "学生需要掌握的核心内容",
      "disposition": "storyboard"
    }
  ]
}
```

`student-core` and `student-evidence` use `storyboard`; `teacher-design`, `ai-system`, and `reference` use `work-record`; `proposed-exclusion` uses `exclude`.

## Return to the caller

Return a teacher-readable material summary, grouped audience classification, conflicts and missing information, detected video/HTML candidates, and explicit media-intent questions. Do not propose the final Part/Piece structure here. The caller must obtain the classification and media-intent confirmations first.
