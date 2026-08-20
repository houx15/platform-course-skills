# Generated course cover: v1.4.0 resolution and verification

## Implemented boundary

The teacher toolkit can now generate a course-specific cover through a bounded imagegen2 subagent, preserve the source, encode an exact 16:9 quality-100 WebP, show the real candidate to the teacher, bind approval to its SHA-256, and plan/reuse the OSS upload at:

```text
courses/<slug>/cover/course-cover.webp
```

`course-authoring-v1.4.0` now binds that object through the optional course-relative field `coverAssetPath`. The toolkit is pinned to this tag and sends the generated cover only after upload and teacher approval.

## Ship request

```json
{
  "cover": "",
  "coverAssetPath": "cover/course-cover.webp"
}
```

Enforced rules:

1. `cover` and `coverAssetPath` are mutually exclusive when both are non-empty.
2. `coverAssetPath` must be under `cover/` and end in `.webp`.
3. The server derives `courses/<slug>/<coverAssetPath>` itself. It must not accept a client-supplied OSS object key or URL.
4. Before changing publication status, the server verifies that the object exists, is WebP, and is within the course namespace.
5. The server persists `asset:<relativePath>` internally. Clients must not send `asset:` through the stock `cover` field.
6. `GET /api/v1/courses` and `GET /api/v1/admin/courses` resolve this reference to a short-lived `coverUrl`, while preserving current `img:*`, `grad:*`, empty-cover, and update behavior.
7. Re-shipping with both fields empty preserves the existing cover, matching current idempotent behavior.

## Toolkit G10 acceptance checks

- A valid uploaded `cover/course-cover.webp` ships and produces a non-empty signed `coverUrl`.
- The signed URL is fetched without the admin bearer credential.
- The downloaded SHA-256 and byte count match the exact uploaded bytes.
- A missing object, non-WebP object, unsafe path, external URL, or cross-course path is rejected before status changes.
- `cover` plus `coverAssetPath` is rejected as ambiguous.
- Existing `img:3` and empty-cover requests remain backward-compatible.
- Updating and re-shipping the same slug changes the same course row and does not create another course.
- The toolkit records only `coverUrlPresent`, SHA-256, and byte count. It never persists or prints the signed URL.

Server error behavior is part of the pinned contract: ambiguous stock/generated cover input returns `400 ambiguous_cover`; invalid paths or `asset:` stock values return `400 invalid_cover`; missing and non-WebP objects return `422 cover_not_found` and `422 cover_not_webp`; disabled OSS returns 503. These failures leave the course in preview.
