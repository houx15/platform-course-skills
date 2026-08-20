# Instructional Binding and Staged Course Authoring Design

**Status:** Approved design  
**Date:** 2026-08-20  
**Scope:** Teacher-facing course production in `platform-course-skills`  
**Implementation status:** Not started

## 1. Purpose

The course authoring workflow must produce lessons whose materials, teaching intent, layout, interactions, and learner actions are deliberately composed. Structural contract validity alone is insufficient.

This design prevents four recurring failures:

1. teacher-provided material is silently omitted or reduced without explanation;
2. content is stacked, hidden, or pushed into an unusable interaction area;
3. images, questions, and explanatory text are paired incorrectly;
4. learner-facing text refers to evidence or source material that is absent when the learner needs it.

The workflow adopts a staged design-approval model inspired by Superpowers: understand the source, propose a page-by-page instructional plan, obtain one meaningful teacher approval, implement the approved plan, perform an Agent visual check, conduct versioned teacher review, and publish only the reviewed version.

## 2. Product decisions

The following decisions are fixed for this iteration:

- The Skill explains the full workflow briefly when it starts.
- The Agent inventories all selected source material before course design.
- The Agent produces a readable page-by-page plan before detailed runtime generation.
- The teacher approves that plan before the Agent completes Blocks, narration, Workflow, navigation, and production details.
- The plan records teaching purpose, selected materials, material roles, learner action, layout, and co-visibility requirements for every Slice.
- Material may be proposed for exclusion without blocking the first plan or preview, but every proposed exclusion needs a reason and teacher confirmation before publication.
- The Agent performs a mandatory renderer-backed visual check before giving the teacher a preview link.
- The teacher preview is versioned. The Agent does not mutate the course while the teacher is reviewing a particular version.
- Annotation handling proceeds in rounds: review, submit feedback, rebuild, revalidate, and review a new version.
- The Publish button is enabled only when the current version has no unresolved required annotations or blockers.
- Publishing uses two steps: prepare and display the exact publication plan, then obtain final teacher confirmation before OSS/API mutation and ship/TTS.
- Other reviewers use the course published to the student platform through the Phoebe account. ZIP archives, copied course directories, and local URLs are not review handoffs.

## 3. Teacher-facing workflow introduction

At the beginning of a new or resumed course task, the Agent gives a short explanation in the teacher's language. The Chinese default is:

> 我会先完整盘点材料，生成一份逐页教学编排计划。你确认计划后，我再补齐文字、素材、layout、workflow 和互动细节，并打开真实学生端样式的本地预览。你可以在预览中批注；修改和终审完成后，再发布到学生端，其他人可以通过 Phoebe 的账号查看。

The introduction must not expose JSON, internal Skills, validator names, or G0-G10 terminology. After the explanation, the Agent continues automatically until the page plan is ready or a genuine source/correctness blocker is found.

## 4. Layered sources of truth

The design strengthens existing work records rather than adding a second course definition.

| Artifact | Responsibility |
| --- | --- |
| `.course-work/materials-extracted.json` | Complete inventory of teacher-selected source items and their stable source locations. |
| `.course-work/audience-classification.json` | Whether an item is learner content, learner evidence, teacher design, system material, reference material, or a proposed exclusion. |
| `.course-work/source-coverage.json` | The accepted disposition of every source item and its real Part/Slice/Block bindings. |
| `.course-work/course-storyboard.json` | The approved page-by-page instructional plan and cross-Block dependencies. |
| `.course-work/course-blueprint.json` | The only authoring source for the complete runtime-shaped course. |
| `course/course.json` | Deterministically compiled CourseDefinition 2.0; never edited directly. |
| `.course-work/prepreview-visual-report.json` | Hash-bound renderer and visual evidence produced before teacher preview. |
| `.course-work/annotations.json` | Stable-target teacher feedback and its lifecycle. |
| `.course-work/preview-manifest.json` | Evidence that the teacher reviewed the current definition and renderer version. |
| `.course-work/publication-plan.json` | Exact create/update, upload/reuse, cover, ship/TTS, and remote-readback plan awaiting approval. |

Each artifact has one purpose. The storyboard specifies the approved teaching design; the Blueprint implements it. Validators compare them and reject unexplained divergence.

## 5. Material inventory and disposition

Every extracted source item appears exactly once in source coverage and has one of these dispositions:

