# Course Production Workflow Iteration 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Subagents are intentionally excluded for this repository run. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the persistent course-production Workflow kernel, unified issue/decision stores, deterministic CLI, and the single teacher-facing `build-platform-course` orchestration contract without depending on the student renderer or publication APIs.

**Architecture:** Add small standard-library Python modules under `course_toolkit/` for workflow state, gate enforcement, artifact hashing/invalidation, issues, and teacher decisions. Expose these through one CLI used by the director Skill. Preserve the existing course authoring implementation while changing the Skill's process contract to the approved G0–G10 workflow; CourseDefinition 2.0 compilation begins in Iteration 2.

**Tech Stack:** Python 3.9+ standard library, JSON, `unittest`, existing Skill Markdown scenario tests.

---

## File structure

### New files

- `course_toolkit/issue_codes.py` — versioned issue-code registry and policy lookup.
- `course_toolkit/issues.py` — issue dataclass, fingerprinting, store load/save/upsert/resolve operations.
- `course_toolkit/decisions.py` — teacher-decision requests, confirmed decisions, and invalidation.
- `course_toolkit/workflow.py` — phases, gates, session persistence, legal transitions, artifact hashing, targeted invalidation, and resume reconciliation.
- `scripts/course-workflow.py` — JSON/human CLI over the Workflow kernel.
- `schemas/course-production-session.schema.json` — documented persisted session shape.
- `schemas/course-production-issues.schema.json` — documented issue-store shape.
- `schemas/course-production-decisions.schema.json` — documented decision-store shape.
- `tests/test_issue_store.py` — issue policy, deduplication, resolution, and persistence tests.
- `tests/test_decisions.py` — confirmation and invalidation tests.
- `tests/test_workflow.py` — gate order, state transition, hashing, invalidation, and resume tests.
- `tests/test_workflow_cli.py` — CLI integration tests.

### Modified files

- `course_toolkit/jsonio.py` — add atomic JSON writes used by all new stores.
- `skills/build-platform-course/SKILL.md` — make Workflow restore/reconcile the mandatory first action and hide internal phases from teachers.
- `skills/build-platform-course/references/workflow.md` — replace the legacy eight-state prose with the approved phase/gate model and CLI usage.
- `tests/test_skill_packages.py` — assert the new director/workflow invariants.
- `docs/superpowers/specs/2026-08-16-course-production-workflow-and-skill-architecture-design.md` — add the omitted canonical `issues.json` work file.

## Task 1: Atomic JSON persistence

**Files:**

- Modify: `course_toolkit/jsonio.py`
- Test: `tests/test_workflow.py`

- [x] **Step 1: Write the failing atomic-write tests**

Add tests proving `write_json_atomic(path, data)` creates parent directories, writes UTF-8 formatted JSON, and leaves no temporary file after success:

```python
def test_write_json_atomic_creates_parent_and_round_trips(self):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ".course-work" / "session.json"
        write_json_atomic(path, {"phase": "intake", "title": "课程"})
        self.assertEqual(load_json(path)["title"], "课程")
        self.assertEqual(list(path.parent.glob("*.tmp")), [])
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_workflow.AtomicJsonTests -v`

Expected: import failure because `write_json_atomic` does not exist.

- [x] **Step 3: Implement the atomic writer**

Add this public API:

```python
def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(dump_json(data), encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
```

- [x] **Step 4: Run the focused test**

Run: `python -m unittest tests.test_workflow.AtomicJsonTests -v`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add course_toolkit/jsonio.py tests/test_workflow.py
git commit -m "feat: add atomic workflow persistence"
```

## Task 2: Versioned issue registry and persistent issue store

**Files:**

- Create: `course_toolkit/issue_codes.py`
- Create: `course_toolkit/issues.py`
- Create: `schemas/course-production-issues.schema.json`
- Create: `tests/test_issue_store.py`

- [ ] **Step 1: Write failing registry and issue-store tests**

Cover:

```python
def test_registered_warning_carries_publish_ack_policy(self):
    policy = get_issue_policy("workflow-artifact-changed")
    self.assertEqual(policy.severity, "warning")
    self.assertEqual(
        policy.warning_policy,
        "no-acknowledgement-required",
    )

