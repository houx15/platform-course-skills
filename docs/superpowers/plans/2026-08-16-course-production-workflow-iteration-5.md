# Course Production Workflow Iteration 5 Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` task by task. Work on `dev`, use no worktree or subagents, commit each completed task, and do not push.

**Goal:** Prepare the complete publication-side local core without making a real OSS or student-platform request: deterministic asset manifests, per-course hash deduplication, stable remote course identity, create/update conflict detection, exact dry-run approval, mockable adapters, idempotent recovery, and verified state transitions.

**Architecture:** Build publication inputs only from current G6 evidence and future G8 evidence supplied as a signed/hash-bound local artifact. Keep `.course-work/asset-manifest.json` as local/verified-remote asset knowledge and `.course-work/publish-state.json` as the stable identity/revision record. A deterministic preflight combines those records with an adapter-produced remote discovery snapshot to decide create versus update, changed versus reusable assets, optimistic revision expectations, and blockers. Adapter protocols receive secrets at call time but never persist them. Tests use in-memory fakes only; no live network, credentials, OSS, or course API is configured.

**Important boundary:** The local toolkit may prepare and approve G9 evidence, but current CLI cannot genuinely complete G9 while renderer-backed G7 and independent G8 evidence are absent. G10 completion remains reserved for a real adapter followed by remote read-back verification; fake adapters prove behavior but never mark a real course published.

---

## Task 1: Build deterministic content-addressed asset manifests

**Files:** `course_toolkit/publication.py`, asset manifest schema, CLI/tests.

- [x] Build the local manifest only from a current successful G6 report and its exact referenced assets.
- [x] Group identical bytes once within the course namespace while retaining every relative path, consumer, role, size, extension/MIME, and SHA-256.
- [x] Derive deterministic course-scoped object keys from hash plus safe extension; never include credentials, signed URLs, or random IDs.
- [x] Preserve verified remote records only when uploaded hash/object key still match; changed files become upload-required and unchanged files remain reusable.
- [x] Exclude unreferenced files from upload and report them as local-only observations without deleting them.
- [x] Commit: `feat: build content addressed course asset manifests`.

## Task 2: Define remote identity and discovery state

**Files:** publication module, publish-state/discovery schemas, tests.

- [x] Define strict local publish state with courseLocalId, slug, optional remoteCourseId/status/revision, published hashes, last operation ID, and verified time.
- [x] Define one adapter discovery snapshot: `found`, `not-found`, `ambiguous`, or `unavailable`, plus remote identity/revision/definition and verified asset records when present.
- [x] Resolve create only when local state has no remote ID and discovery proves not-found; resolve update only when stable local and discovered identity agree.
- [x] Treat existing slug without reconciled local identity, mismatched IDs, stale revisions, ambiguous timeout/retry state, and unavailable discovery as blockers.
- [x] Keep definition revision distinct from CourseDefinition schemaVersion.
- [x] Commit: `feat: protect stable remote course identity`.

## Task 3: Generate and approve exact publication dry runs

**Files:** preflight schema/CLI, DecisionStore/issue integration, tests.

- [x] Require current G6 evidence and an explicit current G8 review-evidence input; never infer publishability from compilation or static validation.
- [x] Emit deterministic `.course-work/publication-preflight.json` listing create/update mode, expected remote revision, definition hash, assets to upload/reuse, intended status/visibility, and limitations.
- [x] Synchronize identity/asset/review blockers into registered G9 issues.
- [x] Create one context-hashed teacher decision for the exact dry run; any changed definition, manifest, identity, revision, visibility, or asset decision invalidates approval.
- [x] Add CLI prepare/status commands that are read-only externally and make no network requests.
- [x] Commit: `feat: prepare hash bound publication dry runs`.

## Task 4: Implement mockable idempotent publication orchestration

**Files:** adapter protocols/orchestrator, in-memory fakes in tests, operation-state schema.

- [x] Define object-store and course-API protocols with verified results, idempotency keys, expected revisions, discovery, create/update, and read-back.
- [x] Upload each unique changed hash once, reuse verified unchanged assets, and persist each verified upload so a partial batch resumes safely.
- [x] Use stable operation/definition hashes for retry idempotency; after an ambiguous create/update response, discover/read before any retry and never issue a second blind create.
- [x] Submit create only in create mode and update only against the known remoteCourseId/revision; never turn an update failure into create.
- [x] Verify remote course ID, revision, definition hash, asset references, and status by post-write read before updating publish state.
- [x] Prove with fakes that repeated publication skips uploads and updates the same course rather than creating another one.
- [x] Commit: `feat: orchestrate idempotent course publication`.

## Task 5: Bind G9/G10 evidence without enabling live publication

**Files:** Workflow/CLI, director/reference Skill, validation report, this plan, tests.

- [ ] Define G9 evidence hashes for approved preflight, manifest, publish state, current G8 review, and publisher code; changes invalidate G9/downstream.
- [ ] Prevent manual G9 when real current G8 evidence or adapter discovery is absent; retain the existing real-adapter-only G10 rule.
- [ ] Keep fake-adapter execution available only as tests/library injection, never as a teacher-facing "published" command.
- [ ] Update the director to present a dry run and request explicit approval only after G8, while clearly stating the live adapter is pending.
- [ ] Run all Python tests, shared contract tests, typecheck, schema checks, contract sync, and Skill scenarios.
- [ ] Commit: `docs: define safe publication adapter boundary`.
