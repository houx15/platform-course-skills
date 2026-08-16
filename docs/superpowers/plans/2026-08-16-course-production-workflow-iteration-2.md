# Course Production Workflow Iteration 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task by task. This run stays on `dev`, uses no worktree or subagents, commits each completed task, and does not push.

**Goal:** Add an approved CourseBlueprint 1.0 authoring document, a safe schemaVersion 1.1 import path, and a deterministic compiler that emits CourseDefinition 2.0 plus a runtime source map and validates the result with the exact shared student `@mind-imprint/course-contract` package.

**Architecture:** Vendor the source-only student contract at the verified upstream snapshot and expose its Zod validator through a small TypeScript CLI. Keep authoring and migration logic in the existing Python toolkit. A Blueprint contains the complete runtime-shaped course plus authoring-only approval, migration, and provenance records. The compiler strips authoring metadata, creates deterministic hashes/source mappings, invokes the shared Zod/referential/workflow validator, and writes outputs atomically only after the shared contract passes.

**Authoritative upstream snapshot:** `/Users/houyuxin/08Coding/mind-imprint` commit `df36a8ecd1b30f28c27789fcf02e898b5bee6e21`; `packages/course-contract` is clean at planning time. The Zod source wins over local prose or Python assumptions.

**Tech stack:** Python 3.9+ standard library, TypeScript, pnpm, Zod, tsx, `unittest`, shared `@mind-imprint/course-contract` tests.

---

## File structure

### Shared contract and toolchain

- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `tsconfig.base.json`
- Create: `pnpm-lock.yaml`
- Copy: `packages/course-contract/` from the authoritative upstream snapshot, including source, tests, config, and package metadata.
- Create: `course-contract.snapshot.json` — upstream commit and SHA-256 for every vendored contract source file.
- Create: `scripts/check-course-contract-sync.py` — optional exact comparison against a supplied upstream repository.
- Create: `scripts/validate-course-definition.ts` — JSON CLI around `validateCourseDefinition` and `collectAssetPaths`.
- Create: `tests/test_shared_course_contract.py` — Python subprocess tests for the shared validator bridge and snapshot check.

### Blueprint, migration, and compilation

- Create: `schemas/course-blueprint.schema.json`
- Create: `schemas/course-runtime-source-map.schema.json`
- Create: `schemas/course-compilation-report.schema.json`
- Create: `course_toolkit/blueprint.py`
- Create: `course_toolkit/legacy_course_import.py`
- Create: `course_toolkit/course_compiler.py`
- Create: `scripts/import-legacy-course.py`
- Create: `scripts/compile-course.py`
- Create: `tests/test_blueprint.py`
- Create: `tests/test_legacy_course_import.py`
- Create: `tests/test_course_compiler.py`
- Create: `tests/test_course_compiler_cli.py`
- Create: `tests/fixtures/course-blueprint/approved-blueprint.json`
- Create: `tests/fixtures/course-blueprint/legacy-course.json`
- Create: `tests/fixtures/course-blueprint/legacy-storyboard.json`
- Create: `tests/fixtures/course-blueprint/expected-course-definition.json`
- Create: `tests/fixtures/course-blueprint/expected-source-map.json`

### Modified files

- Modify: `course_toolkit/issue_codes.py`
- Modify: `course_toolkit/workflow.py`
- Modify: `scripts/course-workflow.py`
- Modify: `skills/build-platform-course/SKILL.md`
- Modify: `skills/build-platform-course/references/workflow.md`
- Modify: `tests/test_issue_store.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/test_workflow_cli.py`
- Modify: `tests/test_skill_packages.py`
- Modify: `docs/validation-report.md`

## Task 1: Vendor and prove the shared student course contract

**Files:** shared contract/toolchain files listed above.

- [x] **Step 1: Write failing shared-contract bridge tests**

Cover:

```python
def test_shared_validator_accepts_upstream_golden_course(self):
    result = run_contract_validator(GOLDEN)
    self.assertEqual(result.returncode, 0, result.stderr)
    payload = json.loads(result.stdout)
    self.assertTrue(payload["ok"])
    self.assertIn("assets/videos/case.mp4", payload["assetPaths"])

def test_shared_validator_returns_ordered_contract_issues(self):
    broken = copy.deepcopy(golden_course())
    broken["course"]["parts"][0]["slices"][0]["layout"]["slots"] = []
    result = run_contract_validator_file(broken)
    self.assertEqual(result.returncode, 2)
    self.assertEqual(payload["issues"][0]["layer"], "structural")

def test_snapshot_manifest_matches_vendored_contract(self):
    self.assertEqual(check_snapshot(ROOT), [])
```

- [x] **Step 2: Run the tests and verify they fail because no Node workspace or bridge exists**

