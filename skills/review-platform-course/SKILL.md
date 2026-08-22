---
name: review-platform-course
description: Use when a CourseDefinition 2.0 course has current G6 validation and G7 renderer preview evidence and needs an independent, source-backed decision before publication.
---

# Review Platform Course

Review independently from the builder. Re-read the current evidence and record what you personally verified; do not convert the builder's confidence, contract success, or page polish into a pass.

## Start from current evidence

1. Run `python _course-toolkit/scripts/course-workflow.py status ROOT --json`. Require completed G7 and no invalidated earlier gate.
2. 重新读取原始材料并忽略 ZIP. Read the approved `.course-work/course-blueprint.json`, `source-coverage.json`, `audience-classification.json` when present, `course-storyboard.json` when present, `decisions.json`, `unresolved.json`, `course/course.json`, `.course-work/course-validation-report.json`, `.course-work/preview-manifest.json`, and `.course-work/annotations.json`.
3. Read [review-rubric.md](references/review-rubric.md), then run:

   ```bash
   python _course-toolkit/scripts/review-course-v2.py prepare ROOT --json
   ```

   This rejects a legacy CourseDefinition or review schema as `migration-required`, stale G6/G7 hashes, unresolved teacher decisions, and invalid objective evidence. It writes a hash-bound `.course-work/review-report.json` scaffold. It does not make the pedagogical judgment for you.

## Review each Part and Slice

For every Part, complete all six dimensions with `pass|revise` and concrete evidence:

- 教学目标与结构 (`instructionalGoalStructure`);
- 内容完整性 (`contentCompleteness`);
- 学生呈现 (`studentFacingPresentation`);
- 模态选择 (`modalityChoice`);
- 练习与反馈 (`practiceFeedback`);
- 资源与格式 (`resourcesFormat`).

Within every Part, review every Slice's content purpose, one-screen desktop layout, workflow reachability and meaningful branches, interaction completion, and media behavior. When the approved storyboard contains `teachingDesign`, independently verify that the rendered course still teaches the named methodology before asking for independent practice, includes a real worked model and scaffolding, advances the cumulative learner artifact, follows the approved learning arc, avoids repetitive test-like question pairs, and reaches the transfer task. When `sliceSemanticReview` is present, compare the runtime course against its per-Slice context and adjacent-page connections; the plan record itself is not proof that the renderer expresses them. Its absence from a legacy approved course is not a review failure. Inspect actual G7 runtime events and errors. 任一维度 or Slice check marked `revise` makes the Part fail and blocks G8.

Check each objective against its exact `evidenceBlockIds`, linking the 目标与真实 Part and at least one 学习证据 Block. That Block must sit inside a Part aligned to the objective and collect a real result; static text, images, or PDF alone do not count.

## Overall Review

Complete every `overallChecks` item. Confirm source classification and coverage, teacher decisions, resources, the shared CourseDefinition 2.0 contract, objective evidence, layout/workflow, PDF, video, HTML, preview runtime, and unresolved items.

- Review every PDF Block against the original 完整文档. Require safe `.pdf`, `%PDF-`, `%%EOF`, a learner purpose, and G7 reading/download behavior. Static checks cannot prove every page or publication authority.
- Review video codec/timing evidence and real preview behavior, including auto-pause and modal interactions. `unsupported-video-codec`, `unsupported-audio-codec`, `missing-faststart`, out-of-range cues, or incomplete required cues block. `long-video` and `large-video` remain explicit warnings, not silent passes.
- Review HTML source, current validation evidence, the iframe completion/student-data protocol, capabilities, and real iframe behavior. When `capabilities.audio` is true, verify host lifecycle audio control and user-gesture behavior. Text must follow the 16px / 14px rules. A stale or missing report/evidence blocks; 静态检查不能证明真实 iframe behavior.
- Review the opening and closing fallback content without claiming actual learner mastery. Confirm all layouts, workflow actions/transitions, navigation behavior, and one-screen density in the real renderer.

## Record and verify

1. Fill the prepared JSON. Use `status: pass` only with a non-empty, specific evidence sentence. Set the overall `status` to `publishable` only when every Part, Slice, objective, and overall check passes. Otherwise keep `blocked` and return findings to `build-platform-course`.
2. Run:

   ```bash
   python _course-toolkit/scripts/review-course-v2.py verify ROOT --json
   ```

   This verifies current hashes and renders `.course-work/review-report.md`.
3. Only after verification succeeds, run:

   ```bash
   python _course-toolkit/scripts/course-workflow.py complete-gate ROOT G8 --json
   ```

   G8 completion writes renderer-backed publication review evidence for the exact definition, validation report, preview manifest, and review report.

## Teacher-facing result

Lead with exactly one result: `可上传` or `缺少必要材料，暂不可上传`. Show a Part table and an overall table with concrete findings. 重新运行完整 Review after any content, asset, decision, validation, preview, annotation, or renderer change. Independent review 不能证明真实学习效果 or subject-matter truth without corresponding evidence, and it never uploads or publishes.
