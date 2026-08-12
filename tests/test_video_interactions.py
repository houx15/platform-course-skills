import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from course_toolkit.mp4 import inspect_mp4, read_mp4_duration
from course_toolkit.jsonio import dump_json, load_json
from course_toolkit.video_interactions import (
    inspect_video_interactions,
    render_video_interactions,
    validate_video_interactions,
)
from tests.helpers import ROOT, write_test_mp4


def valid_video_data():
    return {
        "schemaVersion": "1.0",
        "video": {
            "title": "示例视频",
            "source": "video_example.mp4",
            "durationSeconds": 32.533333,
            "events": [
                {
                    "id": "credibility-check",
                    "timeSeconds": 8,
                    "blocking": True,
                    "prompt": "视频内容一定可信吗？",
                    "interaction": {
                        "type": "singleChoice",
                        "options": [
                            {"id": "credible", "label": "可信"},
                            {"id": "not-credible", "label": "不可信"},
                        ],
                        "assessment": {"mode": "survey"},
                    },
                }
            ],
        },
    }


class VideoInteractionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.course_root = Path(self.temp_dir.name)
        self.probe_patch = patch(
            "course_toolkit.video_interactions._probe_with_ffprobe",
            return_value=None,
        )
        self.probe_patch.start()
        self.video_path = write_test_mp4(
            self.course_root / "video_example.mp4"
        )

    def tearDown(self):
        self.probe_patch.stop()
        self.temp_dir.cleanup()

    def codes(self, data):
        return {
            issue.code
            for issue in validate_video_interactions(data, self.course_root)
        }

    def test_reads_sample_mp4_duration(self):
        duration = read_mp4_duration(self.video_path)
        self.assertGreater(duration, 32)
        self.assertLess(duration, 33)

    def test_zero_duration_mp4_is_unverifiable(self):
        write_test_mp4(self.video_path, duration_seconds=0)
        self.assertIn("video-profile-unverified", self.codes(valid_video_data()))

    def test_inspects_h264_aac_faststart_profile(self):
        profile = inspect_mp4(self.video_path)
        self.assertEqual(profile.video_codecs, ("h264",))
        self.assertEqual(profile.audio_codecs, ("aac",))
        self.assertTrue(profile.faststart)
        self.assertGreater(profile.duration_seconds, 32)

    def test_accepts_silent_h264_video(self):
        path = write_test_mp4(
            self.course_root / "silent.mp4",
            audio_codec=None,
        )
        profile = inspect_mp4(path)
        self.assertEqual(profile.video_codecs, ("h264",))
        self.assertEqual(profile.audio_codecs, ())

    def test_reports_unsupported_video_audio_and_faststart(self):
        data = valid_video_data()
        write_test_mp4(
            self.video_path,
            video_codec=b"hvc1",
            audio_codec=b"ac-3",
            faststart=False,
        )
        codes = self.codes(data)
        self.assertIn("unsupported-video-codec", codes)
        self.assertIn("unsupported-audio-codec", codes)
        self.assertIn("missing-faststart", codes)

    def test_long_sparse_video_emits_nonblocking_warnings(self):
        data = valid_video_data()
        data["video"]["durationSeconds"] = 1200
        write_test_mp4(self.video_path, duration_seconds=1200)

        result = inspect_video_interactions(data, self.course_root)

        self.assertEqual(result.issues, ())
        codes = {warning.code for warning in result.warnings}
        self.assertIn("long-video", codes)
        self.assertIn("sparse-video-interactions", codes)

    def test_large_video_emits_nonblocking_warning(self):
        with self.video_path.open("r+b") as handle:
            handle.truncate(500 * 1024 * 1024 + 1)

        result = inspect_video_interactions(valid_video_data(), self.course_root)

        self.assertEqual(result.issues, ())
        self.assertIn("large-video", {warning.code for warning in result.warnings})

    def test_ffprobe_conflict_blocks_upload(self):
        probe = {
            "format_names": ("mov", "mp4"),
            "video_codecs": ("hevc",),
            "audio_codecs": ("aac",),
            "duration_seconds": 32.533333,
            "size_bytes": self.video_path.stat().st_size,
        }
        with patch(
            "course_toolkit.video_interactions._probe_with_ffprobe",
            return_value=probe,
        ):
            result = inspect_video_interactions(valid_video_data(), self.course_root)

        codes = {issue.code for issue in result.issues}
        self.assertIn("unsupported-video-codec", codes)
        self.assertIn("video-tool-conflict", codes)

    def test_cli_json_exposes_nonblocking_warnings(self):
        data = valid_video_data()
        data["video"]["durationSeconds"] = 1200
        write_test_mp4(self.video_path, duration_seconds=1200)
        data_path = self.course_root / "interactions.json"
        data_path.write_text(dump_json(data), encoding="utf-8")
        environment = os.environ.copy()
        environment["PATH"] = ""

        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "validate-video-interactions.py"),
                str(self.course_root),
                str(data_path),
                "--json",
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["valid"])
        self.assertIn("long-video", {warning["code"] for warning in payload["warnings"]})

    def test_valid_video_interactions_pass(self):
        self.assertEqual(
            validate_video_interactions(valid_video_data(), self.course_root),
            [],
        )

    def test_time_out_of_range_fails(self):
        data = valid_video_data()
        data["video"]["events"][0]["timeSeconds"] = 90
        self.assertIn("time-out-of-range", self.codes(data))

    def test_unordered_and_duplicate_times_fail(self):
        data = valid_video_data()
        second = copy.deepcopy(data["video"]["events"][0])
        second["id"] = "second-check"
        second["timeSeconds"] = 8
        data["video"]["events"].append(second)
        self.assertIn("time-conflict", self.codes(data))
        second["timeSeconds"] = 4
        self.assertIn("time-order", self.codes(data))

    def test_needs_timing_blocks(self):
        data = valid_video_data()
        event = data["video"]["events"][0]
        event["timeSeconds"] = None
        event["anchor"] = "关键论点之后"
        event["status"] = "needs-timing"
        self.assertIn("needs-timing", self.codes(data))

    def test_renderer_is_stable_and_readable(self):
        text = render_video_interactions(valid_video_data())
        self.assertTrue(text.startswith("# 示例视频\n"))
        self.assertIn("## 00:08", text)
        self.assertIn("视频内容一定可信吗？", text)
        self.assertIn("- 阻塞：是", text)
        self.assertIn("- 类型：singleChoice", text)
        self.assertIn("credible：可信", text)
        self.assertIn("- 评价模式：survey", text)
        self.assertTrue(text.endswith("\n"))

    def test_current_sample_fixture_exposes_90_second_error(self):
        data = load_json(
            ROOT / "tests" / "fixtures" / "sample-video-interactions.json"
        )
        issues = validate_video_interactions(data, self.course_root)
        codes_by_path = {(issue.path, issue.code) for issue in issues}
        self.assertNotIn(
            ("video.events[0].timeSeconds", "time-out-of-range"),
            codes_by_path,
        )
        self.assertIn(
            ("video.events[1].timeSeconds", "time-out-of-range"),
            codes_by_path,
        )


if __name__ == "__main__":
    unittest.main()
