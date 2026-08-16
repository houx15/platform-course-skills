# Course Production Workflow and Skill Architecture

**Status:** Approved overall design. Iterations 1–5 are implemented on `dev`: persistent Workflow, CourseBlueprint/CourseDefinition 2.0 compilation, static and asset validation, structure-linked annotation revision, publication dry runs, and a mockable idempotent publisher. The shared renderer preview, real annotation UI, OSS adapter, and student-platform API adapter remain Iteration 6.

**Date:** 2026-08-16

**Scope:** The complete teacher course-production lifecycle, from scattered local materials to a reviewed, previewed, asset-complete CourseDefinition 2.0 course that is safely created or updated and published to the student platform.

## 1. Goal

Teachers are internal team members who work locally through Codex, Claude, or a similar coding agent. They should not need a separate account system, dashboard, visible version manager, or knowledge of Skills, JSON contracts, validators, OSS, or publishing APIs.

The system must give the teacher one conversational entry point that can:

1. understand and organize scattered course materials;
2. ask for the teaching decisions that only the teacher can make;
3. design a complete course with Parts, Slices, Blocks, Layouts, Narrations, Workflows, and Navigation;
4. compile the authoring design into CourseDefinition 2.0;
5. validate the definition and every referenced asset;
6. open the shared student renderer in a local preview shell;
7. collect structure-linked annotations and revise the course through the agent;
8. independently review the final result;
9. upload only changed assets;
10. create or update the same remote course and publish it only after explicit confirmation.

The central separation is:

> Workflow manages process. Skills perform bounded expert reasoning. Deterministic tools perform checks and external operations. The teacher retains teaching decisions and publication authority.

## 2. Non-goals

- No teacher SaaS dashboard.
- No teacher login or role-management system.
- No visible branch, commit, or course-version management for teachers.
- No duplicate implementation of the student renderer.
- No free-form executable workflow code inside course data.
- No direct OSS credentials, internal API keys, or signed URLs inside Skills, course files, annotations, preview URLs, or ordinary logs.
- No automatic acceptance of AI-added substantive teaching content, correct answers, rubrics, blocking rules, media substitutions, or major structural changes.
- No runtime tutoring system in this phase.
- No claim that static validation proves browser rendering or learning quality.

## 3. Chosen architecture

The selected architecture is a **single teacher-facing director Skill**, backed by a **persistent production Workflow**, **internal specialist Skills**, and a **deterministic toolkit**.

Two alternatives were rejected:

- A monolithic Skill would mix material analysis, teaching design, compilation, validation, preview, revision, and publishing in one growing context. It would be difficult to test, resume, or repair.
- A teacher-visible collection of Skills would expose internal architecture and let required stages be skipped or called in the wrong order.

### 3.1 Four layers

| Layer | Responsibility | Teacher visibility |
| --- | --- | --- |
| Teacher-facing director | Understand the request, restore state, explain the current phase, ask decisions, and coordinate the work | Fully visible; this is the single entry |
| Production Workflow | Persist phase, gates, invalidations, issues, decisions, and next legal actions | Summarized as progress and blockers |
| Specialist Skills | Perform bounded material, pedagogy, media, compilation, review, feedback, and publishing work | Hidden unless an explanation is useful |
| Deterministic toolkit | Parse files, validate contracts/assets, hash resources, launch preview, and call external APIs | Results are translated into teacher-readable reports |

## 4. Teacher-facing experience

The teacher uses one main Skill: the existing `build-platform-course`, evolved into the course-director role. There is no second visible entry.

The teacher can say:

- “Build a course from these materials.”
- “Continue this course.”
- “Open the preview.”
- “Apply my preview comments.”
- “Check whether this is ready.”
- “Publish this course.”

The director automatically determines whether the operation is:

- a new course;
- a resumed incomplete course;
- a revision after new materials or decisions;
- a revision after preview annotations;
- an update to an existing remote course;
- a final publication attempt.

The teacher sees only:

- current phase and completed milestones;
- a readable material summary;
- teaching decisions that require confirmation;
- readable course structure and proposed changes;
- preview location and annotation status;
- blockers, decisions required, warnings, and informational changes;
- a final upload/publish dry run;
- the verified remote result.

Raw JSON, internal Skill names, validator stack traces, object-storage keys, and API request details remain hidden unless the teacher explicitly asks for technical diagnostics.

