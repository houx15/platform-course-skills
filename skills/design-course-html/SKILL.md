---
name: design-course-html
description: Use when a platform course needs a standalone HTML interaction, iframe learning activity, simulation, experiment, drag, match, click, exploratory web task, or an existing HTML fails the platform message protocol.
---

# Design Course HTML

## Core rule

Design the learning interaction before writing code. Do not treat a polished screen as evidence of a complete activity.

When an existing HTML fails only because its iframe protocol is legacy or incomplete, repair it as an authoring task. The teacher is not the protocol implementer.

## Existing HTML protocol repair

1. Run `scripts/validate-html.py HTML_FILE --course-definition-2` before editing and record the issue codes.
2. Never mutate the teacher's only source file outside `course/`. Copy it into the intended `course/interactions/html/` path and directly edit the delivery copy. Before every first repair of those bytes, always create or reuse `.course-work/html-backups/<BLOCK_ID>/<ORIGINAL_SHA256>.html`, even on initial import; the filename is the original SHA-256 and is the rollback point.
3. Handle the compatibility work internally: do not ask the teacher to modify code or understand the protocol. Replace `INTERACTION_COMPLETE` and other legacy message plumbing with the adapter in [html-contract.md](references/html-contract.md). Queue frame messages created before the host handshake; never silently drop them while `sessionToken` is absent.
4. Treat protocol migration as a bounded compatibility repair: preserve the existing questions, answers, scoring, feedback, completion threshold, DOM, and CSS. Also preserve interaction order, state transitions, blocking behavior, and the exact moment completion becomes valid. Do not redesign the activity while repairing its envelope.
5. Map the legacy payload to learning evidence without inventing success:
   - graded activity: send its computed `correct` and retain available answer, score, and attempt data in `value`;
   - ungraded activity with student output or state: send that actual output or final state in `value`;
   - explicit completion-only activity: `value: { completed: true }` is sufficient when the source genuinely defines completion without grading;
   - apparently graded activity whose correct result or completion threshold cannot be derived: stop only for that true blocker, phrased as one teaching question rather than a protocol question.
6. After editing, rerun the HTML validator, regenerate the SHA-bound HTML report, recompile the course, rerun CourseDefinition 2.0 validation, and open the real renderer preview. Verify `ready`, token echo, `completed` evidence, one-time completion, navigation unlock, visible unmet requirements, no runtime errors, and unchanged activity semantics and appearance.

## Workflow

1. Read the source coverage and the candidate Piece. State which supplied material the interaction serves.
2. Establish the 学习目标, what the student sees, what the student does, meaningful states, feedback, assessment, completion condition, blocking behavior, and submitted interaction data.
3. Fill [interaction-design-template.md](assets/interaction-design-template.md). Record supported interaction choices as a source-backed AI draft. Ask only when correctness, required learning evidence, or completion behavior is a true blocker that cannot be inferred.
4. Persist the readable design and continue directly to HTML generation. The teacher judges the complete interaction in the renderer preview rather than approving the template first.
5. Read [html-contract.md](references/html-contract.md), then generate a 单个 HTML 文件 with embedded CSS and JavaScript.
6. Use a fixed `1:1` or 横向 4:3 canvas without horizontal scrolling or external runtime resources.
7. Set the `html` or `body` base text to at least `16px`. Content and controls must remain at least `16px`. Only explicit `.auxiliary` or `[data-text-role="auxiliary"]` text may be as small as `14px`; never use visible text below `14px`. Avoid font-size expressions the static validator cannot resolve.
8. Use a visible button labeled `完成` or `完成任务`. Enforce the source-backed completion condition before submission, and explain every unmet requirement visibly near the button.
9. Implement the `mind-course-interaction` version `1.0` handshake. Receive the host's `sessionToken`, echo it with `protocol`, `version`, `type`, and `payload`, send `ready`, and submit `completed` with `correct` and/or JSON-compatible `value` learning evidence. Queue outbound messages until the token arrives. An optional stable `resultId` supports duplicate detection; the host owns and stamps the Block `interactionId`. Do not use the legacy `INTERACTION_COMPLETE` message.
10. Resolve the runtime relative to this skill: prefer sibling `../_course-toolkit/`, otherwise source root `../../`. Run `scripts/validate-html.py HTML_FILE --course-definition-2` on the generated file.
11. Generate the persisted report with `scripts/generate-html-report.py HTML_FILE --block-id BLOCK_ID --source COURSE_RELATIVE_SOURCE --output-dir .course-work/html-reports/`. Both `<block-id>.json` and `<block-id>.md` must exist and match the current HTML SHA-256.
12. Fix every blocking validation issue, regenerate the report, and rerun the validator. Return the AI-draft design, HTML path, report paths, and validator result for renderer review.

## Evidence boundary

静态检查不能证明 the activity is visually reliable in the 真实 iframe or that students learn from it. `browserCheckRequired: true` remains in the HTML report. State that browser/platform verification and pedagogical review remain separate when they have not been performed.
