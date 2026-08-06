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
- `mapped`: placed in one or more course blocks;
- `merged`: combined with other source items; keep every source ID;
- `discard-proposed`: AI recommends omission but the teacher has not agreed;
- `discard-approved`: teacher agreed; include `reason` and `teacherConfirmed: true`.

Final Review blocks `unresolved`, `discard-proposed`, missing destinations, and unconfirmed discards.

Final Review also reconciles this file against `.course-work/materials-extracted.json`:

- every extracted `sourceId` must appear exactly once;
- `sourceFile` and `location` must match the extracted item;
- no invented or stale `sourceId` may remain;
- every mapped destination must name an existing `part-id/piece-id/block-id`;
- DOCX table evidence uses locations such as `table:2/row:3/cell:1/paragraph:1`, not an untraceable flattened paragraph number.

Present the teacher with a readable summary instead of raw JSON unless they ask for the file.
