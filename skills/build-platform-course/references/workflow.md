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

Run `python scripts/validate-course-v2.py ROOT --json`. It checks the current G5 set, shared contract, exact referenced asset inventory and hashes, safe paths, PDF signature/completeness, MP4 codecs/faststart/duration, interaction cues and completion consistency, WEBVTT headers, the renderer-compatible HTML protocol and completion evidence, and fixed course-completeness warnings. Static checks cannot claim real browser rendering. `review-platform-course` runs independently at G8 after real G7 preview and cannot substitute for G6 validation.

Successful validation writes `.course-work/course-validation-report.json`; blocked validation writes `.course-work/course-validation-attempt.json` and preserves the previous successful report. Validation findings synchronize into `.course-work/issues.json`. `course-package-density-warning` is advisory. `course-package-estimate-warning` and `course-package-media-warning` require explicit teacher acknowledgement and a real rationale:

```bash
python scripts/course-workflow.py accept-warning ROOT ISSUE_ID \
  --rationale "TEACHER_RATIONALE" \
  --json
```

Never invent acknowledgement. Complete the gate only through:

```bash
python scripts/course-workflow.py complete-gate ROOT G6 --json
```

This rebuilds validation and verifies the exact definition, report, validator-code, asset-set, and per-asset hashes. Any changed delivery asset or validator invalidates G6 and downstream work, including assets stored outside `course/assets/`.

Exit: the deterministic report is current, no blocker remains, every required warning is explicitly accepted, and G6 evidence hashes are recorded.

### G7 — Preview review

Inputs: the exact definition hash, asset hashes, renderer version, and preview manifest.

Checks: use the same renderer implementation as the student platform; inspect layouts, media, navigation, workflow, iframe behavior, and completion events in a real browser. Collect structure-linked annotations outside the runtime definition.

Invoke `preview-platform-course` and run `python scripts/preview-course.py ROOT`. The bundled browser host mounts the exact pinned student renderer, uses local assets and in-memory session adapters, and places annotation chrome beside the renderer. The teacher must visit every Slice, inspect meaningful interactions and branches, resolve required annotations and runtime errors, then explicitly complete the review. Do not complete G7 from `index.md`, static validation, a screenshot, or the fact that the page opened.

The authoring-side annotation protocol is available before the UI integration. Reconcile stable targets with:

```bash
python scripts/manage-annotations.py reconcile ROOT --json
```

Write a current-hash `.course-work/annotation-revision-plan.json`, then prepare it:

```bash
python scripts/manage-annotations.py prepare ROOT \
  .course-work/annotation-revision-plan.json \
  --json
```

Mechanical copy changes may proceed. Semantic layout, workflow, media, correctness, completion, or source changes require the exact pending decision to be presented to the teacher. After explicit approval and rationale:

```bash
python scripts/course-workflow.py confirm-decision ROOT DECISION_ID \
  --choice approve \
  --rationale "TEACHER_RATIONALE" \
  --json
python scripts/manage-annotations.py apply ROOT \
  .course-work/annotation-revision-plan.json \
  --json
```

Application writes Blueprint and annotations atomically, then requires reconcile, compile, G5, CourseDefinition 2.0 validation, and G6. Runtime bugs have no Blueprint operations and remain preview blockers. After application, applied annotations remain unverified until the shared renderer verifies the new definition in a later G7 preview. The preview writes current hash-bound `.course-work/preview-manifest.json`; then `python scripts/course-workflow.py complete-gate ROOT G7 --json` independently verifies it.

### G8 — Independent final review

Inputs: original sources, decisions, Blueprint/storyboard, generated definition, assets, validation reports, and current preview evidence.

Checks: re-read evidence independently; do not accept the director's or compiler's earlier conclusion as proof. Any open required annotation, stale preview, unresolved semantic issue, or failed Part dimension blocks.

Exit: the independent report is publishable for exactly the reviewed hashes.

### G9 — Publication preflight

Inputs: approved definition hash, current G6 validation, renderer-backed G8 review evidence, relative-path asset manifest, stable slug/publish state, and bearer readback of that slug.

Invoke `publish-platform-course`. Initialize publish state once; this command refuses to replace a different existing identity:

```bash
python scripts/publish-course.py init-state ROOT --slug SLUG --json
```

Prepare the exact production dry run only from current G8 evidence:

```bash
python scripts/publish-course.py preflight ROOT \
  --action publish \
  --blurb "BLURB" \
  --cover "img:3" \
  --json
```

The deterministic `.course-work/publication-preflight.json` shows create versus update, stable slug, remote status/hash, changed versus locally proven unchanged paths, exact options, and production limitations. Existing slugs are never silently adopted. The backend has no revision, visibility option, remote asset inventory, or optimistic concurrency; the preflight states these limits directly.

Present this readable summary and obtain the exact teacher decision with a real rationale through `course-workflow.py confirm-decision`. Check it with `python scripts/publish-course.py status ROOT --json`. A changed definition, evidence, asset manifest, remote observation, identity, options, or API base makes approval non-current.

The live execute command completes G9 immediately before its first external mutation and binds the preflight, manifest, publish state, G8 evidence, discovery, and publisher code hashes.

### G10 — Remote verification

Inputs: results from `python scripts/publish-course.py execute ROOT --json`.

Checks: upload each changed relative path and persist every successful PUT for resume; reuse only the same slug/path/SHA-256 local proof; save through the same slug-keyed PUT for create and update; after an ambiguous response, read before retry; read the remote definition back; verify slug, exact definition, remote hash, and final status before updating verified local state.

Fake adapters never complete G10. G10 requires an operation explicitly recorded as using the live publication adapter. Exit only after post-write bearer readback verifies the expected remote result.

In operational terms, G10 requires the real publication adapter. Only it may perform the real course POST/PUT workflow and OSS upload after explicit publication approval for the current dry run.

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
- Changed asset manifest, remote identity, publish state, renderer-backed review evidence, discovery snapshot, publication preflight, or publisher code invalidates G9.
- Changed verified publication operation or its read-back state invalidates G10.

For preview comments, classify each annotation as mechanical, semantic, or runtime bug. Mechanical changes may be applied with an audit record. Semantic changes require teacher confirmation. Runtime bugs remain blockers and must not be hidden by changing course content. After any applied comment, regenerate from authoring truth, validate, rebuild preview evidence, and rerun the independent review.

## Teacher-facing reporting

Tell the teacher:

- what phase was restored;
- what changed since the last confirmed gate;
- which decisions only they can make;
- which blockers or warnings exist in plain language;
- what will happen next.

Keep credentials, object-store keys, signed URLs, request payloads, raw stack traces, internal Skill routing, and generated JSON out of ordinary conversation. A request to build, check, revise, or preview authorizes local work only. Publication requires its separate dry run and explicit approval.
