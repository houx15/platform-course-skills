---
name: review-platform-course
description: Use when a standardized platform course is believed complete, before upload, or when checking source coverage, course.json, generated Markdown, PDF documents, HTML interactions, video timing, resource paths, and unresolved teacher decisions.
---

# Review Platform Course

## Review independently

Do not accept the builder's completion claim. Reconstruct the evidence chain from originals, teacher confirmations, the storyboard, learner files, and referenced resources.

## Procedure

1. 重新读取原始材料 and all authoring records: `materials-extracted.json`, `source-coverage.json`, `audience-classification.json`, `course-storyboard.json`, `decisions.json`, `unresolved.json`, `session.json`, plus `course/course.json`, generated Markdown, HTML, video interaction data, and referenced assets. 忽略 ZIP everywhere.
2. Read [review-rubric.md](references/review-rubric.md).
3. Reconcile every extracted source ID against audience classification and coverage. Confirm non-student material stayed outside the learner course and every student item reaches real course blocks or has teacher-approved exclusion.
4. Compare the storyboard `courseFrame` and every Piece with `course.json`. Require the introduction and conclusion to match exactly. Verify each course objective has exactly one alignment record, links the 目标与真实 Part, and points to at least one real 学习证据 Block inside those aligned Parts. Static text, images, and PDF cannot count as learning evidence by themselves. Then compare the actual Part/Piece/block structure and modality. Confirm `course.json` and `index.md` contain only final learner-facing material.
5. Resolve the runtime relative to this skill: prefer sibling `../_course-toolkit/`, otherwise source root `../../`.
6. Run:

   ```text
   scripts/validate-course.py course/ --work-dir .course-work --json
   ```

7. Inspect every video Block, including videos without interaction JSON. Require MP4 container, H.264 video, AAC audio when audio exists, and faststart. `unsupported-video-codec`, `unsupported-audio-codec`, `missing-faststart`, and an unverified video profile mean `缺少必要材料，暂不可上传`. Show `long-video`, `sparse-video-interactions`, and `large-video` as separate teacher-facing warnings; these do not by themselves fail the course. For a video 超过 10 分钟, inspect whether the checkpoint gaps are pedagogically justified rather than adding arbitrary pauses.
8. Inspect every HTML Block and its `.course-work/html-reports/<block-id>.json` and `.md`. Require current SHA-256, all static checks passing, base/content/control text at least `16px`, explicit auxiliary text at least `14px`, and a deterministic Markdown match. A missing report or `stale-html-report` blocks full Review. The report cannot replace testing in the 真实 iframe.
9. Inspect 逐个 PDF Block. Require a real safe relative file path, `.pdf` extension, `%PDF-` header, `%%EOF` trailer, a learner-facing title, and a confirmed Piece purpose that explains what students locate, compare, or verify. When the teacher requires the 完整文档, confirm it was not replaced by a summary, excerpt screenshot, reconstructed file, or unconfirmed substitute. A missing, damaged, mislinked, or substituted PDF blocks upload.
10. Perform a separate Part 逐项 Review for every Part. Inspect every Piece within it and record evidence for all six dimensions:

   - 教学目标与结构;
   - 内容完整性;
   - 学生呈现;
   - 模态选择;
   - 练习与反馈;
   - 资源与格式.

   任一维度 fails means that Part is `revise`; any `revise` Part blocks the whole course.
11. Perform the 整体 Review: all Parts pass, source classification/coverage, resources present, course JSON schema, index consistency, `courseIntroduction`, `courseConclusion`, images, video, HTML, assessments, and unresolved decisions. `courseIntroduction` must verify the first learner screen, student-facing overview/objectives/key points, and fixed `开始学习` action. `courseConclusion` must verify the final summary/takeaways/transfer applications, source consistency, and absence of unsupported claims that a student has already mastered the course. Also execute the 整体 `pdf` Review. If no PDF is used, `pdf` may pass only with evidence that neither the storyboard nor confirmed teacher requirements need one.
12. Persist the structured result at `.course-work/review-report.json`, then render `.course-work/review-report.md` with `scripts/render-review-report.py`.
13. Automatically fix only mechanical issues that cannot change teaching meaning: generated Markdown drift, deterministic formatting, and unambiguous safe-path corrections.
14. For pedagogical failures, provide concrete restructuring advice to the builder. The builder must produce a revised course-storyboard table. Ask the teacher to confirm any semantic change, then rebuild.
15. A `schemaVersion` 1.0 course must return `migration-required`; migrate it to 1.1, draft the missing course frame from source evidence, and obtain teacher confirmation before it can pass. Do not silently infer approval from old content.
16. After any fix, 重新运行完整 Review from original sources through the deterministic validator and both tables. Never reuse a previous pass.

## Required result tables

First show one row per Part:

| Part | 标题 | 教学目标与结构 | 内容完整性 | 学生呈现 | 模态选择 | 练习与反馈 | 资源与格式 | 结论 | 修改建议 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

Then show the overall result:

| 检查项 | 结果 | 证据 |
| --- | --- | --- |

## Status

Return exactly one leading status:

- `可上传`
- `修改后可上传`
- `缺少必要材料，暂不可上传`

`review-report.json` may claim `uploadable` only when every Part dimension and every overall check passes. 静态检查不能证明 PDF 每一页能在真实平台中正确渲染、文件是权威出版版本，或学生已经阅读理解；真实上传前仍需测试平台内嵌阅读和下载。 Static/content review can verify structure, traceability, and recorded pedagogical completeness; it 不能证明真实学习效果, subject-matter truth, or real iframe behavior without corresponding evidence.
