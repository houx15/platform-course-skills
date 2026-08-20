---
name: publish-platform-course
description: Use when a teacher explicitly asks to upload, save, submit, or publish a fully reviewed course to the Mind Imprint student platform.
---

# Publish Platform Course

Handle the only externally mutating phase. Read [api-contract.md](references/api-contract.md). A build, validation, preview, annotation, or review request never authorizes publication.

## Preconditions

1. Run `python _course-toolkit/scripts/course-workflow.py status ROOT --json`. Require current G8. If G8 is incomplete or invalidated, explain that you cannot publish and return to the responsible Skill.
2. Run `python _course-toolkit/scripts/manage-course-catalog.py status ROOT --json`. If no current teacher-confirmed binding exists, propose matches from the course title and ask the teacher to select the correct human-readable course. This applies to old courses too. The binding deterministically supplies fixed `category`, structured `introduction`, and `cardIds`; do not ask the teacher to review, approve, or edit those values separately and never send `featured_rank`.
3. Require a stable slug that exactly equals `course.id`. Initialize it once:

   ```bash
   python _course-toolkit/scripts/publish-course.py init-state ROOT --slug SLUG --json
   ```

   Never replace an existing local identity and never adopt a remote course that merely happens to use the same slug.
4. `OSS_ADMIN_KEY` may come from the process environment or 课程目录的 `.env`; 进程环境变量优先. The publication command loads the course `.env` first and uses the toolkit checkout `.env` only as a local development fallback. If a teacher provides the key to the Agent, confirm that `/.env` is ignored, write only `OSS_ADMIN_KEY=...` to that local file, and keep `.env.example` empty. 老师不需要执行命令. 不得回显凭证 or place it in command arguments, ordinary output, generated course files, JSON evidence, or Git. Never print an Authorization header or presigned URL.
5. Cover generation is deferred to the platform administrator. Do not call image generation, ask the teacher to create a placeholder, or block `save-preview` or `publish` because `.course-work/course-cover.json` is absent. A missing cover does not block preview or publication. If a previously confirmed administrator-supplied cover record exists, include its exact WebP in the manifest and retain the existing `coverAssetPath` verification; otherwise send both stock `cover` and `coverAssetPath` empty so a pre-existing remote cover is preserved.

## Prepare the dry run

Choose `save-preview` for a new preview draft or `publish` to save and ship. A previously published course must use `publish`, because its PUT changes live bytes before ship finishes.

Run:

```bash
python _course-toolkit/scripts/publish-course.py preflight ROOT \
  --action publish \
  --blurb "BLURB" \
  --json
```

Present the teacher-readable dry run: stable slug, create/update mode, exact action, definition hash, blurb, confirmation that fixed catalog metadata is bound, optional existing cover path/hash when present, upload and reuse counts, and risks. Do not present category, `cardIds`, or `introduction` as separate teacher choices or approval items. State plainly:

- all writes hit production;
- the API is last-writer-wins;
- editing a published course changes live bytes on the definition save;
- ship regenerates TTS and should not be repeated casually;
- asset reuse is based on local upload proof for the same slug, relative path, and SHA-256 because the server has no asset existence/checksum endpoint.
- category, structured introduction, and card IDs come from the confirmed 33-course catalog entry, not free-form publication flags;
- when a confirmed administrator-supplied WebP exists, it is included in upload/reuse counts and course-authoring-v1.4.0 receives only the course-relative `coverAssetPath` `cover/course-cover.webp`; without one, cover generation remains deferred and publication proceeds without it. Never send an OSS key, URL, or `asset:` value, and never combine a non-empty stock `cover` with `coverAssetPath`.

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

Any definition, asset, G6/G7/G8 evidence, catalog selection, optional cover, options, remote observation, or API base change requires a new preflight and exact approval.

## Execute and recover

Run the deterministic live adapter only when status says `approved: true`:

```bash
python _course-toolkit/scripts/publish-course.py execute ROOT --json
```

The adapter re-reads the slug before mutation, uploads only planned assets, persists each successful upload, PUTs the approved definition/options, reads back the exact definition, ships only for `publish`, then reads back the final status. For a generated cover it also requires a non-empty signed `coverUrl`, downloads it without the bearer credential, and verifies that it resolves to the exact uploaded bytes by SHA-256 before completing G10.

After an ambiguous definition or ship timeout, read back first. If the approved definition already exists or status is already `published`, record success without a blind repeated write. An OSS timeout may require overwriting the same deterministic key; it cannot create an extra object path.

Report only verified slug, final status, remote definition hash, uploaded count, reused count, and the safe cover byte-verification result. Never report success from an HTTP 200 alone. Never reveal credentials, Authorization, `coverUrl`, presigned URL query parameters, or raw remote payloads.
