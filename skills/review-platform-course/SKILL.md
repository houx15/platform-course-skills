---
name: review-platform-course
description: Use when a standardized platform course is believed complete, before upload, or when checking source coverage, course.json, generated Markdown, HTML interactions, video timing, resource paths, and unresolved teacher decisions.
---

# Review Platform Course

## Review independently

Do not accept the builder's completion claim. Reconstruct the evidence chain from originals, teacher confirmations, the storyboard, learner files, and referenced resources.

## Procedure

1. 重新读取原始材料 and all authoring records: `materials-extracted.json`, `source-coverage.json`, `audience-classification.json`, `course-storyboard.json`, `decisions.json`, `unresolved.json`, `session.json`, plus `course/course.json`, generated Markdown, HTML, video interaction data, and referenced assets. 忽略 ZIP everywhere.
2. Read [review-rubric.md](references/review-rubric.md).
3. Reconcile every extracted source ID against audience classification and coverage. Confirm non-student material stayed outside the learner course and every student item reaches real course blocks or has teacher-approved exclusion.
4. Compare every storyboard Piece with the actual Part/Piece/block structure and modality. Confirm `course.json` and `index.md` contain only final learner-facing material.
5. Resolve the runtime relative to this skill: prefer sibling `../_course-toolkit/`, otherwise source root `../../`.
6. Run:

   ```text
   scripts/validate-course.py course/ --work-dir .course-work --json
   ```

7. Perform a separate Part 逐项 Review for every Part. Inspect every Piece within it and record evidence for all six dimensions:

   - 教学目标与结构;
   - 内容完整性;
   - 学生呈现;
   - 模态选择;
   - 练习与反馈;
   - 资源与格式.

   任一维度 fails means that Part is `revise`; any `revise` Part blocks the whole course.
8. Perform the 整体 Review: all Parts pass, source classification/coverage, resources present, course JSON schema, index consistency, images, video, HTML, assessments, and unresolved decisions.
9. Persist the structured result at `.course-work/review-report.json`, then render `.course-work/review-report.md` with `scripts/render-review-report.py`.
10. Automatically fix only mechanical issues that cannot change teaching meaning: generated Markdown drift, deterministic formatting, and unambiguous safe-path corrections.
11. For pedagogical failures, provide concrete restructuring advice to the builder. The builder must produce a revised course-storyboard table. Ask the teacher to confirm any semantic change, then rebuild.
12. After any fix, 重新运行完整 Review from original sources through the deterministic validator and both tables. Never reuse a previous pass.

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

`review-report.json` may claim `uploadable` only when every Part dimension and every overall check passes. Static/content review can verify structure, traceability, and recorded pedagogical completeness; it 不能证明真实学习效果, subject-matter truth, or real iframe behavior without corresponding evidence.
