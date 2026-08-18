import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.helpers import ROOT


class LocalEnvironmentTests(unittest.TestCase):
    def test_repository_ignores_local_secret_file_and_tracks_safe_example(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        example = (ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn("/.env", gitignore.splitlines())
        self.assertIn("OSS_ADMIN_KEY=", example)
        self.assertNotIn("oss-admin-", example)

    def test_course_env_loads_without_overriding_process_environment(self):
        from course_toolkit.local_env import load_local_env

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env").write_text(
                "# Local publication credential\n"
                "OSS_ADMIN_KEY=from-local-file\n"
                "COURSE_UNUSED='quoted value'\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"OSS_ADMIN_KEY": "from-process"}, clear=True):
                loaded = load_local_env(root / ".env")

                self.assertEqual(os.environ["OSS_ADMIN_KEY"], "from-process")
                self.assertEqual(os.environ["COURSE_UNUSED"], "quoted value")
                self.assertEqual(loaded, {"COURSE_UNUSED": "quoted value"})

    def test_missing_env_file_is_a_no_op(self):
        from course_toolkit.local_env import load_local_env

        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    load_local_env(Path(temporary) / ".env"),
                    {},
                )

    def test_publish_cli_loads_course_or_toolkit_env_before_api_client(self):
        script = (ROOT / "scripts" / "publish-course.py").read_text(encoding="utf-8")

        load_index = script.index("load_publication_env(args.root)")
        client_index = script.index("MindImprintAuthoringApi.from_environment")
        self.assertLess(load_index, client_index)


if __name__ == "__main__":
    unittest.main()
