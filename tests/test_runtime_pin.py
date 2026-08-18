import json
import unittest

from tests.helpers import ROOT


class RuntimePinTests(unittest.TestCase):
    def test_runtime_pin_names_all_three_packages_and_tag(self):
        manifest = json.loads(
            (ROOT / "course-contract.snapshot.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["upstreamTag"], "course-authoring-v1.2.0")
        self.assertEqual(
            manifest["upstreamCommit"],
            "3329e96ed632d40ca30b3f190294c1bf935c5ffa",
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
        self.assertNotEqual(renderer["treeHash"], renderer["upstreamTreeHash"])
        self.assertEqual(
            renderer["localPatches"],
            [
                {
                    "path": "src/layout/LayoutRenderer.tsx",
                    "reason": "Preserve v1.2.0 behavior while satisfying noUncheckedIndexedAccess.",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