def test_upsert_deduplicates_by_fingerprint_and_updates_last_seen(self):
    first = store.upsert(make_issue(message="old", seen_at="2026-08-16T00:00:00Z"))
    second = store.upsert(make_issue(message="new", seen_at="2026-08-16T01:00:00Z"))
    self.assertEqual(first.id, second.id)
    self.assertEqual(len(store.all()), 1)
    self.assertEqual(store.all()[0].message, "new")

def test_blocker_cannot_be_accepted(self):
    blocker = store.upsert(make_issue(code="workflow-gate-prerequisite"))
    with self.assertRaisesRegex(ValueError, "cannot be accepted"):
        store.accept(blocker.id, rationale="ignore")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_issue_store -v`

Expected: module import failures.

- [ ] **Step 3: Implement the issue-code registry**

Define:

```python
@dataclass(frozen=True)
class IssuePolicy:
    code: str
    severity: str
    default_gate_id: str
    warning_policy: Optional[str] = None

ISSUE_POLICIES = {
    "workflow-gate-prerequisite": IssuePolicy(
        "workflow-gate-prerequisite", "blocker", "G0"
    ),
    "workflow-active-blocker": IssuePolicy(
        "workflow-active-blocker", "blocker", "G0"
    ),
    "workflow-pending-decision": IssuePolicy(
        "workflow-pending-decision", "decision-required", "G0"
    ),
    "workflow-artifact-changed": IssuePolicy(
        "workflow-artifact-changed",
        "warning",
        "G0",
        "no-acknowledgement-required",
    ),
    "workflow-missing-source": IssuePolicy(
        "workflow-missing-source", "blocker", "G1"
    ),
}
```

Unknown issue codes must raise `ValueError`; Skills cannot invent policy in prose.

- [ ] **Step 4: Implement issue persistence**

Provide:

```python
@dataclass(frozen=True)
class CourseProductionIssue:
    id: str
    fingerprint: str
    code: str
    severity: str
    status: str
    gate_id: str
    source: str
    message: str
    first_seen_at: str
    last_seen_at: str
    target: Optional[dict] = None
    evidence: Tuple[str, ...] = ()
    remediation: Optional[str] = None
    warning_policy: Optional[str] = None
    teacher_decision_id: Optional[str] = None
```

`IssueStore` must load/save `{ "schemaVersion": "1.0", "issues": [...] }`, upsert by deterministic fingerprint, resolve, dismiss, and accept only warnings whose policy permits acknowledgement.

- [ ] **Step 5: Add the JSON Schema**

The schema must close all objects with `additionalProperties: false`, enumerate severity/status/source/warning policy, and require all identity/timestamp fields.

- [ ] **Step 6: Run focused tests**

Run: `python -m unittest tests.test_issue_store -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add course_toolkit/issue_codes.py course_toolkit/issues.py schemas/course-production-issues.schema.json tests/test_issue_store.py
git commit -m "feat: add course production issue store"
```

## Task 3: Teacher decision store

**Files:**

- Create: `course_toolkit/decisions.py`
- Create: `schemas/course-production-decisions.schema.json`
- Create: `tests/test_decisions.py`

- [ ] **Step 1: Write failing decision lifecycle tests**

Cover request creation, answer recording, no silent re-answer, and invalidation when the context hash changes:

```python
def test_confirmed_decision_is_invalidated_by_new_context_hash(self):
    store.request("d-objective", "Which objective?", "hash-a")
    store.confirm("d-objective", "Compare evidence", "2026-08-16T00:00:00Z")
    invalidated = store.reconcile_context("d-objective", "hash-b", "2026-08-16T01:00:00Z")
    self.assertTrue(invalidated)
    self.assertEqual(store.get("d-objective").status, "invalidated")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_decisions -v`

Expected: module import failure.

- [ ] **Step 3: Implement the decision store**

Persist `{ "schemaVersion": "1.0", "decisions": [...] }`. Each decision contains stable ID, question, context, context hash, options, answer, status (`pending`, `confirmed`, `invalidated`), affected artifact IDs, decided time, and invalidated time.

The store must reject confirmation of an unknown request and reject overwriting a confirmed decision without explicit invalidation.

- [ ] **Step 4: Add the closed JSON Schema**

Encode the exact persisted shape and status enum.

- [ ] **Step 5: Run tests**

Run: `python -m unittest tests.test_decisions -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add course_toolkit/decisions.py schemas/course-production-decisions.schema.json tests/test_decisions.py
git commit -m "feat: track teacher decisions"
```

## Task 4: Workflow phases, gates, and legal transitions

**Files:**

- Create: `course_toolkit/workflow.py`
- Create: `schemas/course-production-session.schema.json`
- Modify: `tests/test_workflow.py`

- [ ] **Step 1: Write failing gate-order and resume tests**

Cover:

```python
def test_cannot_complete_gate_before_prerequisite(self):
    session = new_session("course-a", ["materials/source.md"], NOW)
    with self.assertRaisesRegex(WorkflowError, "G1 requires G0"):
        complete_gate(session, "G1", NOW)

