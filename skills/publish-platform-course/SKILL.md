---
name: publish-platform-course
description: Use when a teacher explicitly asks to upload, save, submit, or publish a fully reviewed course to the Mind Imprint student platform.
---

# Publish Platform Course

Handle the only externally mutating phase. Read [api-contract.md](references/api-contract.md). A build, validation, preview, annotation, or review request never authorizes publication.

## Preconditions

1. Run `python _course-toolkit/scripts/course-workflow.py status ROOT --json`. Require current G8. If G8 is incomplete or invalidated, explain that you cannot publish and return to the responsible Skill.
2. Run `python _course-toolkit/scripts/manage-course-catalog.py status ROOT --json`. If no current teacher-confirmed binding exists, propose matches from the course title and ask the teacher to select the correct human-readable course. This applies to old courses too. The binding deterministically supplies `category`, structured `introduction`, and `cardIds`; do not ask for those fields separately and never send `featured_rank`.
3. Require a stable slug that exactly equals `course.id`. Initialize it once:

   ```bash
   python _course-toolkit/scripts/publish-course.py init-state ROOT --slug SLUG --json
   ```

   Never replace an existing local identity and never adopt a remote course that merely happens to use the same slug.
4. `OSS_ADMIN_KEY` may come from the process environment or 课程目录的 `.env`; 进程环境变量优先. The publication command loads the course `.env` first and uses the toolkit checkout `.env` only as a local development fallback. If a teacher provides the key to the Agent, confirm that `/.env` is ignored, write only `OSS_ADMIN_KEY=...` to that local file, and keep `.env.example` empty. 老师不需要执行命令. 不得回显凭证 or place it in command arguments, ordinary output, generated course files, JSON evidence, or Git. Never print an Authorization header or presigned URL.
5. For `publish`, require `.course-work/course-cover.json`. Run `python _course-toolkit/scripts/manage-course-cover.py prompt ROOT --json` and pass its pinned course-cover prompt, beginning `Create a 16:9 conceptual course cover for high-school students.`, unchanged to the separate imagegen2 subagent. Preserve the original generation under `.course-work/cover-sources/` and use `manage-course-cover.py prepare` with that same prompt to create an exact 16:9 quality-100 WebP candidate through `cwebp -q 100`. Show it to the teacher and record explicit confirmation with `manage-course-cover.py confirm` before `.course-work/cover-delivery/course-cover.webp` enters the OSS manifest as `cover/course-cover.webp`. Catalog, prompt, or file hash changes require review again.

## Prepare the dry run

Choose `save-preview` for a new preview draft or `publish` to save and ship. A previously published course must use `publish`, because its PUT changes live bytes before ship finishes.

Run:

```bash
python _course-toolkit/scripts/publish-course.py preflight ROOT \
  --action publish \
  --blurb "BLURB" \
  --json
```

Present the teacher-readable dry run: stable slug, create/update mode, exact action, definition hash, blurb, catalog-derived category/introduction/card IDs, generated cover path/hash, upload and reuse counts, and risks. State plainly:

- all writes hit production;
- the API is last-writer-wins;
- editing a published course changes live bytes on the definition save;
- ship regenerates TTS and should not be repeated casually;
- asset reuse is based on local upload proof for the same slug, relative path, and SHA-256 because the server has no asset existence/checksum endpoint.
- category, structured introduction, and card IDs come from the confirmed 33-course catalog entry, not free-form publication flags;
- the confirmed generated WebP is included in upload/reuse counts, but authoring API v1.3.0 still accepts only stock `img:*` values for the visible cover. Do not execute or claim a complete generated-cover publication until the student API adds a documented course-asset cover reference.

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

Any definition, asset, G6/G7/G8 evidence, catalog selection, generated cover, options, remote observation, or API base change requires a new preflight and exact approval.

## Execute and recover

Run the deterministic live adapter only when status says `approved: true`:

```bash
python _course-toolkit/scripts/publish-course.py execute ROOT --json
```

The adapter re-reads the slug before mutation, uploads only planned assets, persists each successful upload, PUTs the approved definition/options, reads back the exact definition, ships only for `publish`, then reads back the final status. It completes G10 only from live verified evidence.

After an ambiguous definition or ship timeout, read back first. If the approved definition already exists or status is already `published`, record success without a blind repeated write. An OSS timeout may require overwriting the same deterministic key; it cannot create an extra object path.

Report only verified slug, final status, remote definition hash, uploaded count, and reused count. Never report success from an HTTP 200 alone. Never reveal credentials, Authorization, presigned URL query parameters, or raw remote payloads.
