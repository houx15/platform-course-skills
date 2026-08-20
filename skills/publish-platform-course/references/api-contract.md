# Mind Imprint authoring API contract

Pinned student handover tag: `course-authoring-v1.4.0`.

Production base: `https://mind-api.uni-robot.cn`. Authentication is `Authorization: Bearer <OSS_ADMIN_KEY>`, read only from the environment.

- `GET /api/v1/admin/courses/{slug}/definition`: bearer read back; 404 means not found; otherwise `{definition, hash, status}`.
- `POST /api/v1/admin/courses/{slug}/asset-upload-url`: `{relativePath, contentType, size}`; returns a short-lived presigned PUT. Upload with the exact required content type and no bearer header.
- `PUT /api/v1/admin/courses/{slug}/definition`: `{definition, blurb, cardIds, category, introduction}`. `category` is one of the seven controlled slugs. `introduction` is `{hook, whatYouDo, takeaways[], alignment:{ib[],otherIntl[],domestic[]}, keywords[]}`. The confirmed 33-course catalog supplies all three metadata fields. The same endpoint creates or updates by slug. `course.id` must equal slug. Never send `featured_rank` or `featuredRank`; home-page curation is student-end owned.
- `POST /api/v1/admin/courses/{slug}/ship`: `{cover, coverAssetPath?}`; validates assets, generates narration TTS, and sets `published`. Use `coverAssetPath: "cover/course-cover.webp"` for a generated cover. `cover` and `coverAssetPath` are mutually exclusive when both are non-empty. The path must be under `cover/` and end in `.webp`; the server derives `courses/<slug>/<coverAssetPath>`, verifies that object before publication, and persists `asset:<relativePath>`. Never send an OSS key, URL, or `asset:` value. Re-ship with both fields empty preserves the current cover.

There is no optimistic concurrency, separate published snapshot, remote asset checksum/existence endpoint, staging environment, visibility option, remote course ID, or revision field. PUT is last-writer-wins. A published-course PUT changes live definition bytes before ship. Ship can regenerate TTS. Asset keys are exactly `courses/<slug>/<relativePath>`.

Supported course upload content types include images, PDF, MP4, HTML, `application/json`, and `text/vtt`. Local proof may skip a future upload only for the same slug + relative path + SHA-256 after a verified successful PUT.

Cover generation is deferred to the platform administrator and is optional for this teacher workflow. With no confirmed cover record, ship sends both cover fields empty; this preserves an existing remote cover and does not block publication. If an administrator-supplied confirmed cover exists, it is uploaded as `courses/<slug>/cover/course-cover.webp`, exact 16:9 WebP, then shipped as `{cover:"", coverAssetPath:"cover/course-cover.webp"}`. Before G10 completes, the toolkit finds the same slug through `GET /api/v1/admin/courses`, requires a non-empty signed `coverUrl`, downloads it without the bearer header, and verifies that it resolves to the exact uploaded bytes. It records only the hash, byte count, and `coverUrl` presence; the signed URL is never persisted or printed.

Invalid paths or legacy `asset:` values are rejected as `invalid_cover`; non-empty `cover` plus `coverAssetPath` is `ambiguous_cover`; missing/non-WebP objects are `cover_not_found` / `cover_not_webp`. An OSS-disabled server returns 503. These failures leave the course in preview.
