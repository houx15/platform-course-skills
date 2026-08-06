# Course-building state machine

Persist the current state in `.course-work/session.json`.

## States

### 1. `materials-intake`

- Collect explicit input paths.
- Inventory without modifying originals.
- Invoke material analysis.
- Persist the exact extraction at `.course-work/materials-extracted.json`; later Review reconciles every source ID against it.
- Exit only after unreadable files are surfaced and the material summary is confirmed.

### 2. `media-intent`

- Present detected video and HTML candidates with source evidence.
- Ask explicitly about both categories when absent.
- Record accepted and rejected candidates in `decisions.json`.
- Exit only when video and HTML intent are explicit.

### 3. `media-design`

- Invoke the relevant specialist for every accepted candidate.
- Preserve provisional video anchors.
- Exit only after the teacher confirms each readable design. Provisional timing may remain, but must stay in `unresolved.json`.

### 4. `structure-proposal`

- Propose Parts (pages), Pieces (one-click content groups), and ordered blocks.
- Show source IDs, purpose, modality, blocking, and unresolved decisions.
- Exit only after explicit teacher confirmation.

### 5. `part-detail`

- Work Part by Part.
- Ask for missing goals, assessment meaning, answers/rubrics, feedback, and blocking behavior.
- Record substantive AI suggestions and teacher confirmation.
- Preview and confirm each Part.

### 6. `generation`

- Create a clean `course/`.
- Write canonical course and video JSON.
- Generate Markdown views.
- Copy only referenced delivery assets.
- Never generate or include ZIP.

### 7. `review`

- Invoke the independent review skill.
- Treat open blocking items in `.course-work/unresolved.json` and unconfirmed substantive decisions as blockers even when generated files are structurally valid.
- Auto-fix only mechanical problems.
- Return semantic issues to the teacher.
- Repeat until one final status is justified.

## Resume rules

- Never repeat a confirmed question.
- Hash or compare source files and reopen only affected decisions.
- Do not mark an unresolved item resolved because output files exist.
- Preserve every approved discard and substantive AI addition.
