# Video interaction contract

Use one JSON file and one generated Markdown view per interactive MP4.

```json
{
  "schemaVersion": "1.0",
  "video": {
    "title": "视频标题",
    "source": "assets/videos/example.mp4",
    "durationSeconds": 195,
    "events": [
      {
        "id": "credibility-check",
        "timeSeconds": 8,
        "blocking": true,
        "prompt": "视频中的内容一定可信吗？",
        "interaction": {
          "type": "singleChoice",
          "options": [
            {"id": "credible", "label": "可信"},
            {"id": "not-credible", "label": "不可信"}
          ],
          "assessment": {"mode": "survey"}
        }
      }
    ]
  }
}
```

Rules:

- Resolve `source` from the `course/` root.
- The Video Block `source` and `video.source` in its interaction JSON must resolve to the same file. A mismatch blocks Review.
- Keep event IDs unique.
- Put finalized events in strictly increasing time order.
- Do not reuse one timestamp for two events.
- Keep every finalized time below the actual MP4 duration.
- Use `graded`, `survey`, or `reflection` assessment consistently.
- A provisional event requires non-empty `anchor`, null `timeSeconds`, and `status: needs-timing`.
- Final Review blocks every provisional event.
- The final asset uses an MP4 container, H.264 (`avc1` or `avc3`) video, AAC (`mp4a`) audio when an audio track exists, and faststart (`moov` before `mdat`). Silent H.264 MP4 is allowed.
- An unverified container/codec profile, unsupported video codec, unsupported audio codec, or missing faststart blocks upload.
- Duration above 600 seconds emits `long-video`. A gap above 600 seconds between the beginning, confirmed interaction points, and the end also emits `sparse-video-interactions`; review whether to 增加交互点 for a learning reason.
- Size above `500 MiB` emits `large-video`. These three warnings require teacher-facing notice but do not by themselves block upload.

Safe candidate processing rules:

- An incompatible profile or large file may trigger an offer to process it with `ffmpeg`; file size alone does not force conversion.
- Obtain approval for the exact source path, candidate path, output profile, and tradeoff before running media tools.
- Preserve the original bytes and path. Store every attempt in an append-only `.course-work/video-backups/<BLOCK_ID>-<SOURCE_SHA256>-<CANDIDATE_ID>.json` manifest; create the candidate under `.course-work/video-candidates/<BLOCK_ID>/` with `ffmpeg -n`.
- Recheck the source hash immediately before conversion. Probe and compare the candidate after processing.
- Do not update the Blueprint, final asset, or interaction document until the teacher has played and confirmed the exact candidate hash and the decision is persisted under `.course-work/video-processing-decisions/`.
- Adopt with a no-clobber copy. Reuse an identical final hash or choose a new path when a different file already occupies the intended path.
- After adoption, relocate every timed event from its semantic anchor in the confirmed video and record old time, anchor, new time, and verification evidence. Never derive new times by proportional duration scaling.
