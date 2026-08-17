import json
import unittest

from tests.helpers import ROOT


class RuntimePinTests(unittest.TestCase):
    def test_runtime_pin_names_all_three_packages_and_tag(self):
        manifest = json.loads(
            (ROOT / "course-contract.snapshot.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["upstreamTag"], "course-authoring-v1.0.0")
        self.assertEqual(
            set(manifest["packages"]),
            {
                "@mind-imprint/course-contract",
                "@mind-imprint/course-runtime",
                "@mind-imprint/course-renderer",
            },
        )


if __name__ == "__main__":
    unittest.main()
