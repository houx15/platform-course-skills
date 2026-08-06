# Course contract summary

## Upload directory

```text
course/
├── course.json
├── index.md
├── assets/
│   ├── images/
│   └── videos/
└── interactions/
    ├── html/
    └── video/
```

`.course-work/` remains outside the upload directory.

Required authoring records beside the upload directory:

```text
.course-work/
├── materials-extracted.json
├── source-coverage.json
├── decisions.json
├── unresolved.json
└── session.json
```

Review reconciles the extracted source inventory with coverage, checks that mapped destinations are real course blocks, and blocks every open item marked `blocking: true`.

## Canonical hierarchy

```text
course → parts[] → pieces[] → blocks[]
```

- Part: one platform page.
- Piece: one click-revealed content group on that page.
- Block: one ordered content unit.

Allowed v1 block types:

- `text`
- `images`
- `video`
- `interactiveHtml`
- `fillBlank`
- `singleChoice`

Use schema version `1.0`, stable lowercase hyphenated IDs, course-root-relative safe paths, non-empty image alt text, explicit blocking flags, and consistent assessment modes.

Use the bundled `schemas/course.schema.json` and `schemas/video-interactions.schema.json` as the detailed public contracts. Use `scripts/render-index.py` and `scripts/render-video-interactions.py` for views; never hand-maintain generated Markdown.