- `required-core`: learner-facing concepts, explanations, tasks, or conclusions that must be represented;
- `required-evidence`: examples, images, cases, documents, or data that learners must inspect;
- `optional-support`: material that may improve clarity but is not required for the planned learning action;
- `authoring-only`: teacher design, system instructions, provenance, or background used to build the lesson but not shown to learners;
- `exclude-proposed`: the Agent recommends omission and records a concrete reason;
- `exclude-approved`: the teacher has accepted that exclusion.

An unbound `optional-support` item must still carry a concrete non-use reason and appear in the teacher-readable unused-material summary. It does not block publication unless the teacher marks it as required. `authoring-only` items remain traceable work evidence and do not require exclusion approval. Every `exclude-proposed` item blocks publication until it becomes mapped or `exclude-approved`.

Mapped items carry bindings to current CourseDefinition 2.0 identities:

```json
{
  "sourceId": "source-0123456789abcdef",
  "sourceFile": "materials/lesson.pdf",
  "location": "page:7/figure:2",
  "summary": "Comparison diagram used by the evidence question",
  "disposition": "required-evidence",
  "bindings": [
    {
      "partId": "part-evidence",
      "sliceId": "slice-compare",
      "blockId": "comparison-images",
      "role": "question-reference",
      "supportsIds": ["evidence-question"]
    }
  ]
}
```

The current legacy `Part/Piece/Block` destination collector must be migrated to `Part/Slice/Block`. A record that merely claims material was used is not sufficient: every mapped destination must exist, and the target Block must contain or reference the claimed material.

If only a segment is used, the binding preserves a verifiable locator such as PDF page, slide, DOCX paragraph/table cell, video time range, HTML activity ID, or image item ID.

## 6. Page-by-page instructional plan

Before detailed runtime production, the Agent generates a complete storyboard. The teacher sees a concise table with one row per Slice:

| Page | Teaching purpose | Learner sees | Source material | Material role | Learner action | Layout | Required co-visible content |
| --- | --- | --- | --- | --- | --- | --- | --- |

Every Slice plan records:

- a stable Part and Slice identity;
- one explicit teaching purpose;
- the exact material items and source locators used on the page;
- the role of every selected material;
- the intended Blocks or presentation modalities;
- the learner action and completion evidence;
- the high-level layout preset and split intent;
- references that must be available during an answer or interaction;
- image-to-claim and image-to-question relationships;
- unresolved source/correctness blockers;
- proposed exclusions relevant to that teaching stage.

The plan is a pedagogical approval surface, not a runtime JSON review. It does not require the teacher to approve narration IDs, Workflow step syntax, source paths, or other implementation fields.

The teacher may approve the whole plan, edit individual rows, restore proposed exclusions, change the teaching sequence, or change a page's purpose and learner action. One approval binds the storyboard hash, source inventory hash, and decision ID.

Below the Slice table, the Agent presents one grouped “Unused or authoring-only material” section. It lists every unbound source item, its disposition, and its reason. This prevents absence from being mistaken for an intentional teaching decision.

## 7. Plan approval and invalidation

Plan approval is required before detailed production.

The following changes invalidate plan approval and all downstream evidence:

- adding, removing, reordering, splitting, or merging Slices;
- changing a Slice teaching purpose;
- replacing or removing a selected image, PDF, video, HTML file, or source segment;
- changing the material that supports a question;
- changing the learner's core action or evidence of completion;
- changing the main layout preset (`full`, split, or grid);
- changing a proposed exclusion to a different substantive disposition.

The following changes do not require renewed plan approval, but they invalidate compilation and downstream validation:

- copy editing that preserves meaning;
- narration wording or timing details;
- Workflow implementation details that preserve the approved learning sequence;
- accessibility, format, protocol, or media compatibility fixes;
- layout slot refinements within the approved layout intent that do not change material relationships.

Any implementation that materially diverges from the approved plan must report the difference and return to plan approval. It must never silently update the plan after generation.

## 8. Internal gate model

The teacher sees four simple phases while the system retains G0-G10 internally.

| Teacher phase | Internal gates | Exit condition |
| --- | --- | --- |
| Understand materials | G0-G2 | All selected inputs inventoried; intent and genuine blockers identified. |
| Approve page plan | G3-G4 | Complete page plan exists and the teacher has approved its current hash. |
| Produce the course | G5-G6 | Blueprint, compiled course, material bindings, format checks, semantic checks, and pre-preview visual check pass. |
| Preview and publish | G7-G10 | Current version reviewed, annotations verified, final review passed, publication approved, executed, and read back. |