## 5. Persistent Workflow model

The Workflow is not another conversational Skill. It is a deterministic state machine persisted in `.course-work/session.json`.

### 5.1 Phase and status

Avoid encoding every pause or failure as a separate phase. Store a stable `phase` and an orthogonal `status`.

```ts
type CourseProductionPhase =
  | "intake"
  | "material-review"
  | "course-brief"
  | "course-design"
  | "media-design"
  | "compile"
  | "validate"
  | "preview"
  | "revise"
  | "final-review"
  | "publish"
  | "complete"

type PhaseStatus =
  | "ready"
  | "active"
  | "waiting-for-teacher"
  | "blocked"
  | "failed"
  | "completed"
```

`session.json` records at least:

```ts
interface CourseProductionSession {
  workflowVersion: "1.0"
  courseLocalId: string
  phase: CourseProductionPhase
  status: PhaseStatus
  completedGateIds: string[]
  invalidatedGateIds: string[]
  activeIssueIds: string[]
  pendingTeacherDecisionIds: string[]
  pendingAnnotationIds: string[]
  artifactHashes: Record<string, string>
  lastSuccessfulAction?: string
  lastFailure?: {
    action: string
    code: string
    message: string
    recoverable: boolean
  }
}
```

The Workflow permits only legal forward transitions and explicit revision loops. The main loop is:

```text
intake
→ material-review
→ course-brief
→ course-design
→ media-design
→ compile
→ validate
→ preview
→ revise ──┐
     ▲      │
     └──────┘
→ final-review
→ publish
→ complete
```

Validation failure returns to the earliest responsible phase. It does not blindly restart the whole course.

### 5.2 Resume algorithm

Whenever the director starts, it must:

1. locate the selected course root safely;
2. read `session.json` when present;
3. inventory current files and compute relevant hashes;
4. compare current hashes with recorded artifact hashes;
5. invalidate stale downstream gates;
6. load open issues, decisions, annotations, and remote publish state;
7. choose the earliest legal next action;
8. explain the restored state to the teacher in plain language.

The agent must not infer completion merely because an artifact exists. A gate is complete only when its recorded checks and confirmations passed for the current input hashes.

### 5.3 Dependency invalidation

Changes invalidate only their dependants:

| Change | Invalidates |
| --- | --- |
| Raw material added, removed, or changed | material analysis, source coverage, brief if affected, Blueprint, compilation, validation, preview, review, publish preflight |
| Teacher brief decision changed | Blueprint and all downstream gates |
| Blueprint changed | media designs affected by the change, compilation, validation, preview, review, publish preflight |
| Video/HTML/PDF/audio asset changed | relevant media report, asset manifest, runtime validation, preview verification, final review, publish preflight |
| CourseDefinition compiler version changed | compiled definition and all downstream gates |
| Course contract version changed | compilation, validation, preview, final review, publish preflight |
| Student renderer version changed | visual/browser verification and final review, but not material or teaching decisions |
| Open annotation added | final review and publish preflight |
| Previously applied annotation target disappeared | annotation reconciliation, final review, publish preflight |
| Remote course revision changed unexpectedly | publish preflight and remote update decision |

## 6. Quality gates

Each gate has explicit inputs, checks, and exit conditions. A later phase cannot compensate for an incomplete earlier gate.

### G0 — Workspace safety and identity

Checks:

- the course root is explicit;
- reads remain inside the course root;
- ZIP files are ignored;
- writes are limited to `course/`, `.course-work/`, and explicitly generated human-readable files;
- the local course identity is stable;
- no credential is stored in course files.

Exit condition: safe workspace and local course identity recorded.

### G1 — Material inventory complete

Checks:

- all supported source files inventoried;
- readable content extracted where possible;
- duplicate, missing, corrupt, or unsupported files reported;
- source coverage record created;
- video and HTML intent explicitly confirmed, even when source materials are silent;
- complete-document PDF candidates identified.

Exit condition: the teacher understands what was found and all blocking material questions are resolved or explicitly deferred.

### G2 — Course brief approved

The brief records:

- learner audience and assumed prior knowledge;
- course goal and objectives;
- estimated time;
- required outcomes or evidence;
- required materials and non-negotiable content;
- allowed reorganization and AI supplementation boundaries;
- intended use of video, HTML, PDF, images, assessment, and narration.

