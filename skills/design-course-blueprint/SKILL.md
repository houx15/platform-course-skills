---
name: design-course-blueprint
description: Use when a teacher course draft has its learning content and materials but still lacks complete CourseDefinition 2.0 Slice layout, narration, workflow, navigation, completion semantics, or runtime-ready media declarations.
---

# Design Course Blueprint

Complete the production experience for every Slice after the teacher has approved the methodology-centred teaching design and the derived page plan. Preserve that instructional spine and all valid authored content. The pinned shared student Zod contract defines valid data; the runtime catalog makes every supported choice available to the authoring agent.

## Required inputs

- the selected course root;
- current `.course-work/course-storyboard.json`, including `teachingDesign`, the student-perspective review, the derived Slice rows, and their single teacher approval for new work;
- `.course-work/course-blueprint.json`, or the explicitly named draft;
- `_course-toolkit/course_toolkit/runtime_authoring_catalog.json`;
- [runtime-authoring-standard.md](references/runtime-authoring-standard.md).

If the draft still lacks a core methodology, ordered learning arc, worked model, scaffolded practice, transfer task, stable Parts/Slices, learning objectives, or chosen materials, return it to `build-platform-course` for teaching design. This Skill completes runtime experience design; it does not invent the course's teaching logic in isolation or turn every source into a question.

## Workflow

1. Run:

   ```bash
   python _course-toolkit/scripts/complete-course-draft.py ROOT --json
   ```

   In a repository checkout, use `python scripts/complete-course-draft.py ROOT --json`.

2. Read `.course-work/course-completion-plan.json`. Work through every Slice record; do not stop after fixing the first invalid Slice.
3. Read the complete `runtime_authoring_catalog.json`. It exposes all four contract layouts, all seven split weights, all eight Block types, `openAs: "inline" | "modal"`, all 16 种 Action, all 16 种 Event, matcher fields, navigation options, video cues, HTML protocol fields, and the narrower teacher-side media-composition policy. Contract support does not mean every layout is a good default: do not generate `split-vertical` by default or stack multiple inline Blocks in `full`.
4. Preserve every valid authored field, the approved teaching design, the derived page plan, and `sliceSemanticReview` when present. Each Slice implementation must retain its learning-arc phase, instructional role, method-step links, learner-state change, cumulative-artifact update, and the approved page-to-page connection. 不得静默覆盖 explicit teacher wording, source-backed objectives, source disposition, image/question pairing, answers, rubrics, feedback, source paths, media timing, or prior production decisions. When runtime completion requires layout or Workflow detail that the approved plan did not specify, infer it, record the rationale, and continue. Pause only when the detailed implementation would change the approved teaching purpose/material/action or when correctness cannot be inferred.
   Preserve and render every new plan's `journeyContext`. The opening must intentionally introduce the learning problem before asking for an answer, using the form that best fits the material: story, case conflict, observation, demonstration, problem situation, or overview/map. A method is introduced before its first exercise. Every Slice must expose both its local link to the previous page and its position in the overall method or learning arc. Use the lightest clear surface—title, framing sentence, narration, method-step rail, `刚才 / 现在 / 接下来`, or continuing-artifact state—and do not mechanically add a large orientation card to every page. Never rely on hidden IDs alone to supply that orientation.
5. For 每个 Slice, draft the complete production design:

   - `objectiveIds` and `estimatedSeconds`;
   - complete Blocks and completion semantics;
   - one explicit `layout` assigning every Block exactly once;
   - prepared `narrations` with stable IDs, transcript text, and planned relative audio paths;
   - a deterministic `workflow` with explicit initial state, Steps, ordered actions, typed transitions, all meaningful answer branches, and a reachable terminal path;
   - complete `navigation`.

6. Keep one Slice visually bounded to one desktop screen. Treat it like one teaching slide: design one instructional move, one visual focal point, bounded information density, a clear relation to the preceding/following page, and an immediately understandable purpose for a novice. Split the Slice when its learning action, materials, or Blocks cannot fit without crowding. All split Slots must be non-empty: never place every Block in one side and leave a dead column or row. Use `full` for one focused Block, distribute reference/explanation on the left and the answerable Block on the right, or split sequential stacked content into separate Slices. A `split-horizontal` defaults to `1:1`, including text beside a portrait PDF; never choose `3:1` or another ratio to disguise an empty side. Every PDF has a 放大阅读 action in a near-fullscreen modal, so PDF legibility never justifies an asymmetric split. The only normal asymmetric exception is one dominant large video paired with a small amount of supporting text; give the video the wider side. Let the shared renderer keep both sides vertically centred. Put an answerable Block in the right slot when it shares a horizontal split with reference or explanatory content. A `grid` may contain two to four cells; choose it when the material really benefits from comparison rather than from a rigid element-count formula. Text and assessments need constrained reading width.

   Use `openAs: "modal"` to keep a supporting original, detailed figure, video, reference card, secondary interaction, or question available at near-fullscreen size without shrinking the Slice's focal teaching surface. Keep primary teaching content inline. Never hide the instructions or evidence a learner must notice before acting behind a modal launcher. Author a concise `modalLabel` when the derived button label would be ambiguous. A modal question follows the same Workflow and completion payload as its inline form; a modal resource opens only on learner press.
