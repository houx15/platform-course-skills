# Course production workflow

This reference governs the persistent process behind `build-platform-course`. The director Skill is the only teacher-facing entry. Internal specialists and deterministic tools are implementation details and must not be presented as choices the teacher has to operate.

## Non-negotiable rules

- Persist state in `.course-work/session.json`; do not reconstruct progress from conversation memory.
- Restore and reconcile before any analysis or generation.
- Follow the earliest incomplete or invalidated gate. G0–G10 cannot be skipped.
- A file's existence is not evidence that a gate passed for the current hashes.
- `.course-work/course-blueprint.json` is the authoring source of truth. Generated runtime files are never edited directly.
- Blockers cannot be accepted or dismissed. Decisions wait for the teacher. Warnings follow the registered code policy.
- All semantic changes require teacher confirmation. Never silently change learning purpose, source disposition, correct answers, rubrics, blocking rules, media behavior, or a substantive course structure.
- Raw sources remain unchanged. Ignore ZIP files. Keep writes inside `course/`, `.course-work/`, and named generated views.
- By policy, local completion never implies upload, POST, or publication.

## Mandatory start and resume sequence

From the repository root, substitute the explicit course root for `ROOT`:

```bash
python scripts/course-workflow.py status ROOT --json
```

If the session does not exist, initialize it with a stable local identity and every explicit input path:

```bash
python scripts/course-workflow.py init ROOT \
  --course-local-id COURSE_ID \
  --source materials/index.md \
  --json
```

If the session exists, reconcile it before doing other work:

```bash
python scripts/course-workflow.py reconcile ROOT --json
```

Reconciliation hashes tracked artifacts, rejects unsafe relative paths and symlinks, ignores ZIP content in directory hashes, resolves returned sources, and invalidates only dependent gates. Present the restored phase, readable open issues, pending teacher decisions, and the next action. Do not show raw JSON or internal Skill names unless technical diagnostics were requested.

When a gate's checks genuinely pass, record it explicitly:

```bash
python scripts/course-workflow.py complete-gate ROOT G0 --json
```

Use `set-status ROOT waiting-for-teacher --json` while a required decision is pending. Never use a status change to simulate gate completion.

## Phases

The stable phases are:

1. `intake`
2. `material-review`
3. `course-brief`
4. `course-design`
5. `media-design`
6. `compile`
7. `validate`
8. `preview`
9. `revise`
10. `final-review`
11. `publish`
12. `complete`

Pauses and failures are statuses, not new phases. A revision returns to the earliest responsible gate and then moves forward again.

## G0–G10 quality gates

### G0 — Workspace safety and identity

Inputs: explicit course root, stable `courseLocalId`, and explicit source paths.

Checks: all source paths are safe and relative; `.course-work` is not a symlink; ZIP is ignored; writes are bounded; no credential is stored in course files.

Exit: the safe workspace and local identity are persisted.

### G1 — Material inventory

Inputs: original materials and extraction records.

Checks: inventory every supported source; report missing, unreadable, duplicate, corrupt, or unsupported inputs; classify student-facing versus authoring-only material; invoke `analyze-course-materials` internally. Ask explicitly about video and independent HTML 即使材料没有提到 either one. Present every 完整 PDF candidate and confirm its exact file and learning purpose. A required missing document remains `blocking: true`; 不得用摘要替代全文.

Exit: the teacher confirms the material summary, exclusions, video/HTML intent, and complete-document PDF use.

### G2 — Course brief

Inputs: confirmed material analysis and teacher decisions.

Checks: record audience, prior knowledge, course purpose, objectives, estimated time, assessment intent, tone, and constraints. Do not manufacture meaning-changing choices.

Exit: the teacher approves the brief and all required decisions are confirmed.

### G3 — Course design

Inputs: approved brief and source coverage.

Checks: design the 课程开场, Parts, Slices, Blocks, layouts, learner actions, evidence, and conclusion. Maintain `courseFrame` and `objectiveAlignment`. Present the 课程首尾设计表, then one Part/Slice row per learning unit. Static text, images, or PDF alone do not prove objective attainment. Encode the approved result as `.course-work/course-blueprint.json`, including provenance and the exact decision IDs that approve it.

Exit: the teacher confirms the complete design, including required assets and meaningful assessment behavior.

### G4 — Media design

Inputs: accepted video, HTML, PDF, image, and other asset needs.

Checks: invoke `design-video-interactions` and `design-course-html` internally where required; preserve originals; confirm interaction semantics; record provisional timing or absent files as blockers.

Exit: every complex-media design and source file is confirmed and technically checkable.

### G5 — Compile

For existing `schemaVersion: 1.1` material, use `python scripts/import-legacy-course.py LEGACY_COURSE STORYBOARD OUTPUT --json`. The import does not carry forward legacy approval. It records every CourseDefinition 2.0 assumption and remains unconfirmed until the teacher answers a new context-hashed decision.