Exit condition: every substantive field is teacher-confirmed.

### G3 — Course Blueprint approved

Checks:

- every objective maps to a real Part and evidence-producing Block;
- every Part has a clear purpose;
- every Slice represents one desktop screen and one primary learning action;
- Block density is reasonable;
- Layout, narration, interaction, completion, and navigation intent are explicit;
- AI-added substantive content, answers, rubrics, and blocking behavior are confirmed.

Exit condition: teacher approves the readable Course/Part/Slice design.

### G4 — Specialist media designs complete

Checks only the media actually used:

- video timing, pause cues, assessments, completion and resume policy;
- HTML interaction purpose, message protocol, completion evidence, audio policy, disabled/hidden lifecycle, and self-containment;
- PDF identity, integrity, title, and learning purpose;
- image order, alt text, captions, and presentation;
- narration text, audio path, and duration expectations.

Exit condition: every complex media Block has a confirmed design and required local asset.

### G5 — CourseDefinition compilation complete

Checks:

- `course-blueprint.json` compiles deterministically into CourseDefinition 2.0;
- stable semantic IDs are assigned;
- source map links runtime elements back to Blueprint elements;
- all asset references are relative paths;
- generated output contains no unresolved authoring fields;
- generated output is time-free and environment-free.

Exit condition: compiler succeeds and records compiler version plus input/output hashes.

### G6 — Static and asset validation passed

Validation layers:

1. CourseDefinition structural validation.
2. Referential validation.
3. Workflow and Navigation validation.
4. Asset existence and safe-path validation.
5. Video, captions, audio, PDF, and HTML validation.
6. Pre-preview density and visual-risk heuristics.

Exit condition: no active blocker and no unresolved teacher decision. Warnings may remain only when their policy permits preview.

### G7 — Preview review complete

Checks:

- preview uses the same course renderer package as the student platform;
- renderer and contract versions are recorded;
- every Slice was visited under the current definition hash;
- representative Workflow branches and interactive Blocks were exercised;
- layout overflow and media behavior were checked in the supported desktop viewport;
- all required preview annotations are resolved or explicitly dismissed.

Exit condition: teacher marks the current preview review complete and no required annotation remains open.

### G8 — Independent final review passed

The final review re-reads source materials, authoring records, final CourseDefinition, assets, validation results, and preview evidence. It must not accept the director or compiler's claim that an item passed.

Exit condition: `review-report.json` is `publishable`, with no blocker, unresolved decision, stale preview evidence, or open required annotation.

### G9 — Publish preflight approved

Checks:

- local course identity matches the intended remote course identity;
- create versus update is resolved without ambiguity;
- local and remote definition revisions are known;
- changed and unchanged assets are listed by hash;
- no unchanged asset will be uploaded again;
- remote update will not create a second course;
- remaining warnings and their acknowledgements are shown;
- API and OSS credentials are available through the approved external mechanism.

Exit condition: teacher explicitly approves the dry run.

### G10 — Remote publication verified

Checks:

- every required asset upload succeeded and remote metadata was recorded;
- the intended course was created or updated;
- the remote stored CourseDefinition hash matches the local approved hash;
- publish/ship succeeded;
- the returned remote identity and status are stored;
- a post-publish read confirms the expected course revision.

Exit condition: verified remote result. A partial or ambiguous response never marks the course published.

## 7. Skill architecture

### 7.1 Teacher-facing director

#### `build-platform-course` (course-director role)

Responsibilities:

- own the teacher conversation;
- restore and reconcile Workflow state;
- choose the next legal stage;
- invoke specialist Skills and deterministic tools;
- convert raw issues into readable summaries;
- request one bounded set of teacher decisions at a time;
- persist accepted decisions before generating dependent work;
- prevent skipped gates;
- present preview and publication actions;
- never silently broaden the course or publication scope.

The existing `build-platform-course` Skill should be migrated toward this role rather than leaving two competing teacher entry points.

### 7.2 Internal specialist Skills

