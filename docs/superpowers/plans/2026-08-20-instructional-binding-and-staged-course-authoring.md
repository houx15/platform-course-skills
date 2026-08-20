# Instructional Binding and Staged Course Authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn complete teacher materials into a teacher-approved page plan, a source-bound CourseDefinition 2.0, a visually checked local preview, a resolved annotation round, and an explicitly approved update-or-create publication without silently omitting, mismatching, hiding, or duplicating content.

**Architecture:** Extend the existing G0-G10 pipeline instead of creating another authoring system. G3 owns a complete Part/Slice instructional plan, G4 owns the teacher's hash-bound approval, G5 compiles the approved plan into the existing Blueprint and CourseDefinition, G6 requires deterministic binding/layout/runtime checks plus Agent-authored semantic and visual evidence, G7 owns explicit teacher verification, and G9/G10 continue to reuse the existing stable-slug publication machinery. All new approvals and reports are bound to source, plan, Blueprint, definition, asset-set, renderer, and preview-bundle hashes so a later edit invalidates exactly the evidence it made stale.

**Tech Stack:** Python 3.9+ standard library and `unittest`; TypeScript 5, React 18, Vite, Vitest, pnpm 10; existing `@mind-imprint/course-contract`, `course-runtime`, `course-renderer`, localhost preview server, publication preflight, OSS/API adapters, and atomic JSON helpers.

---

## Scope decision

This remains one implementation plan because the approved feature is one hash-bound authoring pipeline. Tasks are independently committable, but splitting plan approval, semantic binding, visual evidence, annotations, and publication readiness into separate products would recreate the drift this work is intended to prevent.

No worktree is required. Preserve unrelated untracked files and existing teacher course data. Do not perform a real OSS/API mutation while implementing or testing this plan.

## File map

### New instructional records and checks

- Create `course_toolkit/instructional_bindings.py`: source-coverage v2 schema, Part/Slice/Block destination validation, material-use audit, and v1 migration.
- Create `course_toolkit/instructional_plan.py`: page-plan schema, teacher-readable Markdown, content hash, approval, and invalidation verification.
- Create `course_toolkit/instructional_audit.py`: hash-bound Agent semantic audit and deterministic verification.
- Create `course_toolkit/prepreview_visual.py`: hash-bound renderer visual report, state coverage, blocker verification, and repair-round limit.
- Create `scripts/manage-course-plan.py`: validate, render, approve, and inspect the page plan.
- Create `scripts/record-instructional-audit.py`: validate and persist the Agent semantic audit.
- Create `scripts/record-prepreview-visual.py`: validate and persist the Agent visual report.

### Existing pipeline integration

- Modify `course_toolkit/package_review.py`: replace legacy Piece destinations with Slice destinations and surface instructional failures.
- Modify `course_toolkit/course_package_validation.py`: include binding, plan-correspondence, semantic-audit, and layout/workflow results.
- Modify `course_toolkit/workflow.py`: move Blueprint ownership to G5; require plan approval at G4 and all pre-preview evidence at G6; invalidate downstream evidence precisely.
- Modify `course_toolkit/preview_evidence.py`: stop auto-verifying applied annotations and require explicit verification.
- Modify `course_toolkit/preview_server.py`: add inspection, annotation-transition, publication-status, prepare, and execute endpoints without exposing credentials.
- Create `course_toolkit/preview_publication.py`: one local controller over existing publication preflight and publisher operations.
- Modify `scripts/preview-course.py`: support `--inspection` before G6 completion and ordinary teacher preview only after G6.

### Preview UI

- Modify `preview_app/src/previewApi.ts`: inspection, explicit annotation verification, and publication controller types.
- Modify `preview_app/src/AnnotationPanel.tsx`: teacher-facing annotation lifecycle and two-step Publish control.
- Modify `preview_app/src/PreviewCoursePlayer.tsx`: inspection mode, stable target attributes, state observation, and annotation-mode separation.
- Modify `preview_app/src/styles.css`: clear inspection/publish states without changing student renderer CSS.

### Skills, migration, and verification

