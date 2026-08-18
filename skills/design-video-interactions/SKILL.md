---
name: design-video-interactions
description: Use when a platform course includes an MP4, long video, timed pause, in-video question, video prompt, or a planned video whose interactive checkpoints and completion behavior need definition.
---

# Design Video Interactions

## Scope

Design the structured interaction layer that accompanies a course video. 不得生成、剪辑、转码或修改 MP4.

## Workflow

1. Locate the source-coverage items and course position served by the video.
2. Infer the video learning purpose and what the student should notice, decide, explain, or apply from source coverage. Record it as a source-backed AI draft; ask only when the intended evidence or correct answer is a true blocker.
3. If the MP4 exists, resolve the runtime relative to this skill and read its 实际时长 with `scripts/validate-video-interactions.py` during validation. The final file must use an MP4 container, H.264 video, AAC audio when audio exists, and `faststart`; an unverified or incompatible profile blocks upload.
4. If the final MP4 is unavailable, describe each pause with a 语义锚点, set `timeSeconds` to `null`, and set `status` to `needs-timing`.
5. For every event, define prompt, interaction type, options when applicable, graded answer or reflection rubric, feedback, and blocking behavior.
6. When the actual duration 超过 10 分钟, tell the teacher and review the whole timeline for stretches longer than 10 minutes without a meaningful checkpoint. 建议增加交互点 only where a pause helps students notice, retrieve, predict, decide, or apply; do not add arbitrary interruptions to satisfy a count. A `long-video` or `sparse-video-interactions` result is a warning, not an upload blocker.
7. When the file exceeds `500 MiB`, return the `large-video` warning and carry it into the preview handoff. File size alone is not a blocker in this toolkit; do not stop solely for warning acknowledgement.
8. Fill [video-interaction-design-template.md](assets/video-interaction-design-template.md), persist event purpose and placement as an AI draft, and continue to JSON generation. Ask only when the source cannot support event correctness, placement, or blocking behavior.
9. Read [video-contract.md](references/video-contract.md). Write video interaction JSON first; JSON 是唯一事实源.
10. Generate the Markdown view with `scripts/render-video-interactions.py`. Do not maintain Markdown independently.
11. Run `scripts/validate-video-interactions.py COURSE_DIR INTERACTION_JSON`. Fix invalid ordering, repeated times, duration mismatch, profile blockers, and events outside the actual MP4.
12. If any event remains `needs-timing`, or the final media profile cannot be verified as MP4/H.264/AAC/faststart, clearly report the course as provisional and 不得判为可上传.

## Return

Return the AI-draft design, canonical JSON path, generated Markdown path, actual or expected duration, and validator result for renderer review. Do not claim the video content itself was fact-checked unless a separate content review occurred.