Run: `python -m unittest tests.test_shared_course_contract -v`

- [x] **Step 3: Copy the exact upstream package and add workspace tooling**

Create a private root package with:

```json
{
  "name": "course-production-toolkit",
  "private": true,
  "packageManager": "pnpm@10.29.3",
  "dependencies": {
    "@mind-imprint/course-contract": "workspace:*"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "tsx": "^4.20.0",
    "typescript": "^5.9.0"
  }
}
```

The copied course-contract retains Zod as its only runtime dependency. Do not edit its schemas to accommodate generator output.

- [x] **Step 4: Add and verify the snapshot manifest**

Record upstream repository commit, package version, and each `src/**/*.ts` SHA-256. `check-course-contract-sync.py` must check the vendored copy always and compare contract source bytes to `--upstream PATH` when supplied. Report a newer repository HEAD as context, not drift, when every contract source hash still matches; unrelated student-platform commits must not invalidate the snapshot. It must never modify either tree.

- [x] **Step 5: Implement the TypeScript validator bridge**

Commands:

```text
node --import tsx scripts/validate-course-definition.ts INPUT --json
pnpm --filter @mind-imprint/course-contract test
pnpm --filter @mind-imprint/course-contract typecheck
```

Output on success:

```json
{"ok":true,"assetPaths":["..."],"courseId":"..."}
```

Output on contract failure contains `ok:false` and the shared ordered `{path,message,layer}` issues. Exit codes: `0` valid, `2` contract-invalid, `3` I/O/tool failure. Never print a stack trace in ordinary output.

- [x] **Step 6: Install from the lockfile and run bridge, upstream package test, and typecheck**

Expected: all pass.

- [x] **Step 7: Commit**

```bash
git add package.json pnpm-workspace.yaml pnpm-lock.yaml tsconfig.base.json packages/course-contract course-contract.snapshot.json scripts/check-course-contract-sync.py scripts/validate-course-definition.ts tests/test_shared_course_contract.py
git commit -m "build: vendor shared course contract"
```

## Task 2: Define the CourseBlueprint authoring contract

**Files:** Blueprint module/schema/tests/fixture.

- [x] **Step 1: Write failing Blueprint tests**

Require this top-level shape:

```json
{
  "schemaVersion": "1.0",
  "targetContractVersion": "2.0",
  "approval": {
    "teacherConfirmed": true,
    "decisionIds": ["decision-course-design"]
  },
  "course": {},
  "provenance": [
    {
      "targetId": "block:evidence-question",
      "sourceIds": ["source-1"],
      "decisionIds": [],
      "status": "source-backed"
    }
  ],
  "migration": null
}
```

Tests must reject unknown top-level/authoring fields, duplicate provenance targets, malformed target IDs, unconfirmed compilation, target contract other than 2.0, and provenance pointing at nonexistent runtime entities. The `course` member is validated by the shared Zod contract after projection rather than by a copied Python schema.

- [x] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests.test_blueprint -v`

- [x] **Step 3: Implement Blueprint parsing and target indexing**

Provide:

```python
load_blueprint(path) -> CourseBlueprint
validate_blueprint_authoring(data) -> List[BlueprintIssue]
project_course_definition(data) -> {"schemaVersion":"2.0","course":...}
index_blueprint_targets(data) -> Dict[target_id, json_pointer]
```

Target IDs:

```text
course
opening
closing
objective:<id>
part:<id>
slice:<id>
block:<id>
slice:<slice-id>/narration:<id>
slice:<slice-id>/workflow-step:<id>
```

Require globally unique block IDs and slice IDs at the authoring layer so mappings are stable. Approval failure is a `decision-required` compiler issue, not an auto-fix.

- [x] **Step 4: Add the closed authoring JSON Schema**

Close Blueprint, approval, provenance, and migration objects. Deliberately leave `course` structurally delegated to the shared Zod validator and document this in `$comment`; do not hand-maintain a second CourseDefinition schema.

- [x] **Step 5: Add the approved Blueprint fixture**

Exercise text, assessment, layout, narration, workflow, navigation, opening, closing, objective evidence, and provenance without requiring real asset bytes.

- [x] **Step 6: Run tests and schema syntax check**

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add course_toolkit/blueprint.py schemas/course-blueprint.schema.json tests/test_blueprint.py tests/fixtures/course-blueprint/approved-blueprint.json
git commit -m "feat: define course blueprint contract"
```

## Task 3: Import schemaVersion 1.1 without silent semantic approval

**Files:** legacy importer, CLI, fixtures, tests, issue policies.

- [x] **Step 1: Write failing legacy-import tests**

Cover:

