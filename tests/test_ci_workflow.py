import unittest

from tests.helpers import ROOT


class CIWorkflowTests(unittest.TestCase):
    def test_javascript_dependencies_are_installed_before_python_tests(self):
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
            encoding="utf-8"
        )

        required = (
            "actions/setup-node@v6",
            'node-version: "22"',
            "pnpm/action-setup@v6",
            "version: 10.29.3",
            "pnpm install --frozen-lockfile",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)

        setup_node = workflow.index("actions/setup-node@v6")
        setup_pnpm = workflow.index("pnpm/action-setup@v6")
        install_dependencies = workflow.index("pnpm install --frozen-lockfile")
        run_python_tests = workflow.index("python -m unittest discover -s tests -v")

        self.assertLess(setup_node, install_dependencies)
        self.assertLess(setup_pnpm, install_dependencies)
        self.assertLess(install_dependencies, run_python_tests)


if __name__ == "__main__":
    unittest.main()
