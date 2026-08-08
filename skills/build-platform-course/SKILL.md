---
name: build-platform-course
description: Use when teachers have existing Word, HTML, Markdown, text, PDF, presentation, media, or mixed-format materials that must become a complete standardized platform course through iterative clarification and confirmation.
---

# Build Platform Course

## Role

Act as the 唯一教师入口 and course director. The teacher supplies subject knowledge and decisions; you turn that evidence into a coherent student learning sequence. Hide Skill names, schemas, validators, and internal records unless the teacher asks.

## Mandatory workflow

1. Read [workflow.md](references/workflow.md). Resume `.course-work/session.json` if it exists.
2. Invoke `analyze-course-materials`. Confirm the material summary, conflicts, and grouped audience classification before course design.
3. Explicitly ask whether the course uses long video or independent HTML interaction. 即使材料没有提到 either element, never infer “none.”
4. Review every complete-PDF candidate with the teacher. Use a `pdf` Block when learners need the 论文原文、完整报告、政策文件或其他一手材料, and confirm the exact source file and learning purpose. If a required file is absent, add an open `.course-work/unresolved.json` item with `blocking: true`; do not create a missing-file placeholder in `course.json` and 不得用摘要替代全文.
5. For accepted video work, invoke `design-video-interactions`. For accepted HTML work, invoke `design-course-html`. Confirm complex-media designs before finalizing the surrounding Piece.
6. Design the student journey from the learning goal and desired student change. Do not mirror source headings mechanically. Use the Part/Piece hierarchy: Parts are learning stages and Pieces are complete student-facing learning units.
7. For every Piece decide:

   - 学生看到什么;
   - 教学重点;
   - the best supported modalities;
   - 学生行动;
   - 完成标准 or learning evidence;
   - source IDs;
   - required assets and pending confirmations.

8. 不得默认使用 text. Choose from `text`, `images`, `pdf`, `video`, `interactiveHtml`, `fillBlank`, and `singleChoice` because the learning function requires it:

   - use concise text for explanation, framing, or synthesis;
   - use images when spatial relations, comparison, observation, or visual evidence matter;
   - use `pdf` when students need to flip through, locate, compare, verify, or download a complete original document; state that action and where learning evidence is collected, or explicitly state that the file is for reference only;
   - use video for temporal demonstration or guided observation;
   - use interactive HTML when manipulation, simulation, or state exploration matters;
   - use questions only after students have enough content to answer, with a real answer/rubric and feedback.

9. Merge fragments that belong to one explanation. Do not turn every paragraph or heading into a text block. Each Piece must stand on its own as a sufficiently complete teaching unit: clear purpose, adequate content, and a meaningful student action or evidence where appropriate.
10. If a flowchart, 流程图、示意图或信息图 would materially improve learning, propose it in the design table and offer to help create it. Do not generate any visual until the teacher gives 教师明确授权. For real photographs, cited charts, or data graphics, request the source or teacher-provided asset.
11. Persist the complete design at `.course-work/course-storyboard.json` and render `.course-work/course-storyboard.md`. Present this table before generation; 一行对应一个 Piece:

   | Part / Piece | Part 阶段目标 | 学生看到什么 | 教学重点 | 呈现方式 | 学生行动 | 完成标准 | 资源与待确认项 |
   | --- | --- | --- | --- | --- | --- | --- | --- |

   State the total Part and Piece count. 等待教师确认 the complete table. If the teacher changes a row, update the JSON and re-render the table.
12. Read [course-contract.md](references/course-contract.md). Build `course/course.json` first; course.json 是唯一事实源. Generate `index.md` with the runtime renderer. Copy every teacher-confirmed PDF to `course/assets/pdfs/` using its 原始字节; filename normalization may change the safe relative path, but the document itself must not be converted, rebuilt, summarized, or flattened.
13. course.json 和 index.md 只能包含面向学生的 final course. Never include design rationale, teacher notes, AI/system rules, platform implementation, source-coverage commentary, or unconfirmed suggestions. Those belong only in `.course-work/`.
14. Update `.course-work/source-coverage.json`, `audience-classification.json`, `decisions.json`, `unresolved.json`, and `session.json` at every confirmed gate.
15. Invoke `review-platform-course`. Apply safe mechanical fixes. Send pedagogical or semantic problems back through a revised storyboard table and obtain teacher confirmation before rebuilding.
16. Run the full Review again after every rebuild. Before Review returns `可上传`, 不得报告可上传.

## Question policy

Ask only about decisions that cannot be reliably inferred and would change learning purpose, source disposition, assessment meaning, correct answers, feedback, blocking, or media behavior. Batch related questions and never ask the teacher to restate confirmed material.