- Piece → Slice one-to-one with stable existing IDs.
- Existing blocks convert to the seven 2.0 shapes; legacy `blocking` is removed.
- Image item IDs are generated deterministically from block ID and position.
- HTML gains `protocolVersion: "1.0"` and explicit `aspectRatio`.
- Video interaction uses the legacy data JSON as `interaction.source`; authoring Markdown is not a runtime asset.
- Completion rules become valid strict 2.0 rules; `submit-correct` does not retain an illegal `maxAttempts`.
- `courseFrame.objectiveAlignment` supplies part and evidence references; missing alignment blocks import rather than inventing evidence.
- Layout, navigation, workflow, personalization-disabled defaults, and estimated time assumptions are recorded in `migration.assumptions`.
- Imported Blueprint is `teacherConfirmed: false` even if the legacy storyboard was confirmed, because new 2.0 layout/workflow/time assumptions need a new decision.
- Identical inputs produce byte-identical Blueprint JSON.

- [x] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.test_legacy_course_import -v`

- [x] **Step 3: Implement deterministic block and course conversion**

Default migration policies are explicit and non-semantic:

- one Piece becomes one Slice;
- one `full/main` layout assigns all Piece blocks once;
- no narration is fabricated;
- personalization is disabled with empty signal lists;
- blocking activities form a deterministic `block.completed`/interaction workflow; otherwise `student.continue` completes the Slice;
- navigation allows previous, allows manual next only after completion, disables auto-next, and restores completed state;
- estimated seconds use a versioned documented heuristic and remain an assumption requiring teacher confirmation.

Do not generate a missing evidence block, answer, rubric, source file, narration audio, or media duration.

- [x] **Step 4: Implement import CLI**

```text
python scripts/import-legacy-course.py LEGACY_COURSE STORYBOARD OUTPUT --json
```

Refuse overwrite unless `--replace-unconfirmed` is supplied and the existing output is itself unconfirmed. Never overwrite a confirmed Blueprint.

- [x] **Step 5: Register compiler/migration issue policies**

Add fixed codes for invalid Blueprint, migration confirmation required, missing objective alignment, and shared-contract failure. Unknown codes remain forbidden.

- [x] **Step 6: Run tests**

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add course_toolkit/legacy_course_import.py scripts/import-legacy-course.py course_toolkit/issue_codes.py tests/test_issue_store.py tests/test_legacy_course_import.py tests/fixtures/course-blueprint/legacy-course.json tests/fixtures/course-blueprint/legacy-storyboard.json
git commit -m "feat: import legacy courses into blueprints"
```

## Task 4: Compile deterministically and emit a runtime source map

**Files:** compiler, schemas, tests, expected fixtures.

- [x] **Step 1: Write failing compiler tests**

Cover:

```python
def test_compile_is_byte_reproducible(self):
    first = compile_blueprint(APPROVED)
    second = compile_blueprint(copy.deepcopy(APPROVED))
    self.assertEqual(dump_json(first.document), dump_json(second.document))
    self.assertEqual(dump_json(first.source_map), dump_json(second.source_map))

def test_runtime_output_contains_no_authoring_metadata(self):
    result = compile_blueprint(APPROVED)
    rendered = dump_json(result.document)
    self.assertNotIn("provenance", rendered)
    self.assertNotIn("decisionIds", rendered)

def test_source_map_resolves_every_stable_target(self):
    result = compile_blueprint(APPROVED)
    self.assertEqual(
        {entry["targetId"] for entry in result.source_map["mappings"]},
        set(index_blueprint_targets(APPROVED)),
    )
```

Also test canonical SHA-256 values, deterministic mapping order, correct JSON pointers, source/decision propagation, missing approval refusal, and failure when the real shared contract rejects the projected runtime document.

