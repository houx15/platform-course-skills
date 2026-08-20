---
name: design-video-interactions
description: Use when a platform course includes a video, an incompatible or unusually large video file, timed pause, in-video question, video prompt, or a planned video whose platform profile, interactive checkpoints, and completion behavior need definition.
---

# Design Video Interactions

## Scope

Validate and encode the structured interaction layer that accompanies a course video. Never invent a video question. Use only teacher-provided video questions; when none were supplied, emit no video interaction and continue with an ordinary video Block. When the supplied file is incompatible or unusually large, this Skill may also prepare a platform-compatible candidate after the teacher approves the exact processing plan. Never overwrite, delete, crop, trim, or otherwise edit the original file.

## Safe video processing

1. Inspect the source with `ffprobe`. Report its exact path, container, video codec, pixel format, audio codec or absence of audio, duration, resolution, frame rate, and file size. If the format is incompatible or the teacher wants a smaller file, say plainly: 可以使用 `ffmpeg` 帮忙处理. Explain the compatibility problem or size tradeoff instead of presenting conversion as mandatory merely because the file exceeds `500 MiB`.
2. Before running `ffmpeg`, present the exact input path, new candidate path, proposed output profile, preserved properties, and expected tradeoff. Obtain explicit teacher approval for that exact operation. The main course Agent may perform the approved work in the current task; do not force a separate session. An internal subagent is optional implementation detail and receives no broader authority.
3. 原视频保持不变并作为回滚备份. Do not make a second full copy merely to call it a backup. Write an append-only processing manifest at `.course-work/video-backups/<BLOCK_ID>-<SOURCE_SHA256>-<CANDIDATE_ID>.json` containing the immutable source path, SHA-256, probe facts, approved operation, and intended candidate path. Never replace an earlier manifest for the same Block. If the original cannot remain available at that path, stop and agree on a different rollback location before processing.
4. Recalculate the source SHA-256 immediately before ffmpeg and compare it with the approved manifest. A mismatch invalidates approval and requires a new probe and plan. Write only to a distinct 候选视频 path under `.course-work/video-candidates/<BLOCK_ID>/`. Use `ffmpeg -n`; never use overwrite mode. A normal compatibility candidate keeps the complete sequence, duration, resolution, and frame rate, adds no subtitles, watermark, intro, or outro, and uses MP4, H.264, `yuv420p`, AAC when audio exists, and faststart. A safe reference command is:

   ```bash
   ffmpeg -n -i input-video \
     -map 0:v:0 -map 0:a? \
     -c:v libx264 -pix_fmt yuv420p -preset medium -crf 23 \
     -c:a aac -b:a 128k -movflags +faststart \
     candidate-video-platform.mp4
   ```

5. Probe the candidate again and compare path, SHA-256, container, codecs, pixel format, duration, resolution, frame rate, file size, faststart, and duration difference with the original. A candidate that is corrupt, materially shorter, or violates the approved plan is rejected. If it still exceeds `500 MiB`, report that result. When size reduction was the approved goal and the result does not meet it, propose a separate second plan and wait; do not silently run repeated compression.
6. Present the before/after facts and candidate path, and ask the teacher to play the candidate. The rule is: teacher confirms the processed video before updating the Blueprint. Persist that exact adoption decision at `.course-work/video-processing-decisions/<BLOCK_ID>-<CANDIDATE_SHA256>.json`, including source hash, candidate hash, probe facts, teacher response, and timestamp. Until that record exists, do not move the candidate into `course/assets/videos/`, change a Video Block, change interaction JSON, or treat it as a course asset. Any later candidate change invalidates the decision.
7. After confirmation, use a no-clobber copy to place the confirmed candidate at its final course-relative asset path. If that path already exists with the same SHA-256, reuse it; if the hash differs, choose a new stable relative path and update the Blueprint instead of overwriting the existing course asset. Then use the new final file to 语义锚点逐个重新核对 every existing interaction. For each event, record old time, semantic anchor, new time, and verification evidence in the interaction design. 不得按时长比例机械缩放 timestamps. Regenerate the canonical interaction JSON and Markdown view, recompile, rerun G6 validation, and require a real preview of playback, pauses, modal interactions, and completion before upload.

## Workflow

1. Locate the source-coverage items and course position served by the video.
2. Record the teacher's stated video learning purpose as a source-backed AI draft. Extract only teacher-provided video questions and their intended placement. Do not propose, infer, or add a checkpoint from the video content, its duration, or a general learning objective. If there is no teacher-provided question, record `no video interaction` and continue. Ask only when ambiguity in a supplied question is a true blocker.
3. If the MP4 exists, resolve the runtime relative to this skill and read its 实际时长 with `scripts/validate-video-interactions.py` during validation. The final file must use an MP4 container, H.264 video, AAC audio when audio exists, and `faststart`; an unverified or incompatible profile blocks upload.
4. If the final MP4 is unavailable, describe each pause with a 语义锚点, set `timeSeconds` to `null`, and set `status` to `needs-timing`.
5. For every teacher-provided event, preserve its prompt, interaction type, options, graded answer or reflection rubric, feedback, and blocking behavior. Complete only contract fields that can be derived without changing the question.
6. When the actual duration 超过 10 分钟, report `long-video` as a warning. Do not use duration or sparse coverage as permission to propose questions, add pauses, or interrupt playback；不要建议增加交互点. `sparse-video-interactions` is informational and never an invitation to invent content.
7. When the file exceeds `500 MiB`, return the `large-video` warning and carry it into the preview handoff. File size alone is not a blocker in this toolkit; do not stop solely for warning acknowledgement. Offer the safe processing path above when conversion or compression would be useful.
8. When teacher-provided interactions exist, fill [video-interaction-design-template.md](assets/video-interaction-design-template.md), persist their purpose and placement as an AI draft, and continue to JSON generation. Ask only when the supplied question cannot support correct timing, answers, or blocking behavior. When no interaction exists, do not create interaction JSON merely to populate the workflow.
9. Read [video-contract.md](references/video-contract.md). Write video interaction JSON first; JSON 是唯一事实源.
10. Generate the Markdown view with `scripts/render-video-interactions.py`. Do not maintain Markdown independently.
11. Run `scripts/validate-video-interactions.py COURSE_DIR INTERACTION_JSON`. Fix invalid ordering, repeated times, duration mismatch, profile blockers, and events outside the actual MP4.
12. If any event remains `needs-timing`, or the final media profile cannot be verified as MP4/H.264/AAC/faststart, clearly report the course as provisional and 不得判为可上传.

## Return

Return the AI-draft design, canonical JSON path, generated Markdown path, actual or expected duration, and validator result for renderer review. Do not claim the video content itself was fact-checked unless a separate content review occurred.