| Skill | Input | Output | May ask teacher? | May write final `course/course.json`? |
| --- | --- | --- | --- | --- |
| `analyze-course-materials` | selected course root and raw materials | inventory, extracted content, source coverage, candidate gaps | Through director | No |
| `design-course-blueprint` | approved brief, source coverage, decisions | authoring Blueprint and readable storyboard | Through director | No |
| `design-video-interactions` | confirmed video Block intent and actual media | validated cue design and interaction document | Through director | No |
| `design-course-html` | confirmed HTML Block intent | HTML design, implementation artifact, protocol/quality report | Through director | No |
| `compile-course-definition` | approved Blueprint and specialist artifacts | CourseDefinition 2.0, source map, compilation report | No | Yes; sole writer |
| `review-platform-course` | all sources, work records, final definition, assets, preview evidence | independent structured review | Through director only when a decision is required | No |
| `apply-preview-feedback` | open annotations, source map, current Blueprint | classified changes, proposed revision, resolved/orphaned annotations | Through director for semantic changes | No direct final write; updates Blueprint after approval |
| `publish-platform-course` | approved definition, asset manifest, publish state, dry-run approval | upload/API results and verified remote state | Final confirmation through director | No |

PDF and ordinary image checks do not require their own conversational Skill. They are deterministic tools plus decisions recorded in the Blueprint. A new Skill is justified only when a domain needs a distinct reasoning protocol and teacher confirmation loop.

### 7.3 Specialist Skill protocol

Every internal Skill receives a bounded context and returns a structured result. It must not assume it owns the overall course lifecycle.

```ts
interface SpecialistSkillInput {
  courseRoot: string
  workflowPhase: CourseProductionPhase
  allowedReadPaths: string[]
  allowedWritePaths: string[]
  artifactRefs: Record<string, string>
  confirmedDecisionIds: string[]
  activeIssueIds: string[]
}

interface SpecialistSkillResult {
  status: "completed" | "waiting-for-teacher" | "blocked" | "failed"
  artifactsCreatedOrUpdated: string[]
  issueUpserts: CourseProductionIssue[]
  issueIdsResolved: string[]
  proposedTeacherDecisions: TeacherDecisionRequest[]
  invalidatedArtifactIds: string[]
  summary: string
}
```

Specialist Skills must:

- stay within their allowed paths;
- return issues instead of hiding failures in prose;
- return proposed semantic changes instead of silently applying them;
- identify every artifact they changed;
- be safe to call again with unchanged inputs;
- never call the publication API unless they are the publisher and G9 is approved.

## 8. Authoring and runtime data model

### 8.1 Sources of truth

| Data | Source of truth | Notes |
| --- | --- | --- |
| Original materials | `materials/` and explicitly referenced root files | Treated as teacher-owned inputs; never overwritten |
| Teacher decisions | `.course-work/decisions.json` | Append/update through stable decision IDs |
| Unresolved questions | `.course-work/unresolved.json` | Blocking and non-blocking items |
| Authoring course design | `.course-work/course-blueprint.json` | Editable semantic design truth |
| Student runtime definition | `course/course.json` | Deterministically generated CourseDefinition 2.0; do not hand-edit |
| Authoring-runtime mapping | `.course-work/course-runtime-source-map.json` | Maps runtime IDs to Blueprint/source elements |
| Preview comments | `.course-work/annotations.json` | Never enters CourseDefinition |
| Asset upload knowledge | `.course-work/asset-manifest.json` | Local/remote hash and upload state |
| Remote course identity | `.course-work/publish-state.json` | Prevents create/update ambiguity |
| Exact publication approval | `.course-work/publication-preflight.json` | Hash-binds mode, identity, revision, assets, status, visibility, and review evidence |
| Recoverable publication attempt | `.course-work/publication-operation.json` | Persists verified uploads, ambiguous-write recovery, and remote read-back; live mode is required for G10 |

The previous authoring contract's schemaVersion 1.1 may be imported as source material, but it is not the final runtime truth. The new compiler emits only the shared student CourseDefinition 2.0 contract.

### 8.2 Recommended directory layout

```text
course-project/
├── index.md
├── materials/
├── course/
│   ├── course.json
│   └── assets/
└── .course-work/
    ├── session.json
    ├── materials-index.json
    ├── source-coverage.json
    ├── course-brief.json
    ├── decisions.json
    ├── issues.json
    ├── unresolved.json
    ├── course-blueprint.json
    ├── course-runtime-source-map.json
    ├── media/
    ├── annotations.json
    ├── validation-report.json
    ├── preview-manifest.json
    ├── review-report.json
    ├── asset-manifest.json
    ├── publish-state.json
    ├── publication-review-evidence.json
    ├── remote-discovery.json
    ├── publication-preflight.json
    └── publication-operation.json
```