- Modify `skills/build-platform-course/SKILL.md`: explain the four teacher phases, produce the plan before runtime detail, and continue automatically between meaningful approvals.
- Modify `skills/analyze-course-materials/SKILL.md`: require full inventory and explicit dispositions.
- Modify `skills/design-course-blueprint/SKILL.md`: implement only an approved plan and keep source relationships intact.
- Modify `skills/preview-platform-course/SKILL.md`: run semantic and visual checks before teacher preview; distinguish inspection from annotation mode.
- Modify `skills/apply-preview-feedback/SKILL.md`: preserve immutable review rounds and explicitly verify fixes.
- Modify `skills/publish-platform-course/SKILL.md`: use preview publication preparation and final confirmation; tell teachers to share via the student platform/Phoebe account.
- Modify `README.md`: teach an Agent the same flow, including new versus partially completed courses.
- Create `scripts/migrate-instructional-authoring.py`: non-destructive migration for legacy in-progress courses.
- Create `tests/fixtures/instructional-binding-course/`: small Chinese source set and expected records.
- Create focused Python and preview-app tests listed in the tasks below.

## Artifact contract

Use the approved design names except where a current canonical artifact already exists:

- `.course-work/source-coverage.json` becomes schema `2.0` and remains the only source disposition/binding record.
- `.course-work/course-storyboard.json` becomes schema `2.0` and remains the only approved page plan.
- `.course-work/course-storyboard.md` is a generated teacher view and never an approval source.
- `.course-work/instructional-audit.json` stores source-grounded semantic evidence.
- `.course-work/prepreview-visual-report.json` stores renderer-backed Agent inspection evidence.
- `.course-work/publication-preflight.json` remains the concrete publication plan. Do not introduce a competing `publication-plan.json`.

### Task 1: Introduce source-coverage v2 with real Part/Slice/Block bindings

**Files:**
- Create: `course_toolkit/instructional_bindings.py`
- Create: `tests/test_instructional_bindings.py`
- Modify: `course_toolkit/package_review.py:314`

- [ ] **Step 1: Write failing tests for dispositions, destinations, and locators**

```python
def test_required_evidence_must_bind_to_a_real_slice_block():
    audit = audit_instructional_bindings(ROOT)
    assert [issue.code for issue in audit.blockers] == ["binding-target-missing"]

def test_optional_support_may_be_unused_only_with_a_reason():
    audit = audit_instructional_bindings(ROOT)
    assert [issue.code for issue in audit.blockers] == ["optional-support-reason-missing"]

def test_pdf_segment_binding_preserves_page_locator():
    document = load_coverage(ROOT)
    assert document["items"][0]["location"] == "page:7/figure:2"
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m unittest tests.test_instructional_bindings -v`

Expected: import failure because `instructional_bindings.py` does not exist.

- [ ] **Step 3: Implement the v2 schema and audit**

Define exactly these dispositions:

```python
DISPOSITIONS = {
    "required-core", "required-evidence", "optional-support",
    "authoring-only", "exclude-proposed", "exclude-approved",
}

@dataclass(frozen=True)
class BindingAudit:
    blockers: Sequence[ValidationIssue]
    warnings: Sequence[ValidationIssue]
```

The public functions are `load_instructional_coverage(root: Path) -> dict`, `migrate_coverage_v1(document: dict, course: dict) -> dict`, `collect_course_destinations(course: dict) -> Dict[Tuple[str, str, str], dict]`, and `audit_instructional_bindings(root: Path) -> BindingAudit`.

The collector must traverse `course.parts[].slices[].blocks[]`. Required material must have at least one binding; every binding target must exist and must reference the declared source asset or source-map entry. `exclude-proposed` is allowed before first preview but blocks publication. `exclude-approved` requires reason, decision ID, and teacher confirmation. `authoring-only` never requires learner binding. Optional unused material requires a concrete reason and remains visible in the summary.

- [ ] **Step 4: Replace `_course_destinations` with the shared Slice collector**

Remove the legacy `pieces` traversal from `package_review.py`; import the shared collector so review and G6 cannot disagree.

- [ ] **Step 5: Run tests and commit**

Run: `python3 -m unittest tests.test_instructional_bindings tests.test_package_review tests.test_package_review_v2 -v`

Commit: `feat: add instructional source bindings`

### Task 2: Create the complete page-plan schema and teacher view

