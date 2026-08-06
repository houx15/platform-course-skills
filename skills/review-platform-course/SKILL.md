---
name: review-platform-course
description: Use when a standardized platform course is believed complete, before upload, or when checking source coverage, course.json, generated Markdown, HTML interactions, video timing, resource paths, and unresolved teacher decisions.
---

# Review Platform Course

## Review independently

Do not accept the builder's completion claim. Reconstruct the evidence chain from files and teacher confirmations.

## Procedure

1. 重新读取原始材料, `.course-work/materials-extracted.json`, `source-coverage.json`, `decisions.json`, `unresolved.json`, `session.json`, `course/course.json`, generated Markdown, referenced media, HTML, and video interaction data. 忽略 ZIP everywhere.
2. Read [review-rubric.md](references/review-rubric.md).
3. Reconcile every extracted source ID against coverage. Verify every source item is mapped to a real `part-id/piece-id/block-id`, merged with real destinations, or explicitly discarded with teacher confirmation.
4. Verify every substantive AI addition in `decisions.json` has teacher confirmation and every open item marked blocking in `unresolved.json` remains a blocker.
5. Resolve the runtime relative to this skill: prefer sibling `../_course-toolkit/`, otherwise source root `../../`.
6. Run:

   ```text
   scripts/validate-course.py course/ --work-dir .course-work --json
   ```

7. Inspect content alignment in addition to the mechanical result: Part/Piece purpose, activity completeness, answers or rubrics, feedback, blocking meaning, and consistency with confirmed designs.
8. Automatically fix only mechanical issues that cannot change teaching meaning: generated Markdown drift, deterministic formatting, and unambiguous safe-path corrections.
9. Ask the teacher before deleting, merging, substantively rewriting, changing answers or rubrics, changing blocking rules, or changing media interaction design.
10. After any fix, 重新运行完整 Review from source coverage through the deterministic validator. Do not reuse a previous pass.

## Result

Return exactly one leading status:

- `可上传`
- `修改后可上传`
- `缺少必要材料，暂不可上传`

Then list blocking issues, auto-fixed issues, teacher decisions still needed, and the verification boundary. Static/content review can verify the contract and traceability; it 不能证明真实学习效果, real iframe behavior, or subject-matter truth without the corresponding evidence.