Only `course/` is the uploadable course package. `.course-work/` is the resumable authoring record and must not be submitted as student content.

## 9. Issue, warning, and decision model

All Skills and tools write to one issue store. Human-readable Markdown is a generated view, not a second issue source.

One versioned issue-code registry defines every `code`, its default severity, responsible gate, whether teacher acknowledgement is permitted, and the minimum evidence fields. Skills and tools emit registered codes and cannot redefine their policy in prose.

```ts
type IssueSeverity = "blocker" | "decision-required" | "warning" | "info"
type IssueStatus = "open" | "accepted" | "resolved" | "dismissed" | "stale"

interface CourseProductionIssue {
  id: string
  fingerprint: string
  code: string
  severity: IssueSeverity
  status: IssueStatus
  gateId: string
  source: "workflow" | "skill" | "contract" | "asset" | "preview" | "review" | "publish"
  target?: {
    artifact?: string
    partId?: string
    sliceId?: string
    blockId?: string
    itemId?: string
    assetPath?: string
  }
  message: string
  evidence?: string[]
  remediation?: string
  warningPolicy?: "no-acknowledgement-required" | "teacher-acknowledgement-required-before-publish"
  teacherDecisionId?: string
  firstSeenAt: string
  lastSeenAt: string
}
```

`fingerprint` deduplicates the same finding across repeated runs while allowing its evidence and last-seen time to update.

### 9.1 Severity behavior

#### Blocker

Examples:

- invalid CourseDefinition;
- missing or corrupt required asset;
- Workflow dead end or bypassed required completion;
- unplayable video profile;
- HTML completion protocol or payload failure;
- damaged PDF;
- ambiguous remote course identity;
- required annotation still open.

Behavior: blocks the relevant gate and all later gates. It cannot be accepted as risk.

#### Decision required

Examples:

- unclear objective;
- ambiguous correct answer;
- proposed AI-added teaching claim;
- replacement or removal of teacher material;
- substantive Layout/Workflow change;
- media substitution.

Behavior: waits for an explicit teacher decision. Once answered, the issue resolves and the decision is stored.

#### Warning

Examples:

- dense Slice;
- long video or sparse meaningful cue coverage;
- missing optional captions under an allowed policy;
- long PDF with weak reading direction;
- possible visual overflow;
- HTML audio subject to browser autoplay fallback.

Behavior: does not block preview. Every warning code has a fixed policy in the issue-code registry: either no acknowledgement is required, or teacher acknowledgement is required before publication. Skills cannot choose the policy ad hoc. Acceptance includes rationale and scope; it is not a silent boolean.

#### Info

Examples:

- normalized generated filename;
- asset skipped because the hash matches the remote record;
- source map regenerated;
- validator passed;
- remote course updated rather than recreated.

Behavior: shown in summaries only when useful; never requires confirmation.

### 9.2 Teacher decisions

```ts
interface TeacherDecision {
  id: string
  question: string
  context: string
  options?: string[]
  answer: string
  affectedArtifactIds: string[]
  decidedAt: string
  invalidatedAt?: string
}
```

A decision becomes invalid when the context it decided has materially changed. The Workflow must surface invalidated decisions rather than silently reusing them.

## 10. Preview and annotation loop

### 10.1 Preview boundary

The local preview shell wraps the same `course-renderer` package used by the student platform. It provides these preview-only adapters:

- local `AssetResolver`;
- in-memory CourseSession;
- authored fallback Opening and Closing text;
- no TTS requirement;
- diagnostics and annotation overlays outside the renderer.

The preview shell must not fork Block rendering, Layout behavior, Workflow behavior, or media behavior.

### 10.2 Preview manifest

`.course-work/preview-manifest.json` records:

- CourseDefinition hash;
- course-contract version;
- course-runtime version;
- course-renderer version;
- preview-shell version;
- supported viewport used;
- visited Slice IDs;
- exercised interaction/branch IDs;
- created time and last review time.

Changing the definition or renderer invalidates the affected preview evidence.

### 10.3 Annotation contract

