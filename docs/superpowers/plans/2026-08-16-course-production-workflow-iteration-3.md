# Course Production Workflow Iteration 3 Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` task by task. Work on `dev`, use no worktree or subagents, commit each completed task, and do not push.

**Goal:** Validate compiled CourseDefinition 2.0 packages completely enough for G6 without depending on the student renderer: exact shared contract, local asset existence and safety, PDF integrity, MP4 profile and cue timing, interactive HTML handshake/completion evidence, accessible companion assets, deterministic warnings, and current validation evidence.

**Architecture:** Keep the vendored shared TypeScript contract authoritative for CourseDefinition and VideoInteractionDocument shapes. Build a Python package validator around its deterministic output and the existing byte-level PDF/MP4/HTML inspectors. Validation reads only a current G5 compilation set and local assets, writes one deterministic report, synchronizes registered G6 issues, and supplies hashes to the Workflow. It does not render a browser preview, upload assets, or call a course API.

**Important boundary:** the current student HTML renderer accepts an envelope `{protocol, version, sessionToken, type, payload}` but still treats payload as unknown. Authoring validation therefore checks the exact renderer handshake plus a stricter local completion-evidence convention (`interactionId` and `evidence`) without claiming the student runtime already persists that evidence. Renderer-backed payload acceptance remains a G7 dependency.

---

## Task 1: Expose the exact shared VideoInteraction validator

**Files:** `scripts/validate-video-interaction.ts`, `tests/test_shared_video_interaction_contract.py`, root package wiring if needed.

- [x] Write failing bridge tests for valid input, structural failure, owning-block mismatch, duplicate/out-of-order/out-of-duration cues, and tool failure.
- [x] Implement `node --import tsx scripts/validate-video-interaction.ts DOCUMENT OWNER --json` using `VideoInteractionDocument.safeParse` and `validateVideoInteraction`.
- [x] Preserve shared issue order, path, message, and layer. Exit `0` valid, `2` contract-invalid, `3` tool failure.
- [x] Run focused tests and shared package tests.
- [x] Commit: `feat: expose shared video interaction validation`.

## Task 2: Add CourseDefinition 2.0 asset indexing and safe path checks

**Files:** `course_toolkit/course_package_validation.py`, `tests/test_course_package_validation.py`, new fixtures under `tests/fixtures/course-definition-2/`.

- [x] Write failing tests covering every asset-bearing field: opening/closing fallback audio, narration audio, image, PDF, video, poster, captions, video interaction JSON, and interactive HTML.
- [x] Define stable `AssetReference` records with runtime JSON path, asset role, block/slice identity, and raw source.
- [x] Follow the shared contract's safe-relative-path rule: URL schemes, `data:`, absolute paths, backslashes, and parent traversal are contract-invalid; validate local references against the compilation report's exact sorted asset list.
- [x] Reject absolute paths, `..`, symlink traversal, missing files, directories, and case-mismatched paths.
- [x] Add deterministic basic file-role extension checks; content-level `WEBVTT`, HTML, PDF, and video checks continue in Task 4.
- [x] Commit: `feat: validate definition 2 asset references`.

## Task 3: Validate the renderer-compatible HTML authoring protocol

**Files:** `course_toolkit/html_validation.py`, `skills/design-course-html/SKILL.md`, `skills/design-course-html/references/html-contract.md`, HTML fixtures/tests.

- [x] Replace the legacy `INTERACTION_COMPLETE` assumption for 2.0 with the actual `mind-course-interaction` 1.0 handshake: receive host protocol/version/sessionToken, echo all envelope fields, and use one of `ready|progress|completed|error`.
- [x] Require a completed payload with a stable `interactionId` and JSON-compatible `evidence`; prohibit completion without learning data.
- [x] Preserve existing self-containment, no-external-resource, aspect ratio, horizontal overflow, and 16px/14px typography checks.
- [x] Detect prohibited host access/storage/network APIs that conflict with the sandboxed self-contained iframe model.
- [x] Keep legacy HTML validation available only for legacy review; expose an explicit 2.0 validator mode.
- [x] Commit: `feat: validate course html protocol 1`.

## Task 4: Build deterministic CourseDefinition 2.0 validation reports

**Files:** `course_toolkit/course_package_validation.py`, `scripts/validate-course-v2.py`, `schemas/course-validation-report.schema.json`, tests/fixtures.

- [x] Validate the current G5 evidence before inspecting assets.
- [x] Re-run the shared CourseDefinition contract.
- [x] PDF: extension, readable file, `%PDF-` header, `%%EOF`.
- [x] Video: MP4, H.264, AAC when audio exists, faststart, actual duration, declared-duration tolerance, long/large-video warnings.
- [x] Video interaction: shared 1.1 document validation against owning block, cue timing against actual MP4, `pauseVideo`/`required` evidence, and required-interaction completion consistency.
- [x] HTML: 2.0 protocol and completion-evidence checks.
- [x] Images/posters/audio/captions: existence and role-compatible extensions; captions require valid `WEBVTT` header.
- [x] Course completeness: at least one Part/Slice, objective evidence remains real, estimated course time is consistent with Slice totals, and dense-Slice warnings follow a fixed policy without pretending to perform layout rendering.
- [x] Emit `.course-work/course-validation-report.json` with deterministic hashes, ordered findings, asset evidence, and no timestamp/random ID.
- [x] CLI exits `0` clear, `1` warnings requiring no block, `2` blocked, `3` tool failure. A failed validation must not overwrite a previous successful report as current evidence.
- [x] Commit: `feat: validate course definition 2 packages`.

## Task 5: Synchronize registered findings and require G6 evidence

**Files:** issue registry/schema, Workflow/CLI, validation CLI, tests.

- [x] Register stable G6 issue codes and severities; blockers cannot be accepted, fixed warnings use explicit acknowledgement policy.
- [x] Synchronize current validation findings into `.course-work/issues.json`, resolve disappeared validator findings, and preserve unrelated workflow/review issues.
- [x] Add `.course-work/course-validation-report.json` to G6 artifact tracking.
- [x] Implement `verify_g6_validation(root)` checking current G5 evidence, report status, definition/asset/report hashes, validator code hash, and zero active blockers/decisions.
- [x] Prevent manual G6 completion without current evidence; store hashes on successful completion.
- [x] Changing definition/assets/validator invalidates G6 and downstream gates.
- [x] Commit: `feat: gate definition 2 validation evidence`.

## Task 6: Verify a real migrated course and update the director boundary

**Files:** real migration validation test, director/review Skill docs, validation report, this plan.

- [ ] Create valid local media stand-ins only inside a temporary test directory; never modify the committed teacher fixture or original assets.
- [ ] Import and explicitly approve the real 6-Part/13-Slice/27-Block fixture, compile, validate twice, and prove deterministic report hashes.
- [ ] Update the director to run the 2.0 validator and complete G6 only from current evidence.
- [ ] State the exact remaining boundary: student renderer/browser preview/annotation UI at G7 and real OSS/course POST at G9/G10.
- [ ] Run all Python tests, shared contract tests, typecheck, schema syntax checks, and contract sync.
- [ ] Commit: `docs: route g6 through definition 2 validation`.
