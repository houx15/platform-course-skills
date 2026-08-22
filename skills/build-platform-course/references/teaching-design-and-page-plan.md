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

The output of teaching design is not only an internal traceability graph. Translate it into a student-visible spine before designing exercises:

- the opening is an intentional student-facing introduction before the first required answer; choose a story, case conflict, observation task, demonstration, problem situation, or course overview/map, and make the learning problem, relevance and direction clear;
- each methodology is introduced as a whole before its first application;
- each practice Slice visibly identifies the active methodology and step, explains why the learner is doing this now, connects to the previous Slice, and previews what the result enables next;
- assessment and interaction Blocks follow this orientation; they never appear as an unexplained cold open.

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

For every newly designed Slice, also write the additive `journeyContext` object. Older approved plans without it remain valid and must not be reopened merely to add it.

```json
{
  "journeyContext": {
    "coursePosition": "方法一：主张拆解 / 步骤 2 of 5",
    "connectionFromPrevious": "上一页已经看过完整方法图，这一页开始第一次带练。",
    "currentFocus": "现在只练习把宽泛表述改写成可核查事实主张。",
    "setsUpNext": "得到清晰主张后，下一页才能选择来源和核查路径。"
  }
}
```

These are learner-facing continuity statements, not production notes. The Blueprint must render their meaning in the Slice, normally in a compact rich-text method-position card beside the source or immediately above the action.

Follow the `learningArc` order. Use the same method-step IDs declared by `teachingDesign`. The before/after states must name a real change. `whyOwnSlice` must justify an instructional unit, not merely say that a source file or image exists.

At page-plan time, choose the intended information shape without writing final HTML yet. Mark `richText` as the likely modality when a course map, current-method position card, reading lens, static method, worked model, comparison, evidence ladder, definition set, table, rubric, or synthesis needs visible grouping that Markdown would flatten. A reading lens sits beside the original source and tells the learner why to read, what dimensions to notice, and what question to carry into the material; it does not replace the material with a summary. A method-position card names the current step, why it follows the prior page, the exact capability being practised, and what comes next. Keep short prose as `text`; keep real media in their media Blocks; keep anything the learner manipulates or submits out of `richText`. The internal rich-text specialist writes the inline HTML only after the teacher approves the complete teaching design and page plan.

Treat each Slice like one teaching slide. Evaluate four things together: bounded information density; the visual scene and focal point; continuity with the previous and next Slice; and whether a novice immediately understands the page's purpose. Do not approve a row merely because its IDs and action are valid.

## Student-perspective review

Review exactly these criteria and record concrete page/phase evidence:

- `purpose-clarity`
- `method-before-practice`
- `scaffolding`
- `assessment-load`
- `cumulative-progress`
- `motivation-and-pacing`
- `transfer`

When reviewing `purpose-clarity`, reject an opening that asks for a question, judgment or answer before creating a meaningful entry into the learning problem. The introduction may be a story, case conflict, observation, demonstration, problem situation, or overview; judge whether the learner understands why this course begins here and what direction it will take. When reviewing `method-before-practice` and `scaffolding`, require each exercise to visibly state the active method step, its prerequisite and its consequence; check whether a structured `richText` teaching surface is needed before the learner is asked to apply it. When reviewing `assessment-load`, reject open-language prompts whose progress depends on an exact keyword or regex match; reflection should accept any meaningful submission, while a closed short-answer check needs feedback and a finite attempt path.

Use `revise` while any criterion fails. Repair the teaching design and derived page plan before changing the overall status to `ready-for-teacher`. A passing record must show what the student experiences; generic claims such as “the design is clear” are not evidence.
