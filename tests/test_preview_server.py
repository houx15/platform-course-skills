import json
import os
import threading
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from course_toolkit.preview_server import (
    create_preview_server,
    validate_preview_prerequisites,
)


class PreviewServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "course" / "assets").mkdir(parents=True)
        (self.root / "course" / "course.json").write_text(
            json.dumps({"schemaVersion": "2.0", "course": {"id": "preview-course"}}),
            encoding="utf-8",
        )
        (self.root / "course" / "assets" / "note.txt").write_text("asset", encoding="utf-8")
        self.static = self.root / "preview-static"
        self.static.mkdir()
        (self.static / "index.html").write_text("<h1>preview</h1>", encoding="utf-8")
        self.server = create_preview_server(self.root, static_dir=self.static)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as response:
            return response.status, response.headers, response.read()

    def put_json(self, path, payload):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()

    def post_json(self, path, payload):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()

    def test_default_bind_is_loopback_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        with self.assertRaises(ValueError):
            create_preview_server(self.root, host="0.0.0.0", static_dir=self.static)

    def test_document_endpoint_reads_only_canonical_course_document(self):
        status, headers, body = self.get("/__course_preview/document")

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["course"]["id"], "preview-course")
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_assets_are_root_constrained(self):
        status, _, body = self.get("/course-assets/assets/note.txt")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"asset")

        for path in (
            "/course-assets/../course.json",
            "/course-assets/%2e%2e/course.json",
            "/course-assets/%2Fetc%2Fpasswd",
        ):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as caught:
                self.get(path)
            self.assertIn(caught.exception.code, {400, 403, 404})

    def test_symlink_asset_escape_is_rejected(self):
        outside = self.root / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        (self.root / "course" / "assets" / "escape.txt").symlink_to(outside)

        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/course-assets/assets/escape.txt")

        self.assertEqual(caught.exception.code, 403)

    def test_annotations_are_the_only_writable_preview_record(self):
        payload = {"schemaVersion": "1.0", "annotations": []}

        status, _ = self.put_json("/__course_preview/annotations", payload)

        self.assertEqual(status, 200)
        saved = json.loads((self.root / ".course-work" / "annotations.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, payload)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.put_json("/course-assets/assets/note.txt", {"replace": True})
        self.assertEqual(caught.exception.code, 405)

    def test_responses_never_expose_environment_credentials(self):
        previous = os.environ.get("OSS_ADMIN_KEY")
        os.environ["OSS_ADMIN_KEY"] = "preview-secret-must-not-leak"
        try:
            _, _, document = self.get("/__course_preview/document")
            _, _, annotations = self.get("/__course_preview/annotations")
        finally:
            if previous is None:
                os.environ.pop("OSS_ADMIN_KEY", None)
            else:
                os.environ["OSS_ADMIN_KEY"] = previous

        self.assertNotIn(b"preview-secret-must-not-leak", document + annotations)

    def test_preview_evidence_is_validated_instead_of_blindly_persisted(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post_json("/__course_preview/evidence", {"pageOpened": True})

        self.assertEqual(caught.exception.code, 400)
        self.assertFalse((self.root / ".course-work" / "preview-manifest.json").exists())

    def test_prerequisites_fail_before_serving_missing_or_invalid_runtime(self):
        with self.assertRaises(ValueError):
            validate_preview_prerequisites(self.root, static_dir=self.root / "missing")

        (self.root / "course" / "course.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_preview_prerequisites(self.root, static_dir=self.static)


if __name__ == "__main__":
    unittest.main()
