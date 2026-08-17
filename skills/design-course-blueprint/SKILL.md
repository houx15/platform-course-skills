---
name: design-course-blueprint
description: Use when a teacher course draft has its learning content and materials but still lacks complete CourseDefinition 2.0 Slice layout, narration, workflow, navigation, completion semantics, or runtime-ready media declarations.
---

# Design Course Blueprint

Complete the production experience for every Slice while preserving confirmed content. The pinned shared student Zod contract defines valid data; the runtime catalog makes every supported choice available to the authoring agent.

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
3. Read the complete `runtime_authoring_catalog.json`. It exposes all four layouts, all seven Block types, all 16 种 Action, all 16 种 Event, matcher fields, navigation options, video cues, and HTML protocol fields. Common patterns are examples only and must never become a smaller closed schema.
4. Preserve every valid authored field. 不得静默覆盖 teacher-confirmed wording, objectives, answers, rubrics, feedback, source paths, media timing, or prior production decisions. If a valid authored choice must change, record the exact before/after proposal and require teacher confirmation.
5. For 每个 Slice, draft the complete production design:

   - `objectiveIds` and `estimatedSeconds`;
   - complete Blocks and completion semantics;
   - one explicit `layout` assigning every Block exactly once;
   - prepared `narrations` with stable IDs, transcript text, and planned relative audio paths;
   - a deterministic `workflow` with explicit initial state, Steps, ordered actions, typed transitions, all meaningful answer branches, and a reachable terminal path;
   - complete `navigation`.

6. Keep one Slice visually bounded to one desktop screen. Split the Slice when its learning action, materials, or Blocks cannot fit without crowding. A Slot may contain multiple ordered Blocks, but density is still a review constraint.
7. For interactive HTML, inspect the actual file and explicitly decide whether it uses audio. When it does, author `capabilities.audio: true` and require the host lifecycle protocol. A valid completion message must carry `correct` or `value`; an empty completion payload is invalid.
8. Do not generate a Workflow transition on `pdf.pageChanged`. It exists in the contract vocabulary but the pinned renderer has no producer for it; the catalog marks it `do-not-generate-transition`. PDF evidence must come from a separate interaction or assessment.
9. Store proposed runtime choices in each Slice's `productionDecisions` inside `course-completion-plan.json`, with source IDs, decision IDs, rationale, and status `ai-proposed`. Present one review row per Slice:

   | Slice | Layout | Initial view | Narration and sequence | Student action | Branches and completion | Navigation | Needs confirmation |
   | --- | --- | --- | --- | --- | --- | --- | --- |

10. Batch related semantic decisions for teacher confirmation. After teacher confirmation, update `.course-work/course-blueprint.json`, its provenance, and approval decision identity. Never edit generated `course/course.json` directly.
11. Rerun `complete-course-draft.py`. Continue until every Slice is `ready-for-contract-validation` and course-level issues are empty.
12. Compile and validate through the shared student Zod contract:

   ```bash
   python _course-toolkit/scripts/compile-course.py ROOT --json
   python _course-toolkit/scripts/validate-course-v2.py ROOT --json
   ```

   Contract success proves structural/runtime validity. It does not replace real renderer preview or teacher Review.

## Completion boundary

Report this Skill complete only when:

- every Slice is `ready-for-contract-validation`;
- the completion-plan draft hash matches the current Blueprint;
- teacher confirmation covers every meaning-changing production decision;
- compilation passes the shared student Zod contract;
- missing assets remain plainly reported rather than hidden with fake files.

Do not upload, publish, call the student API, or mark preview Review complete from this Skill.