```ts
type AnnotationType = "content" | "layout" | "workflow" | "media" | "bug" | "question"
type AnnotationStatus = "open" | "proposed" | "accepted" | "applied" | "verified" | "dismissed" | "orphaned"

interface CourseAnnotation {
  id: string
  type: AnnotationType
  status: AnnotationStatus
  required: boolean
  target: {
    courseId: string
    partId?: string
    sliceId?: string
    blockId?: string
    itemId?: string
    workflowStepId?: string
  }
  definitionHash: string
  text: string
  screenshotPath?: string
  createdAt: string
  proposedChange?: string
  resolutionDecisionId?: string
  verifiedAgainstDefinitionHash?: string
}
```

Annotations target stable semantic IDs, never CSS selectors, pixel coordinates, or array positions.

### 10.4 Revision behavior

`apply-preview-feedback` must:

1. load open annotations;
2. validate each target against the current definition and source map;
3. mark missing targets `orphaned` and explain why;
4. classify requested changes as mechanical or semantic;
5. apply safe mechanical changes;
6. present semantic changes for teacher confirmation;
7. update the Blueprint rather than hand-edit CourseDefinition;
8. recompile;
9. rerun the smallest sufficient validation set;
10. mark annotations `applied`, but not `verified` until checked in a new preview built from the new definition hash.

## 11. Validation architecture

### 11.1 Validation layers

| Layer | Examples | Primary owner |
| --- | --- | --- |
| Structural | Zod shape, closed unions, field types | shared course-contract |
| Referential | IDs, objectives, slots, Blocks, narration, cues | shared course-contract plus compiler checks |
| Workflow | reachability, event producers, completion, navigation, bounded loops | shared course-contract/runtime validator |
| Asset | existence, paths, MIME/bytes, codecs, duration, PDF structure, HTML self-containment | deterministic authoring toolkit |
| Visual runtime | one-screen fit, overflow, focus, media behavior, interaction UI | shared renderer in real browser preview |
| Pedagogical | objective alignment, evidence, density, directions, correctness | independent review Skill plus teacher |
| Publication | identity, revisions, uploaded hashes, API readiness | publisher and remote API |

### 11.2 Validation report

`.course-work/validation-report.json` is the canonical machine-readable report. It contains:

- validator/tool versions;
- input hashes;
- checks run and checks skipped;
- issue IDs created or resolved;
- limitations, especially browser checks not yet performed;
- resulting eligibility: `not-compilable`, `compiled`, `previewable`, or `review-ready`.

Only the independent review may declare `publishable`.

### 11.3 Visual checks

Static heuristics may warn about excessive Blocks, text length, unsupported aspect combinations, or likely overflow. They cannot pass visual review. G7 requires the real renderer in a browser.

## 12. Asset manifest and upload idempotency

### 12.1 Asset manifest

```ts
interface AssetManifestEntry {
  sha256: string
  sizeBytes: number
  extension: string
  mimeType: string
  objectKey: string
  sources: string[]
  roles: string[]
  runtimePaths: string[]
  state: "upload-required" | "reusable"
  remote?: {
    objectKey: string
    uploadedSha256: string
    etag: string | null
    verifiedAt: string
  }
}
```

The manifest is rebuilt deterministically from current successful G6 evidence. One entry represents one unique hash inside the course namespace while `sources`, `roles`, and `runtimePaths` retain every consumer. Upload decisions compare the current local hash/object key with recorded verified remote state and adapter discovery.

Rules:

- unchanged hash: skip upload;
- changed hash at the same relative path: upload replacement only after validation;
- referenced asset without a valid local file: blocker;
- unreferenced file: warning or cleanup suggestion, never silently uploaded;
- remote upload success is recorded only after the response is verified;
- a failed partial batch resumes from `.course-work/publication-operation.json`, which records every verified upload before attempting the next one;
- the manifest is updated to reusable remote state only after the remote course read-back succeeds.

The first version guarantees deduplication within the same remote course namespace. Cross-course global deduplication is outside scope unless the platform later introduces a shared asset store.

## 13. Course identity and update idempotency

`.course-work/publish-state.json` stores:

```ts
interface PublishState {
  courseLocalId: string
  slug: string
  remoteCourseId?: string
  remoteStatus?: "preview" | "published"
  lastKnownRemoteRevision?: string
  lastUploadedDefinitionHash?: string
  lastPublishedDefinitionHash?: string
  lastPublishOperationId?: string
  verifiedAt?: string
}
```