**Files:**
- Create: `course_toolkit/instructional_plan.py`
- Create: `scripts/manage-course-plan.py`
- Create: `tests/test_instructional_plan.py`

- [ ] **Step 1: Write failing schema and rendering tests**

```python
def test_plan_requires_one_row_for_every_planned_slice():
    with self.assertRaisesRegex(InstructionalPlanError, "sliceId"):
        validate_plan(incomplete_plan, coverage)

def test_teacher_markdown_names_purpose_material_action_layout_and_unused_items():
    text = render_teacher_plan(plan, coverage)
    for heading in ("教学目的", "素材", "学生行动", "排版", "未使用或仅用于备课"):
        self.assertIn(heading, text)
```

- [ ] **Step 2: Implement a strict plan body**

Each Slice record must contain `partId`, `sliceId`, `title`, `teachingPurpose`, `sourceUses`, `learnerSees`, `learnerAction`, `completionEvidence`, `layoutIntent`, `coVisibleRequirements`, `imageRelationships`, `unresolvedBlockers`, and `proposedExclusions`. Reject duplicate IDs, unknown source IDs, empty purposes/actions, unsupported presets, an answer task without completion evidence, and a reference-dependent action without a co-visible requirement.

Approval is stored inside the same document but excluded from its content hash:

```python
def plan_content_hash(document: dict) -> str:
    return canonical_json_hash({key: value for key, value in document.items() if key != "approval"})

```

Implement `approve_plan(root: Path, *, decision_id: str, approved_at: str) -> dict` and `verify_plan_approval(root: Path) -> Dict[str, str>` as the only approval write/read interfaces.

`verify_plan_approval` must match the current source-inventory hash, source-coverage hash, plan body hash, decision ID, and `teacherConfirmed: true`.

- [ ] **Step 3: Implement the CLI**

Commands:

```text
python3 scripts/manage-course-plan.py COURSE_ROOT validate
python3 scripts/manage-course-plan.py COURSE_ROOT render
python3 scripts/manage-course-plan.py COURSE_ROOT approve --decision-id DECISION_ID
python3 scripts/manage-course-plan.py COURSE_ROOT status
```

`render` writes `.course-work/course-storyboard.md` atomically. `approve` never edits the plan body and is invoked only after the teacher explicitly confirms the displayed plan.

- [ ] **Step 4: Verify and commit**

Run: `python3 -m unittest tests.test_instructional_plan -v`

Commit: `feat: add teacher approved page plans`

### Task 3: Put plan approval into G3-G5 without exposing gates to teachers

**Files:**
- Modify: `course_toolkit/workflow.py`
- Modify: `scripts/course-workflow.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_workflow_cli.py`

- [ ] **Step 1: Write failing gate and invalidation tests**

Cover these invariants:

1. G3 completion requires current `source-coverage.json` and `course-storyboard.json`.
2. G4 completion requires current teacher approval plus media-design evidence.
3. G5, not G3, owns `course-blueprint.json`.
4. Changing Slice order, purpose, source selection, learner action, completion evidence, main preset, or substantive disposition invalidates G4 onward.
5. Copy edits and workflow implementation refinements preserve G4 but invalidate G5 onward.

- [ ] **Step 2: Add evidence keys and artifact ownership**

```python
G3_EVIDENCE_KEYS = (
    ".course-work/source-coverage.json",
    ".course-work/course-storyboard.json",
)
G4_EVIDENCE_KEYS = (
    ".course-work/course-storyboard.json",
    ".course-work/media-design.json",
    "@decision/course-plan-approval",
)
```

Move `.course-work/course-blueprint.json` from the G3 artifact rule to G5. Preserve existing gate IDs and teacher-facing phase names.

- [ ] **Step 3: Verify approval at completion time**

Call `verify_plan_approval` when completing G4; merge its hashes into evidence. Artifact reconciliation must compare the plan's semantic projection separately from its generated Markdown and approval metadata.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest tests.test_workflow tests.test_workflow_cli -v`

Commit: `feat: gate production on page plan approval`

### Task 4: Audit compiled CourseDefinition against the approved plan

**Files:**
- Create: `course_toolkit/instructional_validation.py`
- Create: `tests/test_instructional_validation.py`
- Modify: `course_toolkit/course_package_validation.py`

