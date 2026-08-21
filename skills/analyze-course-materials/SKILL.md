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
5. Identify duplicate claims, conflicts, unsupported claims, and missing information that would change the learning goal, correct answer, feedback, or media behavior. Specifically extract any teacher-provided `课程目标`, `课程总结`, and `学生收获`. Preserve their source IDs and 区分教师意图与学生措辞: the former is authoring evidence, while the latter must later be rewritten as concise learner-facing prose and bullets. If one is absent but a reasonable version follows from the content, record it as AI-proposed rather than confirmed. Ask only when no reliable learning purpose or correctness can be inferred.
6. Create `.course-work/source-coverage.json` using [source-coverage.md](references/source-coverage.md). It must contain exactly one entry for every extracted item. Every teacher-supplied asset must end with an explicit disposition: use on a named planned Slice, keep as optional/supporting material, exclude with a reason, or block because its purpose cannot be determined. Never silently omit inconvenient material.
7. Create `.course-work/audience-classification.json`. Classify every source ID exactly once into:

   - `student-core`: concepts, explanations, tasks, or conclusions that students need;
   - `student-evidence`: examples, cases, data, quotations, or sources students need to inspect;
   - `teacher-design`: teaching intent, facilitation notes, lesson planning, or teacher-only explanations;
   - `ai-system`: AI role, system behavior, platform fields, generation rules, or implementation notes;
   - `reference`: provenance or background material that supports authoring but should not be copied into the course;
   - `proposed-exclusion`: redundant, obsolete, contradictory, or unsuitable content proposed for omission.

8. Persist a concise grouped summary with `teacherConfirmed: false`. Return it to the director so it can build the complete page plan. Do not ask the teacher to confirm inventory categories separately; the teacher will confirm the combined Part/Slice plan, material placement, and exclusions once.
9. For every PDF, distinguish two separate intents: `构建输入`, where its content is extracted and reorganized, and `学生完整材料`, where learners must receive the unchanged complete file. The same PDF may serve both intents, but record them separately. If the material says 论文原文、原始报告、完整政策文件、附件供学生阅读, or asks learners to return to a primary source, identify a 完整 PDF candidate and 主动建议 `pdf` Block. Infer the exact file when source context is clear; ask only when multiple candidates imply different learner tasks. Do not infer that a summary or screenshot satisfies a complete-document request.
10. If a PDF cannot be read reliably, state that limitation. It can still be recorded as a complete delivery asset when its student-facing purpose is explicit, but do not claim its subject content was understood or use it to invent explanations, answers, or citations.
11. Scan the student material for 长视频, MP4, timed pauses, video questions, simulations, experiments, drag, match, exploration, clicks, webpages, and HTML 交互. For every supplied video, inventory the filename, 文件大小, declared or measurable duration, 封装格式, 视频编码, 音频编码, and whether `faststart` can be verified. Record unknown properties explicitly; do not infer compliance from a `.mp4` suffix.
12. Report detected video and HTML candidates with source evidence. If the supplied materials contain neither, record that none was detected and continue; ask only when the materials refer to a missing or ambiguous media item.
13. Return the extracted goal, summary, and gains as authoring evidence, not ready-to-publish learner copy. Flag contradictions such as a stated objective that no student activity or source content can support.

## Audience record

Use this shape:

```json
{
  "schemaVersion": "1.0",
  "teacherConfirmed": false,
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

Return a teacher-readable material summary, one disposition for every source item, grouped audience classification, course-goal/summary/gains evidence and gaps, conflicts and missing information, complete-PDF candidates, detected video/HTML candidates, and only genuinely blocking questions. Do not separately ask the teacher to approve this analysis; the caller incorporates it into the one page-plan confirmation.