Before create/update:

1. initialize `courseLocalId` and slug once; a different existing local identity is never overwritten;
2. query the stable slug through the discovery adapter;
3. if local state has no `remoteCourseId` but discovery finds a course, stop for explicit identity reconciliation; never silently adopt it;
4. update only when discovered `courseLocalId`, `remoteCourseId`, and remote revision match verified local state;
5. create only when local state has no remote ID and discovery explicitly proves `not-found`;
6. use the exact preflight hash, publisher code hash, adapter mode, definition hash, and per-asset hash to derive stable idempotency keys;
7. after an ambiguous response, discover and read before retrying; never issue a second blind create;
8. never mark success until remote identity, revision, definition hash, asset references, status, and visibility pass read-back verification.

Updating content must not create a new course. Publishing a new definition revision must not re-upload unchanged assets.

Definition revision must be distinct from schema version. The publisher records the remote revision/hash returned by the platform and uses it for optimistic update checks.

## 14. Security and operational boundaries

- Preview binds only to `127.0.0.1` by default.
- Preview reads only the selected course root and blocks path/symlink escape.
- Annotation writes are limited to `.course-work/annotations.json` and explicit screenshot storage.
- Skills do not store credentials.
- Publisher reads credentials through approved environment/keychain/agent configuration at operation time.
- Presigned URLs and tokens are not persisted in reports.
- HTML assets are sandboxed by the shared renderer and validated for prohibited network dependencies before publication.
- External mutations begin only after a dry run and explicit teacher confirmation.
- Publication logs redact secrets and retain stable operation IDs, hashes, paths, statuses, and error codes.

## 15. Failure and recovery behavior

### Tool or Skill failure

- Persist the last successful action before returning failure.
- Store a typed, readable failure record.
- Mark only affected gates invalid.
- Do not delete the last known-good compiled course or report.
- On resume, retry only safe idempotent actions or request confirmation when retry could mutate external state.

### Validation failure

- Keep the compiled artifact for diagnostics.
- Route the issue to the earliest responsible Blueprint/media/source phase.
- Re-run the smallest sufficient checks after correction.

### Preview failure

- Distinguish preview-shell failure, renderer failure, course-definition failure, and asset failure.
- Preserve annotations and CourseDefinition hash.
- Never convert “preview could not run” into a passed visual review.

### Upload failure

- Record each verified successful asset independently.
- Resume only missing or changed hashes.
- Do not submit the CourseDefinition as publish-ready until all referenced assets are verified remotely.

### Ambiguous API response

- Query remote state before retrying create/update/publish.
- If identity or revision cannot be established, stop with a blocker.
- Never issue another create request merely because the first response timed out.

## 16. Testing strategy

### 16.1 Workflow kernel tests

- every legal phase transition;
- every illegal transition;
- gate completion under matching hashes;
- targeted invalidation after each input class changes;
- restore after failure and teacher wait;
- issue deduplication and stale issue handling.

### 16.2 Skill scenario tests

- new course with complete materials;
- silent materials that still require video/HTML confirmation;
- resume with unresolved teacher decisions;
- semantic preview annotation requiring confirmation;
- mechanical annotation applied automatically;
- changed Blueprint invalidating preview/review;
- existing remote course updates rather than creates;
- repeated publish skips unchanged assets.

### 16.3 Compiler and validator fixtures

- one golden CourseDefinition covering every Block, Layout, Workflow event/action, navigation mode, and media type;
- negative fixtures for each contract and Workflow issue code;
- valid and invalid video profiles, captions, audio, PDF, and HTML;
- source-map stability across non-structural edits;
- stable IDs across recompilation.

### 16.4 Preview integration tests

Once the corrected student renderer is available:

- launch the local shell with real renderer packages;
- exercise all four Layouts;
- verify one-screen behavior;
- test PDF, video cue, HTML protocol/audio, assessment, narration, navigation, and Closing;
- create and reconcile annotations;
- prove preview invalidation when definition or renderer version changes.

### 16.5 Publishing integration tests

Against a mock server first, then a controlled preview environment:

- create preview course;
- update the same course;
- retry after timeout without duplicate creation;
- upload partial failure and resume;
- unchanged asset skip;
- changed asset replacement;
- remote revision conflict;
- publish verification.

## 17. Iteration plan

### Iteration 1 — Workflow kernel and one entry