- [ ] **Step 1: Write RED tests for the four observed failure classes**

Fixtures must demonstrate:

- a required image omitted from the course;
- text and a question stacked in one split side while the other side is empty;
- an image bound to the wrong question;
- text saying “参考上面的原文” without the referenced PDF/source in the same Slice.

Each must emit a stable code and exact Part/Slice/Block path. Also test a valid co-visible reference-and-answer Slice.

- [ ] **Step 2: Implement deterministic plan correspondence**

The public checks are `validate_plan_correspondence(root: Path, course: dict) -> List[ValidationIssue]`, `validate_layout_assignment(course: dict) -> List[ValidationIssue]`, and `validate_workflow_availability(course: dict) -> List[ValidationIssue]`.

Check every planned Slice and Block relationship, empty slots, duplicate/unassigned Blocks, required co-visibility, stable image/question support IDs, reachable completion events, reveal/enable ordering, and source-path/source-map identity. Do not guess semantic similarity here; Task 5 records that judgment.

- [ ] **Step 3: Add results to the existing G6 report**

Keep one `.course-work/course-validation-report.json`. Add `layers.instructionalBinding`, `layers.planCorrespondence`, and `layers.layoutWorkflow`; preserve existing contract, HTML, PDF, video, VTT, and asset checks.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest tests.test_instructional_validation tests.test_course_package_validation -v`

Commit: `feat: validate course against approved teaching plan`

### Task 5: Add a hash-bound Agent semantic audit

**Files:**
- Create: `course_toolkit/instructional_audit.py`
- Create: `scripts/record-instructional-audit.py`
- Create: `tests/test_instructional_audit.py`

- [ ] **Step 1: Write failing contract tests**

Reject a report with missing Slice coverage, unrecognized source IDs, missing evidence text, stale plan/Blueprint/definition hashes, or a waived blocker. Accept uncertainty only as a review item with two concrete plausible arrangements.

- [ ] **Step 2: Implement the report contract**

```python
SEMANTIC_CHECKS = (
    "image-supports-assigned-claim",
    "question-answerable-from-declared-evidence",
    "deictic-reference-resolves",
    "required-reference-co-visible",
    "teacher-correctness-preserved",
    "source-claim-not-over-reduced",
)

