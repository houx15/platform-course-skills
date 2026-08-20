---
name: design-course-blueprint
description: Use when a teacher course draft has its learning content and materials but still lacks complete CourseDefinition 2.0 Slice layout, narration, workflow, navigation, completion semantics, or runtime-ready media declarations.
---

# Design Course Blueprint

Complete the production experience for every Slice while preserving valid authored content. The pinned shared student Zod contract defines valid data; the runtime catalog makes every supported choice available to the authoring agent.

## Required inputs

- the selected course root;
- `.course-work/course-blueprint.json`, or the explicitly named draft;
- `_course-toolkit/course_toolkit/runtime_authoring_catalog.json`;
- [runtime-authoring-standard.md](references/runtime-authoring-standard.md).

If the draft still lacks stable Parts, Slices, learning objectives, or chosen materials, return it to `build-platform-course` for content design. This Skill completes runtime experience design; it does not invent the course's core teaching intent in isolation.

## Workflow

1. Run:

   ```bash
   python _course-toolkit/scripts/complete-course-draft.py ROOT --json
   ```

   In a repository checkout, use `python scripts/complete-course-draft.py ROOT --json`.

2. Read `.course-work/course-completion-plan.json`. Work through every Slice record; do not stop after fixing the first invalid Slice.
3. Read the complete `runtime_authoring_catalog.json`. It exposes all four contract layouts, all seven split weights, all seven Block types, all 16 种 Action, all 16 种 Event, matcher fields, navigation options, video cues, HTML protocol fields, and the narrower teacher-side media-composition policy. Contract support does not mean every layout is a good default: do not generate `split-vertical` by default or stack multiple Blocks in `full`.
4. Preserve every valid authored field. 不得静默覆盖 explicit teacher wording, source-backed objectives, answers, rubrics, feedback, source paths, media timing, or prior production decisions. When runtime completion requires a new choice that can be safely inferred, record the exact before/after value and rationale as a source-backed AI draft. Pause only when changing an explicit instruction or when correctness cannot be inferred.
5. For 每个 Slice, draft the complete production design:

   - `objectiveIds` and `estimatedSeconds`;
   - complete Blocks and completion semantics;
   - one explicit `layout` assigning every Block exactly once;
   - prepared `narrations` with stable IDs, transcript text, and planned relative audio paths;
   - a deterministic `workflow` with explicit initial state, Steps, ordered actions, typed transitions, all meaningful answer branches, and a reachable terminal path;
   - complete `navigation`.

6. Keep one Slice visually bounded to one desktop screen. Split the Slice when its learning action, materials, or Blocks cannot fit without crowding. All split Slots must be non-empty: never place every Block in one side and leave a dead column or row. Use `full` for one focused Block, distribute reference/explanation on the left and the answerable Block on the right, or split sequential stacked content into separate Slices. A `split-horizontal` defaults to `1:1`, including text beside a portrait PDF; never choose `3:1` or another ratio to disguise an empty side. The v1.5.2 renderer gives every PDF a 放大阅读 action in a near-fullscreen modal, so PDF legibility never justifies an asymmetric split. The only normal asymmetric exception is one dominant large video paired with a small amount of supporting text; give the video the wider side. Let the shared renderer keep both sides vertically centred. Put an answerable Block in the right slot when it shares a horizontal split with reference or explanatory content. A `grid` may contain two to four cells; choose it when the material really benefits from comparison rather than from a rigid element-count formula. Interactive HTML preserves its declared `1:1`/`4:3` ratio without stretching. Text and assessments need constrained reading width.
7. Keep the evidence needed for an answer in the same Slice whenever it remains readable. Do not require the learner to flip back to another Slice or PDF page merely to recall the referenced prompt. If the source and answer surface cannot fit together clearly, reframe the task or split the teaching sequence before the answer rather than making navigation part of the assessment.
8. For AI-authored single-choice questions, vary correct answer positions and do not default every correct answer to the first option. Reordering options must preserve the exact answer meaning and feedback. Teacher-provided questions and answers remain unchanged unless the teacher explicitly requests an edit.
9. For interactive HTML, inspect the actual file and explicitly decide whether it uses audio. When it does, author `capabilities.audio: true` and require the host lifecycle protocol. A valid completion message must carry `correct` or `value`; an empty completion payload is invalid.
10. Do not generate a Workflow transition on `pdf.pageChanged`. It exists in the contract vocabulary but the pinned renderer has no producer for it; the catalog marks it `do-not-generate-transition`. PDF evidence must come from a separate interaction or assessment.
11. Store proposed runtime choices in each Slice's `productionDecisions` inside `course-completion-plan.json`, with source IDs, decision IDs, rationale, and status `ai-proposed`. Persist one traceability row per Slice without interrupting the first-preview path:

   | Slice | Layout | Initial view | Narration and sequence | Student action | Branches and completion | Navigation | Needs confirmation |
   | --- | --- | --- | --- | --- | --- | --- | --- |

12. Apply source-backed production decisions to `.course-work/course-blueprint.json`, keep `approval.teacherConfirmed: false`, update provenance, and continue directly to compilation. The teacher reviews these choices in the renderer preview. Ask one batched question only for true blockers. Never edit generated `course/course.json` directly.
13. Rerun `complete-course-draft.py`. Continue until every Slice is `ready-for-contract-validation` and course-level issues are empty.
14. Compile and validate through the shared student Zod contract:

   ```bash
   python _course-toolkit/scripts/compile-course.py ROOT --json
   python _course-toolkit/scripts/validate-course-v2.py ROOT --json
   ```

   Contract success proves structural/runtime validity. It does not replace real renderer preview or teacher Review.

## Completion boundary

Report this Skill complete only when:

- every Slice is `ready-for-contract-validation`;
- the completion-plan draft hash matches the current Blueprint;
- every meaning-changing production decision is source-backed or remains a plainly reported blocker;
- compilation passes the shared student Zod contract;
- missing assets remain plainly reported rather than hidden with fake files.

Do not upload, publish, call the student API, or mark preview Review complete from this Skill.
