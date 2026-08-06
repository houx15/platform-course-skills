from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT


def minimal_course():
    return {
        "schemaVersion": "1.0",
        "course": {
            "id": "sample-course",
            "title": "样例课程",
            "language": "zh-CN",
            "parts": [
                {
                    "id": "part-1",
                    "title": "第一部分",
                    "pieces": [
                        {
                            "id": "piece-1",
                            "title": "第一内容块",
                            "blocks": [
                                {
                                    "id": "intro",
                                    "type": "text",
                                    "content": "课程内容",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    }
