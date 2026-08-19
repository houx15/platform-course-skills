# Mind Imprint authoring API contract

Pinned student handover tag: `course-authoring-v1.3.0`.

Production base: `https://mind-api.uni-robot.cn`. Authentication is `Authorization: Bearer <OSS_ADMIN_KEY>`, read only from the environment.

- `GET /api/v1/admin/courses/{slug}/definition`: bearer read back; 404 means not found; otherwise `{definition, hash, status}`.
- `POST /api/v1/admin/courses/{slug}/asset-upload-url`: `{relativePath, contentType, size}`; returns a short-lived presigned PUT. Upload with the exact required content type and no bearer header.
- `PUT /api/v1/admin/courses/{slug}/definition`: `{definition, blurb, cardIds, category, introduction}`. `category` is one of the seven controlled slugs. `introduction` is `{hook, whatYouDo, takeaways[], alignment:{ib[],otherIntl[],domestic[]}, keywords[]}`. The confirmed 33-course catalog supplies all three metadata fields. The same endpoint creates or updates by slug. `course.id` must equal slug. Never send `featured_rank` or `featuredRank`; home-page curation is student-end owned.
- `POST /api/v1/admin/courses/{slug}/ship`: `{cover}`; validates assets, generates narration TTS, and sets `published`. In v1.3.0, `cover` is still a stock cover catalog id such as `img:3`; an empty string preserves the current cover.

There is no optimistic concurrency, separate published snapshot, remote asset checksum/existence endpoint, staging environment, visibility option, remote course ID, or revision field. PUT is last-writer-wins. A published-course PUT changes live definition bytes before ship. Ship can regenerate TTS. Asset keys are exactly `courses/<slug>/<relativePath>`.

Supported course upload content types include images, PDF, MP4, HTML, `application/json`, and `text/vtt`. Local proof may skip a future upload only for the same slug + relative path + SHA-256 after a verified successful PUT.

A confirmed generated cover is uploaded as `courses/<slug>/cover/course-cover.webp`, exact 16:9, quality-100 WebP. This upload alone does not make it visible: v1.3.0 has no documented ship value that resolves a per-course OSS object. Final generated-cover publication remains blocked until the student API safely accepts a course-relative cover path and returns it through `coverUrl`.

The proposed additive request is `{cover:"", coverAssetPath:"cover/course-cover.webp"}`. The server must derive the OSS key from the path slug and validate the object; the toolkit does not send this field while pinned to v1.3.0. See `docs/2026-08-20-generated-course-cover-api-gap.md` in the source repository.
