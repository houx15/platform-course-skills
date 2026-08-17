# Mind Imprint authoring API contract

Production base: `https://mind-api.uni-robot.cn`. Authentication is `Authorization: Bearer <OSS_ADMIN_KEY>`, read only from the environment.

- `GET /api/v1/admin/courses/{slug}/definition`: bearer read back; 404 means not found; otherwise `{definition, hash, status}`.
- `POST /api/v1/admin/courses/{slug}/asset-upload-url`: `{relativePath, contentType, size}`; returns a short-lived presigned PUT. Upload with the exact required content type and no bearer header.
- `PUT /api/v1/admin/courses/{slug}/definition`: `{definition, blurb, cardIds}`. The same endpoint creates or updates by slug. `course.id` must equal slug.
- `POST /api/v1/admin/courses/{slug}/ship`: `{cover}`; validates assets, generates narration TTS, and sets `published`.

There is no optimistic concurrency, separate published snapshot, remote asset checksum/existence endpoint, staging environment, visibility option, remote course ID, or revision field. PUT is last-writer-wins. A published-course PUT changes live definition bytes before ship. Ship can regenerate TTS. Asset keys are exactly `courses/<slug>/<relativePath>`.

Supported course upload content types include images, PDF, MP4, HTML, `application/json`, and `text/vtt`. Local proof may skip a future upload only for the same slug + relative path + SHA-256 after a verified successful PUT.
