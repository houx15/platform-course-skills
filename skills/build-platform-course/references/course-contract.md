# Course contract summary

## Upload directory

```text
course/
├── course.json
├── index.md
├── assets/
│   ├── images/
│   ├── pdfs/
│   └── videos/
└── interactions/
    ├── html/
    └── video/
```

`.course-work/` remains outside the upload directory. ZIP is never required.

Required authoring records:

```text
.course-work/
├── materials-extracted.json
├── source-coverage.json
├── audience-classification.json
├── course-storyboard.json
├── course-storyboard.md
├── decisions.json
├── unresolved.json
├── session.json
├── review-report.json
└── review-report.md
```

Review reconciles extraction, audience classification, coverage, storyboard, actual course blocks, and Part review evidence.

## Canonical hierarchy

```text
course → parts[] → pieces[] → blocks[]
```

- Part: one platform page and one coherent learning stage.
- Piece: one click-revealed, sufficiently complete student teaching unit.
- Block: one ordered presentation or activity unit inside the Piece.

Allowed v1 block types:

- `text`
- `images`
- `pdf`
- `video`
- `interactiveHtml`
- `fillBlank`
- `singleChoice`

Use schema version `1.0`, stable lowercase hyphenated IDs, course-root-relative safe paths, non-empty image alt text, explicit blocking flags, and consistent assessment modes.

## PDF Block

Use a `pdf` Block only for a complete teacher-confirmed learner document:

```json
{
  "id": "source-paper",
  "type": "pdf",
  "title": "研究论文原文",
  "source": "assets/pdfs/source-paper.pdf"
}
```

The Block requires exactly `id`, `type`, `title`, and `source`; it 不得包含 `blocking` or `completion`. Copy the original bytes into `assets/pdfs/`. Do not rebuild, summarize, or convert the full document. The platform embeds the document and offers the original download, but v1 does not claim reading completion.

`course.json` is canonical and learner-facing. `index.md` is its exact generated learner view. Do not place authoring records, teaching rationale, AI/system instructions, or proposed content in either file.

Use `scripts/render-index.py`, `scripts/render-video-interactions.py`, `scripts/render-course-storyboard.py`, and `scripts/render-review-report.py`; never hand-maintain generated Markdown.