```

Expose `record_instructional_audit(root: Path, payload: dict) -> dict` for the atomic write and `verify_instructional_audit(root: Path) -> Dict[str, str>` for gate evidence.

Every Slice/check entry records `status: pass|blocker|review`, source IDs, target IDs, and concise evidence. Any blocker prevents teacher preview. A review item requires an explicit teacher decision before it can become pass; the recorder must never silently downgrade it.

- [ ] **Step 3: Implement CLI input safely**

The Agent writes a candidate JSON file under `.course-work/candidates/` and invokes the recorder with that file. The CLI validates before atomically replacing `.course-work/instructional-audit.json`; it never accepts arbitrary JSON as a command-line string.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest tests.test_instructional_audit -v`

Commit: `feat: record source grounded instructional audit`

### Task 6: Define mandatory renderer-backed visual evidence

**Files:**
- Create: `course_toolkit/prepreview_visual.py`
- Create: `scripts/record-prepreview-visual.py`
- Create: `tests/test_prepreview_visual.py`

- [ ] **Step 1: Write failing coverage and freshness tests**

Require every Slice's initial, narration-complete, action-ready, and final-pre-completion states, plus reachable answer branches, video modals, and HTML states declared by the course. Reject missing screenshots, invalid SHA-256, stale renderer/bundle/assets, off-screen required Blocks, runtime errors, unresolved blockers, and a fourth repair attempt.

- [ ] **Step 2: Implement a browser-tool-neutral evidence contract**

```python
VISUAL_REPORT_VERSION = "1.0"
MAX_AUTONOMOUS_REPAIR_ROUNDS = 3

```

Expose `expected_visual_states(course: dict) -> Sequence[str]`, `record_visual_report(root: Path, payload: dict) -> dict`, and `verify_prepreview_visual(root: Path) -> Dict[str, str>`.

Each state stores viewport, screenshot relative path/hash, visible/enabled Block IDs, DOM rectangles, overflow/occlusion/scroll/focus observations, runtime errors, relevant plan bindings, and Agent findings. Screenshots must remain inside `.course-work/visual-check/screenshots/` and cannot cross symlinks. If browser control or screenshot capture is unavailable, recording fails and teacher preview remains blocked.

- [ ] **Step 3: Encode blocker rules**

Block missing/zero-size/off-screen/occluded/unreachable content, empty split sides, large dead regions, unreadably small media/text, aspect distortion, incorrect reading order, broken co-visibility, unexpected core-task scrolling, and plan/screenshot contradiction. A successful report has `blockerCount: 0` and current hashes.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest tests.test_prepreview_visual -v`

Commit: `feat: require prepreview visual evidence`

### Task 7: Add inspection mode to the real preview renderer

**Files:**
- Modify: `scripts/preview-course.py`
- Modify: `course_toolkit/preview_server.py`
- Modify: `preview_app/src/PreviewCoursePlayer.tsx`
- Modify: `preview_app/src/previewApi.ts`
- Modify: `preview_app/src/styles.css`
- Modify: `tests/test_preview_server.py`
- Modify: `preview_app/src/PreviewCoursePlayer.test.tsx`

- [ ] **Step 1: Write RED tests for inspection isolation**

Assert that `--inspection` may run after current G5 compilation plus a non-blocked static report, ordinary teacher preview still requires completed G6, the annotation panel starts collapsed/disabled in inspection mode, and the DOM observer returns stable Block IDs, rectangles, visibility, enablement, overflow, and runtime errors. The server pins the definition hash at launch and returns `409 preview_version_changed` if the course is edited while that inspection or teacher review session remains open.

- [ ] **Step 2: Add the localhost inspection API**

Expose `GET /__course_preview/inspection/config` and `POST /__course_preview/inspection/observations`. The server issues a per-launch inspection nonce and accepts observations only for its pinned definition hash. The mounted preview client derives observations from the actual renderer DOM and runtime state; the server validates stable target IDs against the CourseDefinition before accepting them. Keep all existing loopback, root-confinement, no-store, and size limits.

- [ ] **Step 3: Instrument without forking student styles**

Add wrapper-level `data-preview-target-*` attributes or observe existing renderer IDs. Do not copy or override student renderer typography/layout CSS. If the renderer lacks stable target attributes, make the smallest additive change in `packages/course-renderer` and update its tests.

- [ ] **Step 4: Verify and commit**

Run:

```text
python3 -m unittest tests.test_preview_server -v
pnpm test:preview -- PreviewCoursePlayer.test.tsx
pnpm typecheck:preview
```

Commit: `feat: add renderer inspection mode`

### Task 8: Make G6 the true pre-preview quality gate

**Files:**
- Modify: `course_toolkit/workflow.py`
- Modify: `course_toolkit/course_package_validation.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_course_package_validation.py`

- [ ] **Step 1: Write failing G6 evidence tests**

G6 must fail for missing/stale instructional audit, missing/stale visual report, any semantic or visual blocker, or unsynchronized binding/layout/runtime findings. A clean current set must pass and emit hashes for every layer. A defensible semantic review item and `exclude-proposed` remain visible warnings that may enter the first teacher preview; they block G8/publication readiness until the teacher decides, approves, or remaps them.

- [ ] **Step 2: Extend G6 evidence**

```python
G6_EVIDENCE_KEYS = (
    ".course-work/course-validation-report.json",
    ".course-work/instructional-audit.json",
    ".course-work/prepreview-visual-report.json",
    "@toolkit/course-package-validator",
    "@toolkit/instructional-audit",
    "@toolkit/prepreview-visual",
    "@course/asset-set",
)
```

Call all three verifiers during G6 completion. A changed plan, Blueprint, definition, asset, renderer package, preview bundle, stylesheet, or visual viewport profile must invalidate G6 and later gates. Persist warnings and teacher review items into the issue/annotation surfaces without converting them to passes.

- [ ] **Step 3: Add the bounded repair loop to the Skill contract**

The deterministic tool counts repair rounds; the Skill may repair and rerun at most three times for the same pre-preview version. On the third repeated blocker it reports the exact blocker to the teacher and stops instead of waiving it.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest tests.test_workflow tests.test_course_package_validation tests.test_prepreview_visual -v`

Commit: `feat: block preview until instructional visual checks pass`

### Task 9: Require explicit annotation verification

**Files:**
- Modify: `course_toolkit/preview_evidence.py`
- Modify: `course_toolkit/preview_server.py`
- Modify: `preview_app/src/previewApi.ts`
- Modify: `preview_app/src/AnnotationPanel.tsx`
- Modify: `tests/test_preview_evidence.py`
- Modify: `tests/test_preview_server.py`
- Modify: `preview_app/src/AnnotationPanel.test.tsx`

- [ ] **Step 1: Write a failing regression test**

An `applied` annotation must remain `applied` after visiting every Slice and posting preview evidence. G7 must remain blocked until the teacher explicitly verifies it against the current definition hash.

- [ ] **Step 2: Remove automatic promotion**

Delete the `applied -> verified` loop in `_load_annotations`. Add a strict transition endpoint that loads the current annotation, validates a legal transition, and supplies the current definition hash when transitioning to `verified`.

- [ ] **Step 3: Present the approved teacher lifecycle**

Keep the storage enum backward compatible, but map it in the UI as:

```text
open -> 待处理
proposed|accepted -> 处理中
applied -> 待老师验证
verified -> 已验证
dismissed -> 不修改/已处理
orphaned -> 目标失效（阻塞）
```

An applied required annotation shows `确认修改有效` and `重新打开`. A required dismissal keeps a resolution decision. Deletion remains allowed only for an open teacher-authored annotation; later lifecycle records are resolved rather than erased.

- [ ] **Step 4: Run and commit**

Run:

```text
python3 -m unittest tests.test_preview_evidence tests.test_preview_server tests.test_annotations -v
pnpm test:preview -- AnnotationPanel.test.tsx
```

Commit: `fix: require teacher verification of preview changes`

### Task 10: Add safe two-step publication controls to local preview

**Files:**
- Create: `course_toolkit/preview_publication.py`
- Create: `tests/test_preview_publication.py`
- Modify: `course_toolkit/preview_server.py`
- Modify: `preview_app/src/previewApi.ts`
- Modify: `preview_app/src/AnnotationPanel.tsx`
- Modify: `preview_app/src/styles.css`
- Modify: `tests/test_preview_server.py`
- Modify: `preview_app/src/AnnotationPanel.test.tsx`

- [ ] **Step 1: Write failing readiness and security tests**

Publish is disabled unless G7 and G8 are current, required annotations are verified/dismissed with decisions, the instructional/visual reports remain current, and the stable catalog selection exists. Preview requests must never return the admin key. Execute must reject a missing/stale preflight hash, absent confirmation nonce, ambiguous create/update identity, or changed local files.

- [ ] **Step 2: Implement a controller over existing publication modules**

Create `PreviewPublicationController` with `status() -> dict`, `prepare() -> dict`, and `execute(*, preflight_hash: str, confirmation_nonce: str) -> dict` methods.

`prepare` calls the existing publication preflight and returns the exact teacher-readable create/update, upload/reuse, cover, ship/TTS, and readback plan. `execute` rechecks every local and remote hash, consumes a one-time in-memory nonce, reads credentials only from the ignored `.env`/process environment through existing code, and delegates to the existing publisher. It does not implement a second uploader or API client. On partial failure it performs remote readback, reports the observed preview/published state, and prevents a blind retry until a new preflight is prepared.

- [ ] **Step 3: Add preview endpoints and UI**

Endpoints:

```text
GET  /__course_preview/publication/status
POST /__course_preview/publication/prepare
POST /__course_preview/publication/execute
```

The UI first shows `准备发布计划`, then the exact plan, then `我确认按此计划发布`. It states that local links only work on this computer and that collaborators should review the published course through the student platform/Phoebe account. Do not offer ZIP export or copy/re-upload.

- [ ] **Step 4: Run and commit**

Run:

```text
python3 -m unittest tests.test_preview_publication tests.test_preview_server tests.test_publication_preflight tests.test_publisher_orchestrator -v
pnpm test:preview -- AnnotationPanel.test.tsx
pnpm typecheck:preview
```

Commit: `feat: publish reviewed courses from local preview`

### Task 11: Migrate partially completed courses non-destructively

**Files:**
- Create: `scripts/migrate-instructional-authoring.py`
- Create: `course_toolkit/instructional_migration.py`
- Create: `tests/test_instructional_migration.py`
- Modify: `tests/test_real_course_migration.py`

- [ ] **Step 1: Write RED migration tests**

Given a legacy in-progress course, preserve the course folder, fixed catalog selection/slug, local course ID, source files, asset manifest, upload hashes, annotations, Blueprint, and compiled definition. Convert legacy `Part/Piece/Block` coverage to `Part/Slice/Block`; reverse-generate an unapproved page plan; identify the earliest invalid gate; never create or upload a remote course.

- [ ] **Step 2: Implement dry-run-first migration**

Commands:

```text
python3 scripts/migrate-instructional-authoring.py COURSE_ROOT inspect
python3 scripts/migrate-instructional-authoring.py COURSE_ROOT apply
```

`inspect` makes no writes. `apply` writes a timestamped backup under `.course-work/migration-backups/`, migrates atomically, and prints the next teacher-visible step. If legacy destinations cannot map unambiguously, keep them as explicit blockers instead of guessing.

- [ ] **Step 3: Resume from the earliest invalid gate**

A valid old compile with a newly generated unapproved plan resumes at plan approval. A stale/mismatched Blueprint resumes at production. Existing `asset-manifest.json` and `publish-state.json` remain intact so unchanged materials continue to reuse OSS objects.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest tests.test_instructional_migration tests.test_real_course_migration -v`

Commit: `feat: migrate in progress courses to staged authoring`

### Task 12: Teach the Skills the four-phase teacher conversation

**Files:**
- Modify: `skills/build-platform-course/SKILL.md`
- Modify: `skills/analyze-course-materials/SKILL.md`
- Modify: `skills/design-course-blueprint/SKILL.md`
- Modify: `skills/preview-platform-course/SKILL.md`
- Modify: `skills/apply-preview-feedback/SKILL.md`
- Modify: `skills/publish-platform-course/SKILL.md`
- Modify: `tests/test_skill_packages.py`
- Modify: `tests/skill_scenarios/**`

- [ ] **Step 1: Add failing Skill scenario assertions**

The baseline scenarios must prove that an Agent:

- starts with the approved Chinese introduction;
- inventories all material and asks specifically about video/HTML intent when needed;
- prepares the page plan and unused-material summary before detailed generation;
- asks once for plan approval, then continues autonomously through production and Visual Check;
- never invents video questions absent from teacher input;
- reports exclusions and semantic uncertainty precisely;
- opens teacher preview only after G6;
- does not mutate the reviewed version until annotations are submitted;
- tells the teacher to publish to the student platform for other reviewers;
- never asks the teacher to choose `auto` mode, JSON fields, validators, or gate IDs.

- [ ] **Step 2: Update the director Skill**

Use exactly four teacher-facing phases: `理解材料`, `确认逐页计划`, `制作并自检`, `预览并发布`. After the plan approval, internal deterministic steps proceed without repeated confirmation unless there is a genuine correctness choice, a persistent blocker, or the final external publication mutation.

- [ ] **Step 3: Update specialist boundaries**

The analyzer owns inventory/disposition; designer owns approved-plan implementation; preview owns semantic/visual self-check and annotation rounds; feedback owns immutable-version rebuilds; publisher owns exact prepare/confirm/execute. Each specialist returns evidence to the director and never addresses the teacher as a separate product.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest tests.test_skill_packages -v`

Commit: `docs: teach staged instructional authoring flow`

### Task 13: Update the Agent-readable README and installer payload

**Files:**
- Modify: `README.md`
- Modify: `scripts/install-skills.py`
- Modify: `tests/test_installer.py`
- Create: `tests/test_readme_teacher_journey.py`

- [ ] **Step 1: Write failing documentation tests**

Assert that README tells an Agent how to handle a new course and a previously half-processed course, requires `.course-work` beneath the course's own folder, distinguishes local preview from collaborator review, and names the three teacher confirmations only: page plan, review completion/fixes, and final publication plan.

- [ ] **Step 2: Rewrite the operational journey**

Make the default path conversational and non-technical. Explain that the teacher selects the fixed course name; fixed category/cards/introduction/cover are mapped by code; the Agent inventories, plans, self-checks, previews, resolves annotations, and publishes. State that one course gets one folder and one `.course-work`; a second course starts in a new folder. State that saving the same stable slug updates the course and hashes prevent duplicate unchanged uploads.

- [ ] **Step 3: Include every new module/script in installation**

Extend installer manifest tests so installed Skills can call plan, semantic audit, visual report, migration, and preview publication code without referring back to the development repository.

- [ ] **Step 4: Run and commit**

Run: `python3 -m unittest tests.test_installer tests.test_readme_teacher_journey tests.test_skill_packages -v`

Commit: `docs: make staged course workflow agent readable`

### Task 14: Prove the complete Chinese teacher journey end to end

**Files:**
- Create: `tests/fixtures/instructional-binding-course/**`
- Create: `tests/test_instructional_authoring_e2e.py`
- Create: `preview_app/src/InstructionalAuthoringFlow.test.tsx`
- Modify: `.github/workflows/validate.yml`

- [ ] **Step 1: Build a small but adversarial Chinese fixture**

Include text, two deliberately distinguishable images, one PDF page reference, teacher-supplied video question data, one HTML activity, optional support, and one proposed exclusion. The expected course must use the correct image/question pairs, co-locate references with answers, avoid empty split slots, preserve the teacher's video question, and retain the fixed course identity.

- [ ] **Step 2: Write the end-to-end test before wiring the final path**

The test performs:

1. inventory and source-coverage migration/validation;
2. page-plan render and explicit approval;
3. Blueprint compile and shared-contract validation;
4. plan/binding/layout/workflow checks;
5. semantic audit record;
6. renderer inspection evidence for all required states;
7. G6 completion;
8. teacher annotation, applied fix, explicit verification, and G7 completion;
9. G8 review;
10. publication prepare in a fake adapter proving stable-slug update and unchanged-asset reuse;
11. execute/readback in the fake adapter only.

Assert that no live API or OSS adapter is constructed.

- [ ] **Step 3: Add browser-level preview assertions**

Using Vitest/jsdom, verify inspection/annotation mode separation, component click targeting, edit/delete/open/verify flows, Publish disabled/readiness states, exact plan display, and second confirmation. Do not make CI depend on image-generation or live student services.

- [ ] **Step 4: Run the full verification matrix**

Run:

```text
python3 -m unittest discover -s tests
pnpm test:preview
pnpm typecheck:preview
pnpm build:runtime
git diff --check
```

Expected: all Python and preview tests pass; TypeScript and runtime build succeed; no whitespace errors.

- [ ] **Step 5: Independently review scope and safety**

Check the implementation against every numbered section of `docs/superpowers/specs/2026-08-20-instructional-binding-and-staged-course-authoring-design.md`. Review every changed file for unfinished implementation markers, empty method bodies, and accidental credentials, then run:

```text
rg -n "oss-admin-|OSS_ADMIN_KEY=" course_toolkit scripts skills preview_app README.md tests
```

Expected: no unfinished implementation and no literal secret values. References to the environment variable name are allowed; values are not.

- [ ] **Step 6: Commit final integration**

Commit: `test: cover staged instructional authoring end to end`

## Completion criteria

Implementation is complete only when all of the following are proven in tests and one fresh local simulation:

1. every selected source item is accounted for and important material cannot be silently omitted;
2. every Slice has a teacher-readable purpose/material/action/layout plan approved before detailed generation;
3. the compiled course deterministically matches that plan and its source bindings;
4. semantic mismatches and unresolved references block preview;
5. the exact student renderer has been visually inspected across required runtime states with zero blockers;
6. the teacher reviews an immutable version and explicitly verifies applied changes;
7. the Publish control prepares an exact update-or-create plan and requires a second confirmation before any external mutation;
8. stable slug and hash records prevent accidental duplicate course creation and repeated unchanged OSS uploads;
9. collaborators are directed to the published student-platform course, never a ZIP or someone else's local preview URL;
10. a partially completed legacy course resumes without losing identity, assets, annotations, or upload-reuse records.
