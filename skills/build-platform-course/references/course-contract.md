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

Review reconciles extraction, audience classification, coverage, storyboard course frame, actual course blocks, and Part review evidence.

## Course-level frame

Use schema version `1.1`. Every course requires `course.introduction` before Parts and `course.conclusion` after all Parts:

```json
{
  "schemaVersion": "1.1",
  "course": {
    "introduction": {
      "overview": "面向学生的一段课程介绍",
      "objectives": [{"id": "compare-evidence", "text": "检查两条证据是否可以直接比较"}],
      "keyPoints": ["先检查对象", "再检查数据和尺度"]
    },
    "parts": [],
    "conclusion": {
      "summary": "面向学生的课程内容回顾",
      "takeaways": ["比较结论前先检查可比性", "边界不同可能造成假冲突"],
      "transferApplications": ["论文阅读", "AI 答案核查"]
    }
  }
}
```

The introduction has 1–5 objective objects and 2–6 key points. The conclusion has 2–6 takeaways and 1–8 transfer applications. The platform supplies the fixed `开始学习` action; it is not a JSON field, Part, Block, or completion rule. The conclusion summarizes designed content and transfer possibilities without claiming an individual student has already mastered it.

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

Use stable lowercase hyphenated IDs, course-root-relative safe paths, non-empty image alt text, explicit blocking flags, and consistent assessment modes. Objective IDs share the global ID namespace with Part, Piece, and Block IDs.

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

`course.json` is canonical and learner-facing. `index.md` is its exact generated learner view: course start screen, ordered Parts, then conclusion report content. Do not place authoring records, teaching rationale, AI/system instructions, or proposed content in either file.

Use `scripts/render-index.py`, `scripts/render-video-interactions.py`, `scripts/render-course-storyboard.py`, and `scripts/render-review-report.py`; never hand-maintain generated Markdown.
