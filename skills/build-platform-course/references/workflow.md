# Course-building state machine

Persist the current state in `.course-work/session.json`.

## States

### 1. `materials-intake`

- Collect explicit input paths and preserve originals.
- Invoke material extraction.
- Persist `.course-work/materials-extracted.json`.
- Surface unreadable inputs and conflicts.
- Exit only after the material summary is confirmed.

### 2. `audience-classification`

- Classify every source item as `student-core`, `student-evidence`, `teacher-design`, `ai-system`, `reference`, or `proposed-exclusion`.
- Present grouped non-student items and proposed exclusions.
- Persist `.course-work/audience-classification.json`.
- Exit only after teacher confirmation.

### 3. `media-intent`

- Present detected video and HTML candidates with evidence.
- Ask explicitly about both categories when absent.
- Record decisions.
- Exit only when video and HTML intent are explicit.

### 4. `media-design`

- Invoke the relevant specialist for every accepted candidate.
- Preserve provisional video semantic anchors.
- Exit only after readable designs are confirmed. Provisional timing remains blocking in `unresolved.json`.

### 5. `course-storyboard`

- Design Parts as learning stages and Pieces as complete student-facing teaching units.
- Decide presentation modality from learning function; never default to text.
- Persist `.course-work/course-storyboard.json`.
- Render `.course-work/course-storyboard.md` with counts and one row per Piece.
- Exit only after the teacher confirms the complete table and all required assets or open items are explicit.

### 6. `part-detail`

- Work Part by Part using the confirmed storyboard.
- Supply complete student content, meaningful exercises, answers/rubrics, feedback, and blocking behavior.
- Record substantive AI suggestions and teacher confirmation.
- Never copy authoring rationale into learner output.

### 7. `generation`

- Create a clean `course/`.
- Write canonical course and video JSON.
- Generate Markdown views.
- Copy only referenced delivery assets.
- Never generate or include ZIP.

### 8. `review`

- Invoke independent Part-level review.
- Persist `review-report.json` and generated `review-report.md`.
- Treat any failed Part dimension, open blocking item, unconfirmed substantive decision, or contract error as blocking.
- Auto-fix only mechanical problems.
- Return semantic issues to the storyboard, obtain confirmation, rebuild, and repeat the full review.

## Resume rules

- Never repeat a confirmed question.
- Hash or compare source files and reopen only affected decisions.
- Do not mark an unresolved item resolved because output files exist.
- Preserve every approved exclusion and substantive AI addition.
- A changed storyboard invalidates the previous review report.
