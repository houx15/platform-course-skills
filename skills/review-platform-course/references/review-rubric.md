# Review rubric

## 1. Source fidelity

- Every extracted source item has a resolved disposition.
- `materials-extracted.json` and `source-coverage.json` have exactly matching source IDs, source files, and locations.
- Every merge retains all source IDs and destinations.
- Every mapped destination names an actual block in `course.json`.
- Every discard records the teacher's confirmation and reason.
- Every substantive AI addition is confirmed.
- Every blocking item in `unresolved.json` is resolved before upload.
- Conflicting source claims remain visible until the teacher resolves them.

## 2. Course contract

- `course.json` uses schema version 1.0.
- Course, Part, Piece, block, event, and option IDs are valid and unique.
- Only the six v1 block types appear.
- Required assessments, answers, rubrics, feedback, blocking flags, and completion rules are present.
- All paths stay inside `course/` and referenced files exist.
- `index.md` is the exact generated view.

## 3. HTML

- One self-contained HTML file.
- Valid canvas, standardized completion button, confirmed completion condition.
- `INTERACTION_COMPLETE` version 1.0 and required payload fields.
- Structured interaction records.
- No prohibited external runtime resources.

## 4. Video interactions

- The MP4 itself is not generated or modified.
- JSON is canonical and Markdown is generated.
- Declared duration matches the actual MP4.
- Final event times are ordered, unique, and inside the video.
- No event remains `needs-timing`.

## 5. Outcome labels

- `可上传`: no blocking issue remains.
- `修改后可上传`: only explicitly listed mechanical repairs remain.
- `缺少必要材料，暂不可上传`: missing evidence, unresolved teacher choice, invalid contract, unsafe path, missing file, invalid HTML, or provisional/invalid video timing remains.

Never upgrade a result because the files look polished.
