import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_package_validation import (
    build_course_validation_report,
    sync_validation_issues,
    write_current_validation_report,
)
from course_toolkit.publication import (
    ASSET_MANIFEST_RELATIVE_PATH,
    build_asset_manifest,
    write_asset_manifest,
)
from course_toolkit.workflow import new_session, save_session
from tests.helpers import ROOT
from tests.test_course_package_validation import build_full_package, build_minimal_package


NOW = "2026-08-16T00:00:00Z"


def prepare_g6(root: Path, *, full: bool = False):
    if full:
        build_full_package(root)
    else:
        build_minimal_package(root)
    report = build_course_validation_report(root)
    write_current_validation_report(root, report)
    sync_validation_issues(root, report, NOW)
    return report


class AssetManifestTests(unittest.TestCase):
    def test_manifest_excludes_server_generated_audio_and_keeps_delivery_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = prepare_g6(root, full=True)

            manifest = build_asset_manifest(root, "course-local-a")

        self.assertFalse(
            any("narration-audio" in entry["roles"] for entry in manifest["entries"])
        )
        self.assertEqual(
            {entry["sha256"] for entry in manifest["entries"]},
            {asset["sha256"] for asset in report["assets"]},
        )
        for entry in manifest["entries"]:
            self.assertEqual(entry["state"], "upload-required")
            self.assertTrue(
                entry["objectKey"].startswith("courses/course-local-a/assets/")
            )
            self.assertEqual(entry["sources"], sorted(entry["sources"]))
            self.assertEqual(entry["runtimePaths"], sorted(entry["runtimePaths"]))

    def test_matching_verified_remote_record_is_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_g6(root, full=True)
            first = build_asset_manifest(root, "course-local-a")
            prior = copy.deepcopy(first)
            entry = prior["entries"][0]
            entry["state"] = "reusable"
            entry["remote"] = {
                "objectKey": entry["objectKey"],
                "uploadedSha256": entry["sha256"],
                "etag": "etag-1",
                "verifiedAt": NOW,
            }

            second = build_asset_manifest(
                root,
                "course-local-a",
                previous_manifest=prior,
            )

        self.assertEqual(second["entries"][0]["state"], "reusable")
        self.assertEqual(second["entries"][0]["remote"], entry["remote"])

    def test_mismatched_remote_hash_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_g6(root, full=True)
            prior = build_asset_manifest(root, "course-local-a")
            prior["entries"][0]["remote"] = {
                "objectKey": prior["entries"][0]["objectKey"],
                "uploadedSha256": "0" * 64,
                "etag": "stale",
                "verifiedAt": NOW,
            }

            rebuilt = build_asset_manifest(
                root,
                "course-local-a",
                previous_manifest=prior,
            )

        self.assertEqual(rebuilt["entries"][0]["state"], "upload-required")
        self.assertIsNone(rebuilt["entries"][0]["remote"])

    def test_unreferenced_files_are_observed_but_zip_is_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_g6(root)
            unused = root / "course/assets/images/unused.png"
            unused.parent.mkdir(parents=True, exist_ok=True)
            unused.write_bytes(b"unused")
            (root / "course/assets/archive.zip").write_bytes(b"zip")

            manifest = build_asset_manifest(root, "course-local-a")

        self.assertEqual(manifest["localOnlyPaths"], ["assets/images/unused.png"])

    def test_manifest_is_deterministic_across_absolute_roots(self):
        manifests = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                prepare_g6(root)
                manifests.append(build_asset_manifest(root, "course-local-a"))

        self.assertEqual(manifests[0], manifests[1])

    def test_write_manifest_uses_canonical_work_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_g6(root)
            manifest = build_asset_manifest(root, "course-local-a")

            output = write_asset_manifest(root, manifest)

        self.assertEqual(output, root.resolve() / ASSET_MANIFEST_RELATIVE_PATH)


class AssetManifestCliTests(unittest.TestCase):
    def test_cli_uses_session_identity_and_never_contacts_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "course"
            root.mkdir()
            prepare_g6(root)
            save_session(root, new_session("course-local-a", [], NOW))

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/prepare-publication.py"),
                    "manifest",
                    str(root),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["manifest"]["courseLocalId"], "course-local-a")
        self.assertTrue(payload["output"].endswith("asset-manifest.json"))


if __name__ == "__main__":
    unittest.main()
