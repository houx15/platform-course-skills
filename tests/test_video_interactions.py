import copy
import tempfile
import unittest
from pathlib import Path

from course_toolkit.mp4 import read_mp4_duration
from course_toolkit.jsonio import load_json
from course_toolkit.video_interactions import (
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
        self.video_path = write_test_mp4(
            self.course_root / "video_example.mp4"
        )

    def tearDown(self):
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
