import copy
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_package_validation import (
    iter_asset_references,
    validate_asset_references,
)
from course_toolkit.jsonio import load_json
from tests.helpers import ROOT


BASE = (
    ROOT
    / "tests"
    / "fixtures"
    / "course-blueprint"
    / "expected-course-definition.json"
)


def full_asset_document():
    data = load_json(BASE)
    course = data["course"]
    course["opening"]["fallback"]["audio"] = "assets/audio/open.mp3"
    course["closing"]["fallback"]["audio"] = "assets/audio/close.mp3"
    slice_data = course["parts"][0]["slices"][0]
    slice_data["blocks"].extend(
        [
            {
                "id": "diagram",
                "type": "images",
                "presentation": "single",
                "items": [
                    {
                        "id": "diagram-item",
                        "source": "assets/images/diagram.png",
                        "alt": "Diagram",
                    }
                ],
            },
            {
                "id": "source-paper",
                "type": "pdf",
                "title": "Source paper",
                "source": "assets/pdfs/source.pdf",
            },
            {
                "id": "case-video",
                "type": "video",
                "source": "assets/videos/case.mp4",
                "poster": "assets/images/case-poster.jpg",
                "captions": "assets/captions/case.en.vtt",
                "interaction": {"source": "interactions/video/case.json"},
            },
            {
                "id": "simulation",
                "type": "interactiveHtml",
                "source": "interactions/html/simulation.html",
                "protocolVersion": "1.0",
                "aspectRatio": "4:3",
            },
        ]
    )
    return data


EXPECTED = {
    "assets/audio/open.mp3",
    "assets/audio/close.mp3",
    "assets/audio/introduce-check.mp3",
    "assets/images/diagram.png",
    "assets/pdfs/source.pdf",
    "assets/videos/case.mp4",
    "assets/images/case-poster.jpg",
    "assets/captions/case.en.vtt",
    "interactions/video/case.json",
    "interactions/html/simulation.html",
}


class CoursePackageAssetTests(unittest.TestCase):
    def test_index_covers_every_asset_bearing_contract_field(self):
        references = list(iter_asset_references(full_asset_document()))

        self.assertEqual({reference.source for reference in references}, EXPECTED)
        self.assertEqual(
            {reference.role for reference in references},
            {
                "opening-audio",
                "closing-audio",
                "narration-audio",
                "image",
                "pdf",
                "video",
                "video-poster",
                "captions",
                "video-interaction",
                "interactive-html",
            },
        )
        video = next(item for item in references if item.role == "video")
        self.assertEqual(video.block_id, "case-video")
        self.assertEqual(video.slice_id, "slice-read-and-answer")
        self.assertIn("blocks[4].source", video.runtime_path)

    def test_complete_safe_inventory_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for raw in EXPECTED:
                path = root / raw
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"asset")
            result = validate_asset_references(
                root,
                full_asset_document(),
                sorted(EXPECTED),
            )

        self.assertEqual(result.issues, ())
        self.assertEqual([item.source for item in result.references], [
            item.source for item in iter_asset_references(full_asset_document())
        ])

    def test_missing_file_and_inventory_drift_are_distinct(self):
        data = full_asset_document()
        with tempfile.TemporaryDirectory() as temporary:
            result = validate_asset_references(
                Path(temporary),
                data,
                ["assets/unowned.bin", *sorted(EXPECTED - {"assets/images/diagram.png"})],
            )

        codes = [issue.code for issue in result.issues]
        self.assertIn("missing-asset", codes)
        self.assertEqual(codes.count("asset-inventory-mismatch"), 2)

    def test_unsafe_absolute_parent_and_backslash_paths_are_rejected(self):
        for source in ("/tmp/file.pdf", "../file.pdf", "assets\\file.pdf"):
            with self.subTest(source=source):
                data = full_asset_document()
                data["course"]["parts"][0]["slices"][0]["blocks"][3][
                    "source"
                ] = source
                with tempfile.TemporaryDirectory() as temporary:
                    result = validate_asset_references(Path(temporary), data, [])
                self.assertIn("unsafe-asset-path", {i.code for i in result.issues})

    def test_symlink_traversal_is_rejected_even_when_target_stays_inside_root(self):
        data = full_asset_document()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            (root / "assets").symlink_to(real, target_is_directory=True)

            result = validate_asset_references(root, data, sorted(EXPECTED))

        self.assertIn("symlink-asset-path", {issue.code for issue in result.issues})

    def test_case_mismatch_is_reported_deterministically(self):
        data = full_asset_document()
        source = "assets/images/diagram.png"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "assets" / "images" / "Diagram.PNG"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"image")

            result = validate_asset_references(root, data, sorted(EXPECTED))

        matching = [
            issue
            for issue in result.issues
            if issue.path.endswith("blocks[2].items[0].source")
        ]
        self.assertEqual(matching[0].code, "asset-case-mismatch")

    def test_role_extension_mismatch_is_rejected(self):
        data = full_asset_document()
        data["course"]["parts"][0]["slices"][0]["blocks"][3][
            "source"
        ] = "assets/pdfs/source.txt"

        with tempfile.TemporaryDirectory() as temporary:
            result = validate_asset_references(Path(temporary), data, [])

        self.assertIn("asset-extension-mismatch", {i.code for i in result.issues})


if __name__ == "__main__":
    unittest.main()