Deliver:

- canonical directory and work-file layout;
- `session.json` state machine;
- gate engine and invalidation rules;
- unified issue/decision store;
- main director Skill that restores state and routes existing Skills;
- no preview or external publication required.

Success: an interrupted course-production session resumes at the correct phase and never skips an incomplete gate.

### Iteration 2 — Blueprint and CourseDefinition 2.0 compiler

Deliver:

- Course Blueprint contract;
- migration/import path from existing schemaVersion 1.1 courses;
- deterministic CourseDefinition 2.0 compiler;
- stable ID rules;
- runtime source map;
- direct dependency on the shared student course-contract.

Success: one real existing course compiles reproducibly into a valid CourseDefinition 2.0 package.

### Iteration 3 — Validation and reporting

Deliver:

- shared issue codes and report schema;
- strengthened Workflow checks;
- video, captions, audio, PDF, HTML, and asset-manifest validation;
- previewability and review-readiness gates;
- teacher-readable warning and blocker summaries.

Success: intentionally broken fixtures fail at the correct gate with actionable evidence.

### Iteration 4 — Annotation and revision protocol

Deliver before the real preview UI:

- annotation schema;
- source-map reconciliation;
- feedback classification;
- Blueprint revision workflow;
- recompile/revalidate loop;
- a mock annotation fixture and command-line/local-file workflow.

Success: a batch of content, layout, workflow, media, and bug annotations updates the right authoring elements without hand-editing CourseDefinition.

### Iteration 5 — Asset and publication client

Deliver against mock APIs:

- asset manifest and hash-based upload decisions;
- publish state and stable identity reconciliation;
- create/update dry run;
- safe retry and partial-upload resume;
- final teacher confirmation;
- remote verification contract.

Success: repeated publication updates one mock remote course and uploads only changed assets.

**Implemented on `dev`.** The local core now includes:

- a G6-bound content-addressed manifest with course-scoped object keys and per-hash reuse state;
- strict `publish-state` and remote discovery contracts that permit create only after explicit `not-found` and update only when local and remote identity/revision agree;
- a deterministic preflight bound to current G6, renderer-backed G8 evidence, discovery, identity, manifest, intended status, and visibility;
- one exact teacher approval whose context changes invalidate approval immediately;
- object-store and course-API protocols with stable idempotency keys, partial-upload resume, optimistic update revisions, ambiguous response discovery/read-back, and no blind second create;
- post-write verification before `publish-state` changes;
- an explicit `test` versus `live` adapter boundary: fake adapter operations cannot satisfy G10, and no teacher-facing execute command exists.

The implementation does not read credentials or perform a real OSS/API request. The local Workflow CLI intentionally refuses manual G9 and G10 completion.

### Iteration 6 — Student renderer and API integration

Deliver after the student platform closes the reviewed runtime gaps and supplies stable APIs:

- local preview shell using the shared renderer packages;
- real preview annotations;
- real asset upload and course create/update/publish adapters;
- renderer/contract compatibility manifest;
- end-to-end browser acceptance journey.

Success: teacher preview and student playback use the same CourseDefinition and rendering implementation.

### Iteration 7 — Real-course pilot and hardening

Run one real course through the full lifecycle:

```text
materials
→ brief
→ Blueprint
→ media designs
→ CourseDefinition 2.0
→ validation
→ preview
→ annotations
→ revision
→ independent review
→ asset upload
→ remote update
→ publication verification
```

Use pilot evidence to adjust issue wording, gate thresholds, recovery behavior, and Skill instructions. Do not change the shared contract merely to accommodate one course unless the requirement generalizes.

## 18. Acceptance criteria for the architecture

The architecture is successful when:

1. the teacher uses one entry for new, resumed, revised, and published courses;
2. the Workflow resumes deterministically and invalidates only stale work;
3. every substantive teaching change remains teacher-confirmed;
4. CourseDefinition 2.0 is generated, never manually maintained as authoring truth;
5. preview annotations map back to stable authoring elements;
6. all warnings and blockers use one structured issue model;
7. independent review is required after revision;
8. the same renderer is used for preview and student playback;
9. repeated updates target the same remote course;
10. unchanged assets are not uploaded again;
11. failed or ambiguous external operations are safely resumable;
12. the final published remote definition and assets are verified against the locally approved hashes.
