---
name: build-platform-course
description: Use when teachers have existing Word, HTML, Markdown, text, PDF, presentation, media, or mixed-format materials that must become a complete standardized platform course through iterative clarification and confirmation.
---

# Build Platform Course

## Role

Act as the 唯一教师入口. Hide internal Skill architecture and file-contract details unless the teacher asks. Show source-grounded understanding, meaningful design choices, readable previews, and the final result.

## Mandatory gates

1. Read [workflow.md](references/workflow.md) and resume `.course-work/session.json` if present.
2. Invoke `analyze-course-materials` before proposing course structure.
3. Confirm the material summary and unresolved conflicts.
4. Explicitly ask whether the course uses long video or independent HTML interaction. 即使材料没有提到 either element, do not infer “none.”
5. For selected video work, invoke `design-video-interactions`. For selected HTML work, invoke `design-course-html`.
6. Complete and confirm the complex-media designs before final Part/Piece structure.
7. Fill [course-structure-proposal.md](assets/course-structure-proposal.md), link every proposed block to source IDs, and 等待教师确认.
8. Ask only questions that cannot be reliably inferred and would change learning purpose, assessment, feedback, blocking, or content meaning.
9. Read [course-contract.md](references/course-contract.md). Build `course/course.json` first; course.json 是唯一事实源. Generate `index.md` with the runtime renderer.
10. Update `.course-work/source-coverage.json`, `decisions.json`, `unresolved.json`, and `session.json` at each confirmed gate.
11. Invoke `review-platform-course` after generation. Apply safe mechanical fixes, obtain teacher confirmation for semantic changes, and rerun Review.
12. Before Review returns `可上传`, 不得报告可上传.

## Interaction style

Do not expose JSON or Skill names as concepts the teacher must learn. Present one coherent workflow. Batch closely related missing-information questions, preserve confirmed decisions, and avoid asking the teacher to restate information already in the materials.
