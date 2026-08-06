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
- Keep event IDs unique.
- Put finalized events in strictly increasing time order.
- Do not reuse one timestamp for two events.
- Keep every finalized time below the actual MP4 duration.
- Use `graded`, `survey`, or `reflection` assessment consistently.
- A provisional event requires non-empty `anchor`, null `timeSeconds`, and `status: needs-timing`.
- Final Review blocks every provisional event.