The Agent completes deterministic work without repeatedly asking the teacher to approve internal production details.

## 9. Pre-preview instructional validation

Before the teacher receives a preview URL, the system performs four complementary checks.

### 9.1 Material coverage

Blockers include:

- a `required-core` or `required-evidence` item has no real binding;
- a mapped target Part, Slice, Block, or image item does not exist;
- a Block exists but does not contain/reference the bound source;
- a source segment was summarized or substituted where the plan requires the complete original;
- an exclusion is disguised as a mapped or merged item;
- the generated course uses an untracked source item.

### 9.2 Instructional correspondence

The Agent performs a source-grounded semantic audit:

- an image supports the claim, comparison, observation task, or question assigned to it;
- a question is answerable from the declared evidence and preserves teacher-provided correctness;
- phrases such as “the figure above,” “the original paper,” “this case,” or “the following data” resolve to the correct Block;
- required reference material is in the same Slice whenever the learner must use it while answering;
- any justified cross-Slice dependency is explicit and does not force ordinary backtracking during assessment;
- no important source claim has been reduced beyond what the approved plan allows.

Semantic uncertainty becomes a review item only when two arrangements are genuinely plausible. A clear mismatch is a blocker.

### 9.3 Layout and Workflow consistency

Blockers include:

- any Block is unassigned, duplicated, or assigned to a non-existent Slot;
- a split Slot is empty;
- answerable and reference content are stacked into one side while the other side is unused;
- a Workflow begins the learner action before required reference Blocks are visible;
- an answerable Block is not enabled when the learner is asked to respond;
- the Workflow hides content that remains necessary;
- a required interaction has no reachable completion path;
- a critical task is placed in a visually hidden overflow area.

### 9.4 Format and runtime safety

Existing CourseDefinition, PDF, video, WEBVTT, HTML protocol, asset-path, hash, and interaction checks remain mandatory. Passing them does not substitute for instructional or visual validation.

## 10. Mandatory Agent Visual Check

The Agent Visual Check runs after static and semantic validation and before teacher preview. It mounts the exact pinned student renderer and uses the same definition and local assets that the teacher will review.

### 10.1 Coverage

The Agent visits:

- every Slice initial state;
- the state after prepared narration;
- the state in which each learner action becomes available;
- meaningful answer branches, including correct, incorrect, and exhausted-attempt states when supported;
- video interaction modal states;
- interactive HTML ready, active, completed, and error states when reachable;
- the final pre-completion state of each Slice.

The inspection uses the teacher annotation panel collapsed and student-shell-equivalent desktop viewport profiles. It checks the normal desktop target and the constrained content width created by the student sidebar. Mobile is out of scope.

### 10.2 Evidence

For every inspected state, the report records:

- screenshot path and SHA-256;
- definition, Blueprint, asset-set, renderer, and viewport hashes/identities;
- visible and enabled Block IDs;
- DOM bounding rectangles and viewport intersection;
- overflow, occlusion, scroll, focus, and runtime-error observations;
- the relevant approved storyboard bindings;
- Agent visual findings and severity.

### 10.3 Visual judgments

The Agent checks:

- missing, zero-sized, off-screen, occluded, or unclickable content;
- large dead columns or rows;
- misleading centering caused by an empty or badly weighted Slot;
- unreadably small text, images, PDFs, videos, or HTML;
- improper media aspect or stretching;
- poor reading order between explanation, evidence, and action;
- reference and answer surfaces that should be co-visible but are not;
- a screenshot that visibly contradicts the approved page plan;
- core tasks discoverable only through unexpected scrolling.

### 10.4 Repair loop

Deterministic layout, Workflow, binding, and formatting problems are repaired automatically. The course is recompiled, revalidated, and visually checked again. The Agent may perform up to three consecutive autonomous repair rounds for the same pre-preview version. Persistent blockers are reported as specific source, renderer, or design problems rather than hidden or waived.

The teacher receives a preview link only when:

```text
static validation passes
+ instructional bindings pass
+ Agent Visual Check has zero blockers
+ all evidence matches the current hashes
```

The Agent Visual Check does not complete teacher review and cannot approve publication.

