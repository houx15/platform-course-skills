import tempfile
import unittest
from pathlib import Path

from maintenance.catalog_cover_seed import (
    CatalogCoverSeedBlocked,
    build_cover_seed_plan,
    execute_cover_seed_plan,
)
from tests.helpers import ROOT


class FakeCoverSeedApi:
    def __init__(self, *, wrong_key=False):
        self.wrong_key = wrong_key
        self.uploads = []

    def plan_asset_upload(self, slug, relative_path, content_type, size):
        object_key = f"courses/{slug}/{relative_path}"
        if self.wrong_key:
            object_key = "courses/wrong/cover/course-cover.webp"
        return {
            "putUrl": f"https://oss.example.test/{slug}",
            "objectKey": object_key,
            "requiredContentType": content_type,
            "maxBytes": size,
        }

    def upload_asset(self, put_url, local_path, required_content_type):
        self.uploads.append((put_url, local_path, required_content_type))
        return "etag"


class CatalogCoverSeedingTests(unittest.TestCase):
    def test_plan_contains_all_fixed_keys_and_verified_source_bytes(self):
        plan = build_cover_seed_plan(ROOT)

        self.assertEqual(plan["schemaVersion"], "1.0")
        self.assertEqual(len(plan["entries"]), 33)
        self.assertEqual(
            [entry["slug"] for entry in plan["entries"]],
            [f"course-{number:02d}" for number in range(1, 34)],
        )
        self.assertTrue(all(entry["objectKey"] == f"courses/{entry['slug']}/cover/course-cover.webp" for entry in plan["entries"]))
        self.assertTrue(all((ROOT / entry["sourcePath"]).is_file() for entry in plan["entries"]))

    def test_execute_uploads_exactly_33_fixed_objects(self):
        api = FakeCoverSeedApi()
        result = execute_cover_seed_plan(ROOT, api)

        self.assertEqual(result, {"planned": 33, "uploaded": 33})
        self.assertEqual(len(api.uploads), 33)
        self.assertTrue(all(path.name.endswith(".webp") for _, path, _ in api.uploads))

    def test_execute_refuses_server_key_drift_before_upload(self):
        api = FakeCoverSeedApi(wrong_key=True)

        with self.assertRaisesRegex(CatalogCoverSeedBlocked, "object key"):
            execute_cover_seed_plan(ROOT, api)

        self.assertEqual(api.uploads, [])

    def test_plan_rejects_tampered_source_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "course_toolkit").mkdir()
            (root / "docs/course-covers-webp").mkdir(parents=True)
            (root / "course_toolkit/course_catalog.json").write_text(
                (ROOT / "course_toolkit/course_catalog.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            first_cover = build_cover_seed_plan(ROOT)["entries"][0]
            destination = root / first_cover["sourcePath"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"not-a-webp")

            with self.assertRaisesRegex(CatalogCoverSeedBlocked, "missing or changed"):
                build_cover_seed_plan(root)


if __name__ == "__main__":
    unittest.main()
