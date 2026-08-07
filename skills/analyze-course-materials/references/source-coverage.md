# Source coverage contract

Store authoring traceability at `.course-work/source-coverage.json`:

```json
{
  "schemaVersion": "1.0",
  "items": [
    {
      "sourceId": "source-0123456789abcdef",
      "sourceFile": "materials/lesson.docx",
      "location": "paragraph:12",
      "kind": "paragraph",
      "summary": "教师提供的内容摘要",
      "status": "unresolved",
      "destinations": [],
      "teacherConfirmed": false
    }
  ]
}
```

Allowed statuses:

- `unresolved`: no accepted disposition yet;
- `mapped`: placed in one or more learner-facing course blocks;
- `merged`: combined with other source items; keep every source ID and real destinations;
- `discard-proposed`: AI recommends excluding it from the learner course but the teacher has not agreed;
- `discard-approved`: teacher agreed it stays outside the learner course; include `reason` and `teacherConfirmed: true`.

Audience and coverage are separate judgments:

- `.course-work/audience-classification.json` says who the source item is for;
- `source-coverage.json` says where it went in the final learner course;
- confirmed `teacher-design`, `ai-system`, and `reference` items normally become `discard-approved` with a reason such as “保留在作者工作记录，不进入学生课程”;
- `proposed-exclusion` cannot become `discard-approved` until the teacher confirms the grouped exclusion.

Final Review blocks `unresolved`, `discard-proposed`, missing destinations, and unconfirmed discards. It also reconciles both records against `.course-work/materials-extracted.json`:

- every extracted `sourceId` appears exactly once in coverage and exactly once in audience classification;
- `sourceFile` and `location` match the extracted item;
- no invented or stale `sourceId` remains;
- every mapped destination names an existing `part-id/piece-id/block-id`;
- DOCX table evidence retains locations such as `table:2/row:3/cell:1/paragraph:1`, never an untraceable flattened paragraph.

Present readable grouped summaries to the teacher instead of raw JSON unless requested.
