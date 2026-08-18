---
name: design-course-html
description: Use when a platform course needs a standalone HTML interaction, iframe learning activity, simulation, experiment, drag, match, click, or exploratory web task, before generating or reviewing the HTML file.
---

# Design Course HTML

## Core rule

Design the learning interaction before writing code. Do not treat a polished screen as evidence of a complete activity.

## Workflow

1. Read the source coverage and the candidate Piece. State which supplied material the interaction serves.
2. Establish the 学习目标, what the student sees, what the student does, meaningful states, feedback, assessment, completion condition, blocking behavior, and submitted interaction data.
3. Fill [interaction-design-template.md](assets/interaction-design-template.md). Surface only missing or outcome-changing decisions to the teacher.
4. Present the readable design and wait for 教师确认 before generating or materially revising HTML.
5. Read [html-contract.md](references/html-contract.md), then generate a 单个 HTML 文件 with embedded CSS and JavaScript.
6. Use a fixed `1:1` or 横向 4:3 canvas without horizontal scrolling or external runtime resources.
7. Set the `html` or `body` base text to at least `16px`. Content and controls must remain at least `16px`. Only explicit `.auxiliary` or `[data-text-role="auxiliary"]` text may be as small as `14px`; never use visible text below `14px`. Avoid font-size expressions the static validator cannot resolve.
8. Use a visible button labeled `完成` or `完成任务`. Enforce the confirmed completion condition before submission.
9. Implement the `mind-course-interaction` version `1.0` handshake. Receive the host's `sessionToken`, echo it with `protocol`, `version`, `type`, and `payload`, send `ready`, and submit `completed` with `correct` and/or JSON-compatible `value` learning evidence. An optional stable `resultId` supports duplicate detection; the host owns and stamps the Block `interactionId`. Do not use the legacy `INTERACTION_COMPLETE` message.
10. Resolve the runtime relative to this skill: prefer sibling `../_course-toolkit/`, otherwise source root `../../`. Run `scripts/validate-html.py HTML_FILE --course-definition-2` on the generated file.
11. Generate the persisted report with `scripts/generate-html-report.py HTML_FILE --block-id BLOCK_ID --source COURSE_RELATIVE_SOURCE --output-dir .course-work/html-reports/`. Both `<block-id>.json` and `<block-id>.md` must exist and match the current HTML SHA-256.
12. Fix every blocking validation issue, regenerate the report, and rerun the validator. Return the confirmed design, HTML path, report paths, and validator result.

## Evidence boundary

静态检查不能证明 the activity is visually reliable in the 真实 iframe or that students learn from it. `browserCheckRequired: true` remains in the HTML report. State that browser/platform verification and pedagogical review remain separate when they have not been performed.
