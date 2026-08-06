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
7. Use a visible button labeled `完成` or `完成任务`. Enforce the confirmed completion condition before submission.
8. Submit `INTERACTION_COMPLETE` version `1.0` with lesson ID, total duration, and structured interactions.
9. Resolve the runtime relative to this skill: prefer sibling `../_course-toolkit/`, otherwise source root `../../`. Run `scripts/validate-html.py` on the generated file.
10. Fix every blocking validation issue and rerun the validator. Return the confirmed design, HTML path, and validator result.

## Evidence boundary

静态检查不能证明 the activity is visually reliable in the real platform iframe or that students learn from it. State that browser/platform verification and pedagogical review remain separate when they have not been performed.