7. Keep the evidence needed for an answer in the same Slice whenever it remains readable. Do not require the learner to flip back to another Slice or PDF page merely to recall the referenced prompt. If the source and answer surface cannot fit together clearly, reframe the task or split the teaching sequence before the answer rather than making navigation part of the assessment.
8. For AI-authored single-choice questions, vary correct answer positions and do not default every correct answer to the first option. Reordering options must preserve the exact answer meaning and feedback. Teacher-provided questions and answers remain unchanged unless the teacher explicitly requests an edit.
   For an `images` Block, use `side-by-side` only for two landscape images that must stay simultaneously visible. Prefer `gallery` for multiple portrait/tall images or more than two images so the existing previous/next controls keep each image legible; do not create a long vertical stack unless simultaneous vertical comparison is essential.
9. For every planned `richText` Block, invoke `design-course-rich-text` internally after page-plan approval. Use it for the opening course map, current-method position, consequential concepts and source-reading instructions, as well as worked-example anatomy, comparisons, definitions, tables or synthesis. It carries inline HTML, no asset path and no completion rule. Give it a tall slot, keep it under 64 KB, and never use it as an interaction substitute. Reject a heading plus plain list disguised as `richText`: require an inline style and at least two clearly differentiated teaching regions, using restrained primitives such as large numbered steps, subtle theme-derived cards, a progress rail, a hint block or a worked-example panel.
10. For graded `fillBlank`, reject `submit-correct` as an authoring choice. Open language uses `reflection + submit-any`; genuinely closed short answers use realistic accepted variants, actionable `incorrectFeedback`, and `submit-correct-or-exhausted` with `maxAttempts` no greater than 3. After exhaustion, the workflow must reveal explanation or allow continuation rather than silently stranding the learner. Regex keywords must not grade conceptual understanding.
11. For interactive HTML, inspect the actual file and explicitly decide whether it uses audio. When it does, author `capabilities.audio: true` and require the host lifecycle protocol. Treat `aspectRatio` as a design hint and use `fill` when the interaction has no preferred shape; the v1.8.0 host gives the iframe the complete Slot. Require the HTML to fill that frame fluidly, scroll internally when needed, and avoid a centred/scaled fixed canvas or a clipped `aspect-ratio` wrapper. Verify the complete task and completion control at 1280×720 and 1200×520, plus the opened modal when `openAs: "modal"`. A valid completion message must carry `correct` or `value`; an empty completion payload is invalid. A free-text interaction may not keep completion unreachable behind an unbounded regex/keyword match: show actionable mismatch feedback and provide a finite explanation/continuation path, or treat the response as ungraded.
12. Do not generate a Workflow transition on `pdf.pageChanged`. It exists in the contract vocabulary but the pinned renderer has no producer for it; the catalog marks it `do-not-generate-transition`. PDF evidence must come from a separate interaction or assessment.
13. Store runtime choices in each Slice's `productionDecisions` inside `course-completion-plan.json`, with source IDs, rationale, and their link to the approved page plan. Persist one traceability row per Slice without asking the teacher to approve implementation details separately:

   | Slice | Layout | Initial view | Narration and sequence | Student action | Branches and completion | Navigation | Needs confirmation |
   | --- | --- | --- | --- | --- | --- | --- | --- |

14. Apply source-backed production decisions to `.course-work/course-blueprint.json`, preserve the combined teaching-design/page-plan approval evidence, update provenance, and continue directly to compilation. Do not add questions merely to create a completion event; explanation, modelling, and guided observation Slices may use an appropriate non-assessment completion path. The teacher reviews the rendered result later. Ask one batched question only for true blockers. Never edit generated `course/course.json` directly.
15. Rerun `complete-course-draft.py`. Continue until every Slice is `ready-for-contract-validation` and course-level issues are empty.
16. Compile and validate through the shared student Zod contract:

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
