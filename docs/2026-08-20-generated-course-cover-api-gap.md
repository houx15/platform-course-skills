# Generated course cover: student authoring API gap

## Current boundary

The teacher toolkit can now generate a course-specific cover through a bounded imagegen2 subagent, preserve the source, encode an exact 16:9 quality-100 WebP, show the real candidate to the teacher, bind approval to its SHA-256, and plan/reuse the OSS upload at:

```text
courses/<slug>/cover/course-cover.webp
```

`course-authoring-v1.3.0` cannot make that object the visible course cover. `POST /api/v1/admin/courses/{slug}/ship` documents `cover` as a stock catalog value such as `img:3`, and the course summary resolver only turns supported stock values into `coverUrl`. Uploading the WebP and passing an arbitrary object key would therefore create a published course with no usable generated cover URL.

The toolkit deliberately blocks final `publish` at this boundary. It does not silently substitute a stock image or report that an uploaded file is live.

## Smallest safe additive API change

Add an optional course-relative cover field to the ship request while retaining the existing stock field:

```json
{
  "cover": "",
  "coverAssetPath": "cover/course-cover.webp"
}
```

Rules:

1. `cover` and `coverAssetPath` are mutually exclusive when both are non-empty.
2. `coverAssetPath` uses the same safe relative-path validation as course assets. For this first version, require the fixed value `cover/course-cover.webp` or at least a path under `cover/` ending in `.webp`.
3. The server derives `courses/<slug>/<coverAssetPath>` itself. It must not accept a client-supplied OSS object key or URL.
4. Before changing publication status, verify that the object exists, is WebP, and is within the course namespace. Dimension checking at 16:9 is recommended; the teacher toolkit already performs it locally.
5. Persist a course-cover reference that cannot sign an arbitrary object. One safe design is `asset:<relativePath>` plus a course-specific resolver that receives the course slug and derives the OSS key at read time.
6. `GET /api/v1/courses` and `GET /api/v1/admin/courses` must resolve this reference to a short-lived `coverUrl`, while preserving current `img:*`, `grad:*`, empty-cover, and update behavior.
7. Re-shipping with both fields empty preserves the existing cover, matching current idempotent behavior.

## Acceptance tests

- A valid uploaded `cover/course-cover.webp` ships and produces a non-empty signed `coverUrl`.
- A missing object, non-WebP object, unsafe path, external URL, or cross-course path is rejected before status changes.
- `cover` plus `coverAssetPath` is rejected as ambiguous.
- Existing `img:3` and empty-cover requests remain backward-compatible.
- Updating and re-shipping the same slug changes the same course row and does not create another course.
- The generated cover URL resolves to the exact bytes uploaded at `courses/<slug>/cover/course-cover.webp`.

After this contract ships under a new pinned authoring tag, the teacher toolkit can enable its generated-cover capability and complete the live publish test without changing the local generation, approval, hashing, upload, or reuse workflow.
