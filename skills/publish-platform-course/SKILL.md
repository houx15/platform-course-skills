---
name: publish-platform-course
description: Use when a teacher explicitly asks to upload, save, submit, or publish a fully reviewed course to the Mind Imprint student platform.
---

# Publish Platform Course

Handle the only externally mutating phase. Read [api-contract.md](references/api-contract.md). A build, validation, preview, annotation, or review request never authorizes publication.

## Preconditions

1. Run `python _course-toolkit/scripts/course-workflow.py status ROOT --json`. For a newly produced course, require the existing renderer review and independent review that precede publication. For a previously reviewed or published course, preserve its current status and publication identity; never block it solely because it predates the newly added page-plan, semantic-audit, or Agent visual-check records.
2. Run `python _course-toolkit/scripts/manage-course-catalog.py status ROOT --json`. If no current teacher-confirmed catalog binding exists, propose matches from the course title and ask the teacher to select the correct human-readable course. This applies to old courses too. The binding deterministically supplies the fixed slug, title, blurb, category, structured `introduction`, `cardIds`, and catalog cover; do not ask the teacher to review, approve, or edit those values separately and never send `featured_rank`.
3. Initialize publication identity without accepting a free-form slug. The publisher applies the selected catalog's fixed ID and title to the outbound definition in memory; it does not rewrite the reviewed local CourseDefinition or require a second preview solely because the teacher selected the course at publication time:

   ```bash
   python _course-toolkit/scripts/publish-course.py init-state ROOT --json
   ```

   This is the stable slug: each catalog course always uses its canonical `course-01` through `course-33` slug. If that slug exists remotely, the only mode is update; if absent, the only mode is create. Never create an alternate slug for the same course. Require one independent course root and `.course-work` per course; never share or copy publication state between courses.
4. `OSS_ADMIN_KEY` may come from the process environment or 课程目录的 `.env`; 进程环境变量优先. The publication command loads the course `.env` first and uses the toolkit checkout `.env` only as a local development fallback. If a teacher provides the key to the Agent, confirm that `/.env` is ignored, write only `OSS_ADMIN_KEY=...` to that local file, and keep `.env.example` empty. 老师不需要执行命令. 不得回显凭证 or place it in command arguments, ordinary output, generated course files, JSON evidence, or Git. Never print an Authorization header or presigned URL.
5. The 33 approved covers are preseeded once by the platform administrator at the catalog's fixed OSS keys. Do not call image generation, ask the teacher to select or confirm a cover, copy a cover into the course root, or include it in the teacher asset manifest. For `publish`, always use the catalog-relative `coverAssetPath: "cover/course-cover.webp"` and verify the returned `coverUrl` bytes against the catalog SHA-256.

## Prepare the existing publication plan

Choose `save-preview` for a new preview draft or `publish` to save and ship. A previously published course must use `publish`, because its PUT changes live bytes before ship finishes.

Run:

```bash
python _course-toolkit/scripts/publish-course.py preflight ROOT \
  --action publish \
  --json
```

Present the teacher-readable dry run: canonical slug, create/update mode, exact action, definition hash, fixed catalog binding, upload and reuse counts, and risks. Do not present blurb, category, `cardIds`, `introduction`, or cover as separate teacher choices or approval items. State plainly:

- all writes hit production;
- the API is last-writer-wins;
- editing a published course changes live bytes on the definition save;
- ship regenerates TTS and should not be repeated casually;
- unchanged teacher assets are reused only when local upload proof matches the same slug, relative path, and SHA-256; preserve `.course-work`. If that proof is lost, the server has no checksum/existence lookup, so a future run may overwrite the same deterministic key with identical bytes but cannot create an extra object key;
- category, structured introduction, and card IDs come from the confirmed 33-course catalog entry, not free-form publication flags;
- the fixed catalog WebP is never a teacher upload or a count in the teacher manifest. course-authoring-v1.4.0 receives only `coverAssetPath: "cover/course-cover.webp"`; never send the full OSS key, URL, or `asset:` value, and never combine a non-empty stock `cover` with `coverAssetPath`.

Do not expose object keys in the ordinary summary. Multiple relative paths with identical bytes still need separate OSS objects because the CourseDefinition references each relative path.

## Exact approval

Ask the teacher to approve or revise this exact dry run. Only after explicit approval plus rationale, record:

```bash
python _course-toolkit/scripts/course-workflow.py confirm-decision ROOT \
  decision-publication-preflight \
  --choice approve \
  --rationale "TEACHER_RATIONALE" \
  --json
python _course-toolkit/scripts/publish-course.py status ROOT --json
```

Any definition, asset, G6/G7/G8 evidence, catalog selection, options, remote observation, or API base change requires a new preflight and exact approval.

## Execute and recover

Run the deterministic live adapter only when status says `approved: true`:

```bash
python _course-toolkit/scripts/publish-course.py execute ROOT --json
```

The adapter re-reads the canonical slug before mutation, uploads only changed teacher assets, persists each successful upload, PUTs the approved definition/options, reads back the exact definition, ships only for `publish`, then reads back the final status. It never uploads the fixed cover; after ship it requires a non-empty signed `coverUrl`, downloads it without the bearer credential, and verifies that it resolves to the catalog bytes by SHA-256 before completing G10.

After an ambiguous definition or ship timeout, read back first. If the approved definition already exists or status is already `published`, record success without a blind repeated write. An OSS timeout may require overwriting the same deterministic key; it cannot create an extra object path.

Report only verified slug, final status, remote definition hash, uploaded count, reused count, and the safe cover byte-verification result. Never report success from an HTTP 200 alone. Never reveal credentials, Authorization, `coverUrl`, presigned URL query parameters, or raw remote payloads.
