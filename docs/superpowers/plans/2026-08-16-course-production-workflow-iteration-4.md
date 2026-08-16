# Course Production Workflow Iteration 4 Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` task by task. Work on `dev`, use no worktree or subagents, commit each completed task, and do not push.

**Goal:** Implement the complete local annotation and authoring-revision protocol that can later be driven by the student renderer preview shell, without implementing or simulating that renderer. Annotations must bind to stable CourseDefinition IDs, survive deterministic reconciliation, route semantic changes through teacher decisions, update CourseBlueprint rather than generated CourseDefinition, and remain unverified until a future G7 preview proves the new definition.

**Architecture:** Keep `.course-work/annotations.json` as authoring-only state. Use the current CourseDefinition hash and runtime source map to resolve stable course/Part/Slice/Block/item/workflow-step targets. Store agent-authored revision plans separately, with scoped JSON-pointer replacement operations, before-value hashes, and explicit classification. A deterministic tool applies only safe mechanical edits or semantic edits backed by a current confirmed teacher decision. Runtime bugs create G7 blockers and never mutate course content. Reconciliation and application invalidate downstream workflow through the existing artifact rules; no browser, renderer, OSS, or remote course API is involved.

**Important boundary:** `applied` means the Blueprint change exists. Only the future renderer-backed G7 loop may set an annotation to `verified` against a new definition hash. This iteration may create mock annotations and reconcile targets, but it cannot claim visual or runtime verification.

---

## Task 1: Define and persist the annotation contract

**Files:** `course_toolkit/annotations.py`, `schemas/course-annotations.schema.json`, tests.

- [x] Define versioned annotation types, statuses, classifications, stable targets, definition hash, text, optional safe screenshot path, proposal/resolution fields, applied Blueprint hash, and verified definition hash.
- [x] Enforce legal lifecycle transitions and status-specific invariants; required annotations cannot be dismissed without a teacher decision.
- [x] Provide deterministic load/save/add/update behavior with stable IDs supplied by the caller and no timestamps generated inside the store.
- [x] Reject duplicate IDs, unknown fields, unsafe screenshot paths, CSS selectors, pixel coordinates, and array-position targets.
- [x] Add schema syntax and round-trip/lifecycle tests.
- [x] Commit: `feat: define course annotation records`.

## Task 2: Resolve annotations through current definition and source map

**Files:** annotation module/CLI, issue registry/schema, Workflow, tests.

- [x] Resolve course, Part, Slice, Block, item, and workflow-step targets hierarchically against current CourseDefinition 2.0.
- [x] Map each resolvable annotation to a stable source-map target and Blueprint pointer; item targets remain scoped under their owning Block.
- [x] Mark missing or structurally inconsistent targets `orphaned` with an explanation; restore an orphan to `open` if the exact stable target reappears.
- [x] Preserve annotations created against an older definition hash when stable IDs still resolve, while recording that rebinding occurred.
- [x] Synchronize required open/orphaned annotations and runtime bugs into registered G7 issues without touching unrelated issues.
- [x] Add `manage-annotations.py add|list|reconcile` for mock/local-file use and update session pending annotation IDs.
- [x] Commit: `feat: reconcile stable course annotations`.

## Task 3: Define scoped annotation revision plans

**Files:** `course_toolkit/annotation_revisions.py`, `schemas/annotation-revision-plan.schema.json`, CLI/tests.

- [ ] Define a plan tied to current Blueprint, definition, and source-map hashes, with one entry per annotation.
- [ ] Classify entries as `mechanical`, `semantic`, or `runtime-bug`; include target ID, summary, and zero or more scoped `replace` operations with before-value hashes.
- [ ] Reject operations outside the annotation target, changes to stable IDs/source paths/correctness/workflow/layout under the mechanical policy, and all mutation operations for runtime bugs.
- [ ] `prepare` marks valid entries proposed, creates context-hashed teacher decisions for semantic entries, and creates a G7 blocker for runtime bugs.
- [ ] Repeated preparation is idempotent and never overwrites a confirmed decision with different context.
- [ ] Commit: `feat: plan annotation driven revisions`.

## Task 4: Apply approved revisions to Blueprint only

**Files:** revision module/CLI, DecisionStore/Workflow integration, tests.

- [ ] Add an explicit CLI path to confirm a pending teacher decision only from a supplied teacher answer; never infer confirmation.
- [ ] Apply safe mechanical entries directly and semantic entries only when their exact context-hashed decision is confirmed.
- [ ] Verify base hashes and every before-value hash, apply all operations to a copy, validate the resulting Blueprint, then write Blueprint plus annotation states atomically with rollback.
- [ ] Never write `course/course.json`; require the existing compile, G5, validation, and G6 sequence after application.
- [ ] Mark applied annotations with the new Blueprint hash and resolution decision where applicable, but leave `verifiedAgainstDefinitionHash` empty.
- [ ] Reapplying the exact plan is idempotent; partial application or stale plans fail without mutation.
- [ ] Commit: `feat: apply approved annotation revisions`.

## Task 5: Prove a mixed revision batch and update the teacher workflow

**Files:** real/mock batch fixture test, director/reference Skill, validation report, this plan.

- [ ] Exercise content, layout/semantic, workflow/semantic, media/semantic, and runtime-bug annotations against stable targets without hand-editing CourseDefinition.
- [ ] Prove mechanical application, semantic decision blocking/confirmation, runtime-bug non-mutation, orphan handling, recompilation/G6 invalidation, and no premature `verified` state.
- [ ] Update the director to read/reconcile annotations, present proposed semantic decisions, apply approved revisions, then recompile and rerun G5/G6.
- [ ] State that only future G7 preview evidence can verify applied annotations or clear runtime bugs.
- [ ] Run all Python tests, shared contract tests, typecheck, schema checks, contract sync, and Skill scenarios.
- [ ] Commit: `docs: route preview feedback through blueprint revisions`.
