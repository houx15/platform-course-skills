import json
import unittest

from tests.helpers import ROOT


class RuntimePinTests(unittest.TestCase):
    def test_runtime_pin_names_all_three_packages_and_tag(self):
        manifest = json.loads(
            (ROOT / "course-contract.snapshot.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["upstreamTag"], "course-authoring-v1.5.2")
        self.assertEqual(
            manifest["upstreamCommit"],
            "222fb2f28844dc5fc0851d4e5e8fc27f7399f0b9",
        )
        self.assertEqual(
            set(manifest["packages"]),
            {
                "@mind-imprint/course-contract",
                "@mind-imprint/course-runtime",
                "@mind-imprint/course-renderer",
            },
        )
        renderer = manifest["packages"]["@mind-imprint/course-renderer"]
        self.assertEqual(renderer["treeHash"], renderer["upstreamTreeHash"])
        self.assertNotIn("localPatches", renderer)
        self.assertTrue(
            (ROOT / "packages/course-renderer/src/blocks/media/PdfModal.tsx").is_file()
        )


if __name__ == "__main__":
    unittest.main()