Compile the approved Blueprint with `python scripts/compile-course.py ROOT --json`. The command deterministically emits CourseDefinition 2.0, a runtime source map, and a compilation report as one recoverable output set. The shared student Zod contract is the sole runtime schema gate. Always return changes to Blueprint and never hand edit `course/course.json`.

Complete G5 with `python scripts/course-workflow.py complete-gate ROOT G5 --json`. G5 requires current compilation hashes for Blueprint, definition, source map, report, compiler code, and contract snapshot; it also reruns the shared contract. A stale or partial output set cannot pass.

Exit: compilation succeeds reproducibly, the source map resolves stable runtime targets, and all current compilation hashes are recorded.

### G6 — Static and asset validation

Inputs: generated course definition and all referenced local assets.

Checks: contract, references, IDs, learning alignment, HTML bridge/report rules, video container/codecs/faststart/timing, PDF signature/completeness, and asset path safety. Static checks cannot claim real browser rendering. The legacy `review-platform-course` path still targets schema 1.1; until the enhanced 2.0 validator is complete, do not use it to certify G6.

Exit: no blocker or unresolved teacher decision remains. Any warning follows its registered policy.

### G7 — Preview review

Inputs: the exact definition hash, asset hashes, renderer version, and preview manifest.

Checks: use the same renderer implementation as the student platform; inspect layouts, media, navigation, workflow, iframe behavior, and completion events in a real browser. Collect structure-linked annotations outside the runtime definition.

The student renderer, browser preview, and annotation UI are not implemented in this repository yet. Do not complete G7 from `index.md`, static validation, or an invented preview. When the integration exists, the teacher must mark the current preview review complete and required annotations must be resolved.

### G8 — Independent final review

Inputs: original sources, decisions, Blueprint/storyboard, generated definition, assets, validation reports, and current preview evidence.

Checks: re-read evidence independently; do not accept the director's or compiler's earlier conclusion as proof. Any open required annotation, stale preview, unresolved semantic issue, or failed Part dimension blocks.

Exit: the independent report is publishable for exactly the reviewed hashes.

### G9 — Publication preflight

Inputs: approved definition hash, asset manifest, remote identity/publish state, and G8 report.

Checks: prepare a dry run showing create versus update, changed versus reused assets, remote revision expectations, and intended visibility. Require explicit publication approval for that exact plan. Do not infer approval from local course completion or a previous publication.

Exit: the exact dry run is approved and still current. OSS and the real course POST remain outside the current implementation.

### G10 — Remote verification

Inputs: results from the real publication adapter.

Checks: upload only changed hashes; create or update the stable remote course identity; handle ambiguous retries without duplicate creates; read the remote course back; verify revision, definition hash, asset references, and publication status.

G10 requires the real publication adapter. The local CLI intentionally refuses manual G10 completion. Exit only after the post-write read verifies the expected remote result.

## Issues and decisions

All tools use `.course-work/issues.json` and one versioned issue-code registry:

- `blocker`: stops its gate and cannot be accepted or dismissed;
- `decision-required`: waits for a recorded teacher answer;
- `warning`: follows its fixed acknowledgement policy and never changes severity ad hoc;
- `info`: records a non-blocking fact.

`.course-work/decisions.json` stores each question with a context hash. A confirmed answer cannot be overwritten. If relevant context changes, invalidate the old decision and ask only the changed question. Never ask the teacher to restate confirmed material.

## Targeted invalidation and revision

- Changed raw material or an explicit external source invalidates G1 and downstream work.
- Changed course brief invalidates G2 and downstream work.
- Changed Blueprint invalidates G3 and downstream work.
- Changed media design invalidates G4 and downstream work.
- Changed generated definition, source map, compilation report, compiler code, or shared contract snapshot invalidates G5 and downstream work.
- Changed delivery assets invalidate G6 and downstream work.
- Changed renderer version or preview manifest invalidates G7 and downstream work.
- Open or changed annotations invalidate G8 and G9; in short, annotations invalidate G8 and G9 until verified in a new preview.
- Changed final review invalidates G8 and G9.
- Changed asset manifest, remote identity, or publish state invalidates G9.

For preview comments, classify each annotation as mechanical, semantic, or runtime bug. Mechanical changes may be applied with an audit record. Semantic changes require teacher confirmation. Runtime bugs remain blockers and must not be hidden by changing course content. After any applied comment, regenerate from authoring truth, validate, rebuild preview evidence, and rerun the independent review.

## Teacher-facing reporting

Tell the teacher:

- what phase was restored;
- what changed since the last confirmed gate;
- which decisions only they can make;
- which blockers or warnings exist in plain language;
- what will happen next.

Keep credentials, object-store keys, signed URLs, request payloads, raw stack traces, internal Skill routing, and generated JSON out of ordinary conversation. A request to build, check, revise, or preview authorizes local work only. Publication requires its separate dry run and explicit approval.