## 11. Finding severity

### Blocker

A blocker prevents teacher preview or publication as appropriate. Examples include omitted required material, clear source mismatch, absent answer evidence, invisible controls, unreachable completion, plan divergence, stale evidence, or a failed visual check.

### Warning

A warning permits teacher preview but remains visible. Examples include low-confidence semantic correspondence, near-density-limit pages, or an unresolved aesthetic preference with two defensible options.

### Teacher review item

A review item asks for pedagogical judgment rather than engineering repair. Examples include tone, explanatory depth, pacing, preferred image emphasis, or teaching order within the already approved intent.

Proposed exclusions are allowed through first preview but block publication until confirmed or remapped.

## 12. Versioned preview and annotation rounds

The Agent must not change the definition while the teacher is reviewing that version.

The lifecycle is:

```text
preview version N
→ teacher reviews and annotates
→ teacher submits the review round
→ Agent reconciles and applies bounded changes
→ compile, validate, and run the Agent Visual Check
→ preview version N+1
→ teacher verifies resolved items
```

Annotations use these states:

- `open`: awaiting action;
- `in-progress`: being analyzed or changed;
- `applied`: changed in the Blueprint but not yet verified in a current preview;
- `verified`: confirmed resolved in the current preview;
- `wont-fix`: explicitly retained with a rationale.

An applied annotation cannot be auto-promoted to verified. A new definition hash makes prior visual verification stale. New or reopened required annotations invalidate final review and publication readiness.

## 13. Publish button and publication controller

The Publish button is part of the teacher preview chrome, not the student renderer. It is enabled only when the current version satisfies all of these conditions:

- every Slice and required interaction was reviewed;
- the current preview manifest matches the current definition and renderer;
- no `open` or `in-progress` required annotation exists;
- every `applied` required annotation is now `verified` or explicitly `wont-fix`;
- no runtime error or pre-preview visual blocker exists;
- every proposed source exclusion has been confirmed or remapped;
- independent G8 review passes;
- the fixed 33-course catalog identity is confirmed.

Clicking Publish performs a preflight; it does not immediately mutate OSS or the student platform. The preview UI requests the local authoring controller to produce an exact publication plan containing:

- fixed course title and slug;
- create versus update result from remote readback;
- new upload count and reused asset count;
- fixed cover binding;
- definition PUT effects;
- ship/TTS effects;
- current approved hashes;
- the statement that the published course will be reviewed through the Phoebe account.

The teacher confirms this plan in a second UI step. Only then may the local publication controller load the Git-ignored credential, upload required assets, PUT the fixed-slug course, ship, and perform byte/hash/readback verification. The renderer iframe never receives credentials or publication authority.

Any local or remote change after preflight invalidates approval and requires a new plan.

## 14. Invalidation model

| Change | Invalidated evidence |
| --- | --- |
| Selected source content changes | Material inventory and every downstream gate. |
| Teaching purpose, material selection, Slice order, dependency, or layout intent changes | Storyboard approval and every downstream gate. |
| Blueprint copy, Blocks, Workflow, navigation, or asset bytes change | Compilation, G6, visual check, teacher preview, final review, and publication. |
| Renderer or stylesheet changes | Visual check, teacher preview, final review, and publication. |
| Annotation is added or reopened | Final review and publication. |
| Remote course state changes after preflight | Publication approval and execution plan. |

No artifact is current merely because its file exists. Every gate verifies hashes and required upstream decisions.

## 15. Existing in-progress courses

Legacy and partially processed courses must not restart or create new remote identities.

The migration path is:

1. preserve the existing Blueprint, source files, annotations, stable catalog identity, and publication state;
2. reconcile all current materials and generated Blocks;
3. replace legacy `Part/Piece/Block` coverage destinations with `Part/Slice/Block` bindings;
4. reverse-generate a readable page plan from the current course and sources;
5. identify unused material, unsupported exclusions, unexplained pages, missing references, and source mismatches;
6. obtain one teacher approval for the recovered plan;
7. resume from the earliest invalidated gate;
8. update the same fixed slug and reuse unchanged asset objects.

Migration must not silently delete existing course content or annotations.

## 16. Error handling

