import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from course_toolkit.mind_imprint_api import MindImprintApiError, MindImprintAuthoringApi


class FakeAuthoringHandler(BaseHTTPRequestHandler):
    records = []
    definition = None
    status = "preview"

    def log_message(self, format, *args):
        return

    def _json(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", "0")))

    def do_GET(self):
        type(self).records.append(("GET", self.path, self.headers.get("Authorization"), b""))
        if self.path == "/api/v1/admin/courses":
            self._json(200, {"courses": []})
        elif self.path.endswith("/missing/definition"):
            self._json(404, {"code": "not_found", "message": "课程不存在"})
        elif self.path.endswith("/demo/definition") and type(self).definition is not None:
            self._json(200, {"definition": type(self).definition, "hash": "a" * 64, "status": type(self).status})
        else:
            self._json(404, {"code": "not_found", "message": "课程不存在"})

    def do_POST(self):
        body = self._body()
        type(self).records.append(("POST", self.path, self.headers.get("Authorization"), body))
        if self.path.endswith("/asset-upload-url"):
            request = json.loads(body)
            self._json(200, {
                "putUrl": f"http://{self.server.server_address[0]}:{self.server.server_address[1]}/oss/{request['relativePath']}",
                "objectKey": f"courses/demo/{request['relativePath']}",
                "requiredContentType": request["contentType"],
                "maxBytes": 500_000_000,
                "expiresAt": "2026-08-17T14:00:00Z",
            })
        elif self.path.endswith("/ship"):
            type(self).status = "published"
            self._json(200, {"slug": "demo", "status": "published", "narrationsGenerated": 1})
        else:
            self._json(404, {"code": "not_found"})

    def do_PUT(self):
        body = self._body()
        type(self).records.append(("PUT", self.path, self.headers.get("Authorization"), body))
        if self.path.startswith("/oss/"):
            self.send_response(200)
            self.send_header("ETag", "etag-1")
            self.end_headers()
        elif self.path.endswith("/definition"):
            type(self).definition = json.loads(body)["definition"]
            self._json(200, {"slug": "demo", "status": type(self).status})
        else:
            self._json(404, {"code": "not_found"})


class MindImprintAuthoringApiTests(unittest.TestCase):
    def setUp(self):
        FakeAuthoringHandler.records = []
        FakeAuthoringHandler.definition = None
        FakeAuthoringHandler.status = "preview"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAuthoringHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.api = MindImprintAuthoringApi(f"http://{host}:{port}", "synthetic-test-key")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_bearer_discovery_write_upload_and_readback_contract(self):
        self.assertEqual(self.api.list_courses(), [])
        self.assertIsNone(self.api.get_course("missing"))
        plan = self.api.plan_asset_upload("demo", "assets/file.json", "application/json", 3)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "file.json"
            path.write_bytes(b"{}\n")
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("upload must stream")):
                self.assertEqual(self.api.upload_asset(plan["putUrl"], path, plan["requiredContentType"]), "etag-1")
        definition = {"schemaVersion": "2.0", "course": {"id": "demo"}}
        self.api.save_definition("demo", definition, blurb="Demo", card_ids=[])
        self.assertEqual(self.api.get_course("demo").definition, definition)
        self.api.ship("demo", cover="img:3")
        self.assertEqual(self.api.get_course("demo").status, "published")

        api_records = [record for record in FakeAuthoringHandler.records if not record[1].startswith("/oss/")]
        self.assertTrue(all(record[2] == "Bearer synthetic-test-key" for record in api_records))
        oss_record = next(record for record in FakeAuthoringHandler.records if record[1].startswith("/oss/"))
        self.assertIsNone(oss_record[2])
        self.assertEqual(oss_record[3], b"{}\n")

    def test_environment_factory_requires_key_without_echoing_it(self):
        previous = os.environ.pop("OSS_ADMIN_KEY", None)
        try:
            with self.assertRaisesRegex(MindImprintApiError, "not set"):
                MindImprintAuthoringApi.from_environment(api_base=self.api.api_base)
        finally:
            if previous is not None:
                os.environ["OSS_ADMIN_KEY"] = previous


if __name__ == "__main__":
    unittest.main()
