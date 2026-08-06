---
name: design-video-interactions
description: Use when a platform course includes an MP4, long video, timed pause, in-video question, video prompt, or a planned video whose interactive checkpoints and completion behavior need definition.
---

# Design Video Interactions

## Scope

Design the structured interaction layer that accompanies a course video. 不得生成、剪辑、转码或修改 MP4.

## Workflow

1. Locate the source-coverage items and course position served by the video.
2. Confirm the video learning purpose and what the student should notice, decide, explain, or apply.
3. If the MP4 exists, resolve the runtime relative to this skill and read its 实际时长 with `scripts/validate-video-interactions.py` during validation.
4. If the final MP4 is unavailable, describe each pause with a 语义锚点, set `timeSeconds` to `null`, and set `status` to `needs-timing`.
5. For every event, define prompt, interaction type, options when applicable, graded answer or reflection rubric, feedback, and blocking behavior.
6. Fill [video-interaction-design-template.md](assets/video-interaction-design-template.md) and obtain 教师确认 for event purpose and placement.
7. Read [video-contract.md](references/video-contract.md). Write video interaction JSON first; JSON 是唯一事实源.
8. Generate the Markdown view with `scripts/render-video-interactions.py`. Do not maintain Markdown independently.
9. Run `scripts/validate-video-interactions.py COURSE_DIR INTERACTION_JSON`. Fix invalid ordering, repeated times, duration mismatch, and events outside the actual MP4.
10. If any event remains `needs-timing`, clearly report the course as provisional and 不得判为可上传.

## Return

Return the confirmed design, canonical JSON path, generated Markdown path, actual or expected duration, and validator result. Do not claim the video content itself was fact-checked unless a separate content review occurred.