def test_completing_gate_advances_to_next_phase(self):
    session = new_session("course-a", [], NOW)
    complete_gate(session, "G0", NOW)
    self.assertEqual(session.phase, "material-review")

def test_complete_gate_refuses_active_blocker_or_pending_decision(self):
    session = new_session("course-a", [], NOW)
    blocker = make_registered_issue(
        code="workflow-active-blocker",
        source="workflow",
        message="unsafe path",
        gate_id="G0",
        seen_at=NOW,
    )
    with self.assertRaisesRegex(WorkflowError, "active blocker"):
        complete_gate(session, "G0", NOW, active_issues=[blocker])
    with self.assertRaisesRegex(WorkflowError, "pending teacher decision"):
        complete_gate(session, "G0", NOW, pending_decision_ids=["decision-1"])
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `python -m unittest tests.test_workflow.WorkflowGateTests -v`

Expected: missing `course_toolkit.workflow`.

- [ ] **Step 3: Implement phases and gates**

Define exact constants:

```python
PHASES = (
    "intake", "material-review", "course-brief", "course-design",
    "media-design", "compile", "validate", "preview", "revise",
    "final-review", "publish", "complete",
)

GATES = (
    Gate("G0", "intake", None, "material-review"),
    Gate("G1", "material-review", "G0", "course-brief"),
    Gate("G2", "course-brief", "G1", "course-design"),
    Gate("G3", "course-design", "G2", "media-design"),
    Gate("G4", "media-design", "G3", "compile"),
    Gate("G5", "compile", "G4", "validate"),
    Gate("G6", "validate", "G5", "preview"),
    Gate("G7", "preview", "G6", "final-review"),
    Gate("G8", "final-review", "G7", "publish"),
    Gate("G9", "publish", "G8", "complete"),
    Gate("G10", "complete", "G9", "complete"),
)
```

Provide `new_session`, `load_session`, `save_session`, `complete_gate`, `invalidate_from_gate`, `set_phase_status`, and `workflow_summary`.

Gate completion must require its prerequisite, reject unresolved blockers at or before the gate, and reject pending decisions at or before the gate.

- [ ] **Step 4: Add the closed session JSON Schema**

Match the persisted API, including workflow version, stable local course ID, source paths, phase/status, completed/invalidated gates, active issue IDs, pending decision/annotation IDs, artifact hashes, last successful action, and optional failure record.

- [ ] **Step 5: Run gate tests**

Run: `python -m unittest tests.test_workflow.WorkflowGateTests -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add course_toolkit/workflow.py schemas/course-production-session.schema.json tests/test_workflow.py
git commit -m "feat: add course production workflow gates"
```