- [x] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.test_course_compiler -v`

- [x] **Step 3: Implement canonical hashes and compiler result**

Provide:

```python
compile_blueprint(data, contract_validator) -> CompilationResult
canonical_json_hash(data) -> sha256
build_runtime_source_map(data, document) -> dict
```

The source map contains no timestamp:

```json
{
  "schemaVersion": "1.0",
  "compilerVersion": "1.0",
  "blueprintHash": "...",
  "courseDefinitionHash": "...",
  "mappings": [
    {
      "targetId": "block:evidence-question",
      "blueprintPointer": "/course/parts/0/slices/0/blocks/1",
      "runtimePointer": "/course/parts/0/slices/0/blocks/1",
      "sourceIds": ["source-1"],
      "decisionIds": []
    }
  ]
}
```

- [x] **Step 4: Invoke only the shared contract as the runtime gate**

The compiler adapter runs `node --import tsx scripts/validate-course-definition.ts`. This avoids the `tsx` CLI's optional IPC server while executing the same TypeScript source. Preserve shared issue order/layer/path/message. A failed validator produces no new course definition or source map.

- [x] **Step 5: Add source-map and compilation-report schemas**

Compilation report fields: schema version, status, compiler version, Blueprint/definition/source-map hashes, sorted asset paths from `collectAssetPaths`, shared-contract snapshot commit, and ordered issues. No current time or random ID.

- [x] **Step 6: Freeze expected output fixtures and run reproducibility tests**

Expected: approved fixture compiles byte-for-byte to the frozen CourseDefinition 2.0 and source map twice.

- [x] **Step 7: Commit**

```bash
git add course_toolkit/course_compiler.py schemas/course-runtime-source-map.schema.json schemas/course-compilation-report.schema.json tests/test_course_compiler.py tests/fixtures/course-blueprint/expected-course-definition.json tests/fixtures/course-blueprint/expected-source-map.json
git commit -m "feat: compile course blueprints to definition 2"
```

## Task 5: Add an atomic compile CLI and G5 Workflow evidence

**Files:** compile CLI, Workflow/CLI modules/tests.

- [ ] **Step 1: Write failing CLI and Workflow tests**

Cover:

- successful compile writes `course/course.json`, `.course-work/course-runtime-source-map.json`, and `.course-work/compilation-report.json` atomically;
- outputs are unchanged on a failed recompile;
- report asset paths come from the shared contract;
- `compile-course.py` exits 0/2/3 for success/contract-or-approval block/tool failure;
- G5 cannot complete without a current successful compilation report whose Blueprint/definition/source-map hashes match disk;
- changing the Blueprint invalidates G3+; changing compiler or contract snapshot invalidates G5+;
- successful G5 completion stores current compiler/contract evidence in session artifact hashes.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.test_course_compiler_cli tests.test_workflow tests.test_workflow_cli -v`

- [ ] **Step 3: Implement the compile CLI**

```text
python scripts/compile-course.py ROOT --json
```

Read only `.course-work/course-blueprint.json`. Validate in memory first. Write all three outputs only after the shared validator passes. Use staged temporary files and recover the previous complete set if any final replacement fails.

- [ ] **Step 4: Add deterministic G5 evidence checks**

Extend Workflow gate completion with a gate-evidence callback/registry. G5 evidence must verify hashes and successful shared-contract snapshot. Keep G0–G4 behavior unchanged; do not pretend G6/G7/G9 evidence exists yet.

- [ ] **Step 5: Run focused tests**

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/compile-course.py tests/test_course_compiler_cli.py course_toolkit/workflow.py scripts/course-workflow.py tests/test_workflow.py tests/test_workflow_cli.py
git commit -m "feat: gate compiled course definition evidence"
```

## Task 6: Route the director Skill to Blueprint and verify one real migration

**Files:** Skill/reference/tests/report.

- [ ] **Step 1: Write failing Skill contract tests**

Require:

- `.course-work/course-blueprint.json` is authoring truth;
- legacy 1.1 import never implies approval of new layout/workflow/time assumptions;
- CourseDefinition 2.0 is generated only by `compile-course.py`;
- `course/course.json` is never hand edited after migration;
- shared student Zod validator is the one runtime gate;
- G5 requires current compilation hashes;
- the student renderer, browser preview, OSS, and real POST remain unavailable boundaries.

- [ ] **Step 2: Run Skill tests and verify failure**

Run: `python -m unittest tests.test_skill_packages -v`

- [ ] **Step 3: Update director and workflow instructions**

Replace the temporary legacy G5 boundary. Preserve the ability to validate old 1.1 packages, but route new authoring through Blueprint. Teachers see the migration assumptions in readable form and must confirm them before compile.

- [ ] **Step 4: Migrate the repository's valid real fixture**

Use the existing real end-to-end pair `e2e/for-test-course/course/course.json` and `e2e/for-test-course/.course-work/course-storyboard.json` to produce a reviewable Blueprint in a temporary directory. Explicitly confirm the migration assumptions through a test decision record, compile twice, and validate with the shared contract. Record Part/Slice/Block counts and hashes without committing the ignored teacher-derived course package.

- [ ] **Step 5: Run all Python and shared-contract tests**

Run:

```bash
python -m unittest discover -s tests -q
pnpm --filter @mind-imprint/course-contract test
pnpm --filter @mind-imprint/course-contract typecheck
```

- [ ] **Step 6: Update validation report with exact boundaries**

State that CourseDefinition 2.0 generation/validation exists, while renderer preview, annotation UI, enhanced media completeness gates, OSS, and real API publication do not.

- [ ] **Step 7: Commit**

```bash
git add skills/build-platform-course/SKILL.md skills/build-platform-course/references/workflow.md tests/test_skill_packages.py docs/validation-report.md docs/superpowers/plans/2026-08-16-course-production-workflow-iteration-2.md
git commit -m "docs: route authoring through course blueprints"
```
