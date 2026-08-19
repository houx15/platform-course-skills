import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from course_toolkit.course_catalog import confirm_course_selection
from course_toolkit.course_cover import (
    CourseCoverError,
    confirm_cover_candidate,
    load_confirmed_cover,
    prepare_cover_candidate,
    register_cover_candidate,
)


NOW = "2026-08-20T00:00:00Z"


class CourseCoverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.candidate = self.root / ".course-work/cover-candidates/course-01.webp"
        self.candidate.parent.mkdir(parents=True)
        self.candidate.write_bytes(b"RIFF\x00\x00\x00\x00WEBPcandidate")
        self.selection = confirm_course_selection(
            self.root,
            "course-01",
            teacher_response="确认第一门课",
            confirmed_at=NOW,
        )

    def tearDown(self):
        self.temporary.cleanup()

    @mock.patch("course_toolkit.course_cover._probe_webp", return_value={"width": 1600, "height": 900})
    def test_candidate_is_16_by_9_webp_quality_100_and_teacher_confirmed(self, _probe):
        candidate = register_cover_candidate(
            self.root,
            self.candidate,
            prompt="A visual metaphor for evidence comparison",
            generator="imagegen2-subagent",
            quality=100,
            created_at=NOW,
        )
        self.assertEqual(candidate["width"], 1600)
        self.assertEqual(candidate["height"], 900)
        self.assertEqual(candidate["qualitySetting"], 100)
        self.assertFalse(candidate["teacherConfirmed"])

        confirmed = confirm_cover_candidate(
            self.root,
            teacher_response="确认采用这张封面。",
            confirmed_at=NOW,
        )
        loaded = load_confirmed_cover(self.root)

        self.assertEqual(loaded, confirmed)
        self.assertTrue(loaded["teacherConfirmed"])
        self.assertEqual(loaded["relativePath"], "cover/course-cover.webp")
        self.assertEqual(loaded["localPath"], ".course-work/cover-delivery/course-cover.webp")
        self.assertEqual(
            (self.root / ".course-work/cover-delivery/course-cover.webp").read_bytes(),
            self.candidate.read_bytes(),
        )
        self.assertEqual(loaded["catalogHash"], self.selection["catalogHash"])

    @mock.patch("course_toolkit.course_cover._probe_webp", return_value={"width": 1200, "height": 900})
    def test_non_16_by_9_candidate_is_rejected(self, _probe):
        with self.assertRaisesRegex(CourseCoverError, "16:9"):
            register_cover_candidate(
                self.root,
                self.candidate,
                prompt="Prompt",
                generator="imagegen2-subagent",
                quality=100,
                created_at=NOW,
            )

    @mock.patch("course_toolkit.course_cover._probe_webp", return_value={"width": 1600, "height": 900})
    def test_changed_delivery_copy_invalidates_confirmation(self, _probe):
        register_cover_candidate(
            self.root,
            self.candidate,
            prompt="Prompt",
            generator="imagegen2-subagent",
            quality=100,
            created_at=NOW,
        )
        confirm_cover_candidate(self.root, teacher_response="确认", confirmed_at=NOW)
        (self.root / ".course-work/cover-delivery/course-cover.webp").write_bytes(b"changed")

        with self.assertRaisesRegex(CourseCoverError, "changed"):
            load_confirmed_cover(self.root)

    @mock.patch("course_toolkit.course_cover._probe_image_dimensions", return_value={"width": 1600, "height": 900})
    @mock.patch("course_toolkit.course_cover._probe_webp", return_value={"width": 1600, "height": 900})
    def test_fixed_encoder_preserves_source_and_uses_quality_100(self, _probe_webp, _probe_source):
        source = self.root / ".course-work/cover-sources/imagegen-output.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"source-image-bytes")
        candidate = self.root / ".course-work/cover-candidates/encoded.webp"

        def encode(command, **_kwargs):
            self.assertIn("-q", command)
            self.assertEqual(command[command.index("-q") + 1], "100")
            self.assertIn("-metadata", command)
            candidate.write_bytes(b"RIFF\x00\x00\x00\x00WEBPencoded")
            return CompletedProcess(command, 0, "", "")

        with mock.patch("course_toolkit.course_cover.subprocess.run", side_effect=encode):
            record = prepare_cover_candidate(
                self.root,
                source,
                candidate,
                prompt="Prompt",
                created_at=NOW,
            )

        self.assertEqual(source.read_bytes(), b"source-image-bytes")
        self.assertEqual(record["qualitySetting"], 100)
        with self.assertRaisesRegex(CourseCoverError, "already exists"):
            prepare_cover_candidate(
                self.root,
                source,
                candidate,
                prompt="Prompt",
                created_at=NOW,
            )

    @mock.patch("course_toolkit.course_cover._probe_image_dimensions", return_value={"width": 1672, "height": 941})
    @mock.patch("course_toolkit.course_cover._probe_webp", return_value={"width": 1600, "height": 900})
    def test_near_16_by_9_imagegen_output_is_normalized_without_replacing_source(
        self, _probe_webp, _probe_source
    ):
        source = self.root / ".course-work/cover-sources/imagegen-output.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"source-image-bytes")
        candidate = self.root / ".course-work/cover-candidates/normalized.webp"

        def encode(command, **_kwargs):
            self.assertEqual(command[command.index("-resize") + 1 : command.index("-resize") + 3], ["1600", "900"])
            candidate.write_bytes(b"RIFF\x00\x00\x00\x00WEBPnormalized")
            return CompletedProcess(command, 0, "", "")

        with mock.patch("course_toolkit.course_cover.subprocess.run", side_effect=encode):
            record = prepare_cover_candidate(
                self.root,
                source,
                candidate,
                prompt="Prompt",
                created_at=NOW,
            )

        self.assertEqual(source.read_bytes(), b"source-image-bytes")
        self.assertEqual(record["sourceWidth"], 1672)
        self.assertEqual(record["sourceHeight"], 941)
        self.assertEqual(record["aspectNormalization"], "resize-1600x900")

    @mock.patch("course_toolkit.course_cover._probe_image_dimensions", return_value={"width": 1200, "height": 900})
    def test_far_from_16_by_9_source_requires_regeneration(self, _probe_source):
        source = self.root / ".course-work/cover-sources/portrait.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"source-image-bytes")
        candidate = self.root / ".course-work/cover-candidates/rejected.webp"

        with mock.patch("course_toolkit.course_cover.subprocess.run") as run:
            with self.assertRaisesRegex(CourseCoverError, "not close enough to 16:9"):
                prepare_cover_candidate(
                    self.root,
                    source,
                    candidate,
                    prompt="Prompt",
                    created_at=NOW,
                )

        run.assert_not_called()
        self.assertFalse(candidate.exists())

    @mock.patch("course_toolkit.course_cover._probe_image_dimensions", return_value={"width": 1600, "height": 900})
    @mock.patch("course_toolkit.course_cover._probe_webp", side_effect=CourseCoverError("invalid WebP"))
    def test_failed_candidate_validation_removes_only_new_candidate(self, _probe_webp, _probe_source):
        source = self.root / ".course-work/cover-sources/imagegen-output.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"source-image-bytes")
        candidate = self.root / ".course-work/cover-candidates/invalid.webp"

        def encode(command, **_kwargs):
            candidate.write_bytes(b"RIFF\x00\x00\x00\x00WEBPinvalid")
            return CompletedProcess(command, 0, "", "")

        with mock.patch("course_toolkit.course_cover.subprocess.run", side_effect=encode):
            with self.assertRaisesRegex(CourseCoverError, "invalid WebP"):
                prepare_cover_candidate(
                    self.root,
                    source,
                    candidate,
                    prompt="Prompt",
                    created_at=NOW,
                )

        self.assertEqual(source.read_bytes(), b"source-image-bytes")
        self.assertFalse(candidate.exists())


if __name__ == "__main__":
    unittest.main()