## Task 5: Artifact hashing and targeted invalidation

**Files:**

- Modify: `course_toolkit/workflow.py`
- Modify: `tests/test_workflow.py`

- [ ] **Step 1: Write failing hashing and invalidation tests**

Test deterministic file/directory tree hashing, safe relative source paths, and the invalidation matrix:

```python
def test_blueprint_change_invalidates_g3_and_downstream_only(self):
    session = fully_gated_through("G8")
    session.artifact_hashes[".course-work/course-blueprint.json"] = "old"
    reconcile_artifacts(self.root, session, NOW)
    self.assertEqual(session.completed_gate_ids, ["G0", "G1", "G2"])
    self.assertIn("G3", session.invalidated_gate_ids)
    self.assertEqual(session.phase, "course-design")

def test_renderer_version_change_invalidates_preview_not_compilation(self):
    manifest = self.root / ".course-work" / "preview-manifest.json"
    write_json_atomic(manifest, {"rendererVersion": "1"})
    session = fully_gated_through("G8")
    session.artifact_hashes[".course-work/preview-manifest.json"] = hash_path(manifest)
    write_json_atomic(manifest, {"rendererVersion": "2"})
    reconcile_artifacts(self.root, session, NOW)
    self.assertEqual(
        session.completed_gate_ids,
        ["G0", "G1", "G2", "G3", "G4", "G5", "G6"],
    )
    self.assertEqual(session.phase, "preview")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_workflow.ArtifactReconciliationTests -v`

Expected: missing reconciliation APIs.

- [ ] **Step 3: Implement deterministic hashing**

Provide SHA-256 for a file and a directory tree. Directory hashing must sort POSIX relative paths, include the path and file hash, ignore ZIPs, and reject symlink/path escape.

- [ ] **Step 4: Implement the invalidation matrix**

Use exact earliest gates:

```python
ARTIFACT_GATE_RULES = (
    ArtifactRule("materials/", "G1"),
    ArtifactRule(".course-work/course-brief.json", "G2"),
    ArtifactRule(".course-work/course-blueprint.json", "G3"),
    ArtifactRule(".course-work/media/", "G4"),
    ArtifactRule("course/course.json", "G5"),
    ArtifactRule("course/assets/", "G6"),
    ArtifactRule(".course-work/preview-manifest.json", "G7"),
    ArtifactRule(".course-work/annotations.json", "G7"),
    ArtifactRule(".course-work/review-report.json", "G8"),
    ArtifactRule(".course-work/asset-manifest.json", "G9"),
    ArtifactRule(".course-work/publish-state.json", "G9"),
)
```

Explicit `sourcePaths` registered outside `materials/` use G1. Missing sources create `workflow-missing-source` blockers. A changed artifact creates or refreshes `workflow-artifact-changed` and invalidates its gate plus all downstream gates.

- [ ] **Step 5: Run artifact tests**

Run: `python -m unittest tests.test_workflow.ArtifactReconciliationTests -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add course_toolkit/workflow.py tests/test_workflow.py
git commit -m "feat: invalidate stale course work"
```

## Task 6: Workflow CLI

**Files:**

- Create: `scripts/course-workflow.py`
- Create: `tests/test_workflow_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Use subprocess to cover:

```text
course-workflow.py init ROOT --course-local-id demo --source materials/a.md --json
course-workflow.py status ROOT --json
course-workflow.py reconcile ROOT --json
course-workflow.py complete-gate ROOT G0 --json
course-workflow.py set-status ROOT waiting-for-teacher --json
```

Assert stable exit codes: `0` success, `2` workflow/gate blocked, `3` tool/storage failure.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_workflow_cli -v`

Expected: script missing.

- [ ] **Step 3: Implement the CLI**

The CLI must:

- resolve root without allowing escape;
- store all work under `.course-work/`;
- emit a stable JSON object with `ok`, `phase`, `status`, `completedGates`, `invalidatedGates`, `issues`, `pendingDecisions`, and `nextAction`;
- write human-readable summaries without exposing internal stack traces;
- never offer a command that skips prerequisites or force-accepts a blocker.