- If a required file cannot be read, record the exact file and block any claim derived from its content.
- If a material relationship is ambiguous, present the competing interpretations at plan review rather than guessing during production.
- If browser automation or screenshot capture is unavailable, pre-preview visual review is blocked; the Agent cannot waive it.
- If an interaction state cannot be reached, classify whether the cause is authored Workflow, media protocol, or renderer behavior and retain it as a blocker.
- If three visual repair rounds fail, stop autonomous reshuffling and report the persistent evidence.
- If a renderer bug is responsible, preserve it as a runtime bug; do not rewrite course content to conceal it.
- If publication preflight or execution fails, the course remains at its previous remote state when the API contract guarantees atomicity; otherwise the Agent reports the observed remote state and requires readback before another attempt.
- Credentials never appear in course files, screenshots, reports, logs, command arguments, or the renderer.

## 17. Acceptance tests

The implementation needs deterministic unit, integration, browser, and end-to-end coverage.

### 17.1 Material and binding mutations

Tests must reject:

- a required item with no binding;
- a binding whose target Block does not exist;
- a Block that exists but does not contain the bound source;
- two images swapped between questions;
- a learner-facing reference to an absent PDF, image, case, or data Block;
- a mapped complete-document requirement satisfied only by a summary or screenshot;
- an unconfirmed proposed exclusion at publication time.

### 17.2 Layout, Workflow, and visual mutations

Tests must reject:

- an empty split Slot;
- all content stacked in one split side;
- required evidence hidden when the question is enabled;
- an answer surface outside the viewport or under another element;
- a required task discoverable only through unintended scrolling;
- incorrect PDF/video/HTML aspect handling;
- a stale visual report reused after definition, asset, renderer, stylesheet, or viewport change;
- a visual-check blocker followed by teacher preview handoff.

### 17.3 Annotation and publication state

Tests must prove:

- applied annotations remain unverified until a new current preview verifies them;
- a new or reopened annotation disables Publish;
- a proposed exclusion disables Publish until approved/remapped;
- Publish preflight reports create/update and upload/reuse accurately;
- a changed remote state invalidates approval;
- an existing fixed slug is updated rather than recreated;
- unchanged assets are reused by slug, relative path, and SHA-256;
- final readback matches the exact approved definition and uploaded bytes.

### 17.4 Full Chinese teacher simulation

The required end-to-end scenario is:

```text
scattered Chinese teacher materials
→ Agent explains the workflow
→ complete material inventory
→ page-by-page plan
→ teacher revises and approves the plan
→ detailed runtime production
→ structural and semantic validation
→ mandatory Agent Visual Check and autonomous repair
→ teacher preview and Chinese annotations
→ annotation application and rebuilt preview
→ teacher verifies every required annotation
→ Publish becomes enabled
→ exact publication preflight
→ teacher confirms
→ fixed course is updated and shipped
→ course is visible through the Phoebe account
```

The scenario must include unused material, a deliberate image-question swap, a missing co-visible reference, an initially hidden answer surface, and an unchanged asset that must be reused.

## 18. Success criteria

The feature is complete only when:

- every teacher-selected material has an explainable disposition;
- all required learner material has a verifiable runtime binding;
- the course matches the teacher-approved page plan;
- clear source, image, question, and reference mismatches are blocked before preview;
- the Agent Visual Check has zero blockers for the current hashes;
- the teacher reviews the current version rather than a stale one;
- all required annotations are resolved and verified;
- publication updates the fixed catalog course and reuses unchanged assets;
- student-platform readback matches the locally approved version;
- another reviewer can inspect the published course through the Phoebe account without receiving a ZIP or local URL.

## 19. Out of scope

- mobile course authoring or mobile visual profiles;
- live AI mutation while a teacher is viewing a preview version;
- collaborative simultaneous annotation by multiple teachers;
- automatic deletion or merging of historical duplicate remote courses;
- allowing the renderer iframe to access publication credentials;
- replacing teacher pedagogical review with Agent visual judgment.

## 20. Implementation boundary

This document specifies behavior and evidence. Implementation should be decomposed into independently testable work for:

1. CourseDefinition 2.0 coverage/binding migration;
2. page-plan schema, rendering, approval, and invalidation;
3. deterministic instructional validation;
4. Agent semantic and visual preflight orchestration;
5. annotation lifecycle and preview-version handling;
6. Publish-button preflight, approval, and controller handoff;
7. legacy-course reconciliation and end-to-end fixtures.

No implementation work is authorized by this design document alone. An implementation plan follows only after user review of the committed specification.
