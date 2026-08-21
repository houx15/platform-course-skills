# Teaching design and page-plan authoring

Use this reference only for a new course or a course whose teaching structure is being redesigned. Existing plans without `teachingDesign` remain valid and must not be reopened solely to add it.

## Authoring order

1. Finish material analysis.
2. Draft `teachingDesign` without creating Slice rows.
3. Derive the Part/Slice rows from the ordered `learningArc`.
4. Re-read the entire journey from a novice student's perspective.
5. Repair the design and rows until all student-perspective checks pass.
6. Render the combined Markdown and ask the teacher for one approval.

Do not start with a source-to-page mapping. A source may support several phases, several sources may share one Slice, and teacher/reference sources may remain outside the learner course.

## `teachingDesign` shape

```json
{
  "essentialQuestion": "学生真正要解决的问题",
  "learnerStartingPoint": "开始时的直觉、知识或常见误解",
  "learnerDestination": "课程结束时能够独立使用的方法",
  "methodologies": [
    {
      "id": "method-id",
      "name": "方法名称",
      "purpose": "这个方法解决什么问题",
      "steps": [
        {
          "id": "method-step-id",
          "name": "步骤名称",
          "learnerCapability": "学生完成这一步时能够做什么"
        }
      ],
      "commonMistakes": ["一个具体常见错误"]
    }
  ],
  "casePractice": {
    "anchorCase": "贯穿练习的案例",
    "caseRole": "案例如何帮助学生练习方法",
    "transferTask": "与示范案例不同的新情境任务"
  },
  "cumulativeArtifact": {
    "name": "学生持续完成的成果",
    "description": "它如何随着课程推进逐步形成"
  },
  "learningArc": [
    {
      "id": "phase-id",
      "title": "阶段标题",
      "instructionalRoles": ["teach", "model"],
      "methodStepIds": ["method-step-id"],
      "learnerStartsWith": "进入阶段时的状态",
      "learnerDoes": "学生在此阶段经历什么",
      "learnerLeavesWith": "离开阶段时新增的理解或能力",
      "artifactUpdate": "累计成果在此阶段怎样更新"
    }
  ],
  "studentPerspectiveReview": {
    "status": "ready-for-teacher",
    "studentJourneySummary": "按顺序描述学生实际经历的学习过程",
    "checks": [
      {
        "criterion": "purpose-clarity",
        "status": "pass",
        "evidence": "具体说明学生何时知道课程问题和学习目的"
      }
    ],
    "revisionsMade": ["预审后已经完成的具体修改"],
    "remainingConcerns": []
  }
}
```

Supported `instructionalRoles` are:

- `hook`
- `activate-prior-knowledge`
- `teach`
- `model`
- `guided-practice`
- `independent-practice`
- `feedback`
- `synthesis`
- `transfer`

Every core method step must appear in at least one `teach` or `model` Slice and at least one guided, independent, synthesis, or transfer Slice. Include at least one worked `model` Slice and one `transfer` Slice in the complete course.

## Slice additions

When `teachingDesign` exists, every Slice row also requires:

```json
{
  "arcPhaseId": "phase-id",
  "instructionalRole": "guided-practice",
  "methodStepIds": ["method-step-id"],
  "learnerStateBefore": "进入本页前的理解状态",
  "learnerStateAfter": "离开本页后的新增理解或能力",
  "artifactUpdate": "本页对累计成果的具体更新",
  "whyOwnSlice": "为什么这段教学必须独立成页"
}
```

Follow the `learningArc` order. Use the same method-step IDs declared by `teachingDesign`. The before/after states must name a real change. `whyOwnSlice` must justify an instructional unit, not merely say that a source file or image exists.

## Student-perspective review

Review exactly these criteria and record concrete page/phase evidence:

- `purpose-clarity`
- `method-before-practice`
- `scaffolding`
- `assessment-load`
- `cumulative-progress`
- `motivation-and-pacing`
- `transfer`

Use `revise` while any criterion fails. Repair the teaching design and derived page plan before changing the overall status to `ready-for-teacher`. A passing record must show what the student experiences; generic claims such as “the design is clear” are not evidence.