- [ ] **Step 4: Run CLI tests**

Run: `python -m unittest tests.test_workflow_cli -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/course-workflow.py tests/test_workflow_cli.py
git commit -m "feat: add course workflow CLI"
```

## Task 7: Director Skill workflow contract

**Files:**

- Modify: `skills/build-platform-course/SKILL.md`
- Replace: `skills/build-platform-course/references/workflow.md`
- Modify: `tests/test_skill_packages.py`
- Modify: `docs/superpowers/specs/2026-08-16-course-production-workflow-and-skill-architecture-design.md`

- [ ] **Step 1: Write failing Skill contract tests**

Require the visible Skill/reference to state:

- `build-platform-course` is the only teacher entry;
- restore and reconcile happen before any generation;
- G0–G10 cannot be skipped;
- internal Skills and JSON remain hidden;
- semantic changes require teacher confirmation;
- CourseDefinition 2.0 compilation is a later gate, not a direct hand edit;
- annotations invalidate final review;
- publication requires dry run and explicit approval;
- no push, upload, or external mutation is inferred from local completion.

- [ ] **Step 2: Run the test to verify failure**

Run: `python -m unittest tests.test_skill_packages -v`

Expected: new required phrases missing.

- [ ] **Step 3: Rewrite the workflow reference**

Document the 12 phases, G0–G10 inputs/exit conditions, resume/reconciliation commands, targeted invalidation, issue severities, and revision loop. Preserve the existing teacher-confirmation and original-material safety rules.

- [ ] **Step 4: Update the director Skill**

Make this the mandatory start:

```text
1. Locate the course root and run `scripts/course-workflow.py status ROOT --json`.
2. If no session exists, initialize it with explicit source paths. Otherwise reconcile before any analysis or generation.
3. Follow the earliest incomplete or invalidated gate. Never infer gate completion from file existence.
4. Present only the current teacher decisions, readable issues, and next action; keep internal Skill and JSON details hidden.
```

Keep legacy schema 1.1 generation explicitly marked as the current implementation boundary until Iteration 2 replaces it; do not falsely claim the new compiler exists.

- [ ] **Step 5: Run Skill tests**

Run: `python -m unittest tests.test_skill_packages -v`

Expected: PASS.

- [ ] **Step 6: Run all Iteration 1 tests**

Run:

```bash
python -m unittest \
  tests.test_issue_store \
  tests.test_decisions \
  tests.test_workflow \
  tests.test_workflow_cli \
  tests.test_skill_packages -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add skills/build-platform-course/SKILL.md skills/build-platform-course/references/workflow.md tests/test_skill_packages.py docs/superpowers/specs/2026-08-16-course-production-workflow-and-skill-architecture-design.md
git commit -m "docs: route course building through workflow gates"
```

## Task 8: Iteration 1 full verification and handoff record

**Files:**

- Modify: `docs/validation-report.md`

- [ ] **Step 1: Run the entire existing repository test suite**

Run: `python -m unittest discover -s tests -q`

Expected: all tests pass with no failures or errors.

- [ ] **Step 2: Run the existing valid fixture validator**

Run: `python scripts/validate-course.py tests/fixtures/valid-course --json`

Expected: current legacy fixture remains `uploadable`; Iteration 1 must not regress existing course validation.

- [ ] **Step 3: Exercise workflow resume manually through the CLI**

Use a temporary course root, initialize with one source, complete G0, alter the source, reconcile, and confirm the output returns to the earliest affected phase with an artifact/source issue.

- [ ] **Step 4: Update the validation report**

Record the commands, counts, branch, commit range, implemented Iteration 1 boundaries, and the explicit remaining Iteration 2–5 work. Do not claim CourseDefinition 2.0, preview, OSS, or API integration exists.

- [ ] **Step 5: Commit**

```bash
git add docs/validation-report.md
git commit -m "docs: verify workflow iteration one"
```
