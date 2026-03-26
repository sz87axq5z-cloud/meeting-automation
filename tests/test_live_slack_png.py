"""
実 Slack への投稿検証（任意）。

  MEETING_AUTOMATION_LIVE_SLACK=1 .venv/bin/python -m unittest tests.test_live_slack_png

要: .env に SLACK_BOT_TOKEN / SLACK_CHANNEL_ID が有効な値。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@unittest.skipUnless(
    os.environ.get("MEETING_AUTOMATION_LIVE_SLACK") == "1",
    "set MEETING_AUTOMATION_LIVE_SLACK=1 to run",
)
class TestLiveSlackPng(unittest.TestCase):
    def test_post_summary_png_to_slack(self) -> None:
        from app.services.image_generator import render_summary_png
        from app.services.slack_publisher import post_meeting_summary_png

        meeting = {
            "name": "[自動テスト] 要約PNG",
            "happened_at": "2026-03-24",
            "participants": [],
        }
        summary = (
            "## 確認\n"
            "MEETING_AUTOMATION_LIVE_SLACK=1 での実投稿テストです。\n\n"
            "## タスク一覧\n"
            "1. **Bot** - このメッセージを確認 - 期限未定"
        )
        png = render_summary_png(meeting, summary, width=1080)
        self.assertTrue(png.startswith(b"\x89PNG"))

        fid = post_meeting_summary_png(
            png_bytes=png,
            meeting_id="live-test-png",
            meeting_info=meeting,
        )
        self.assertIsNotNone(fid)


if __name__ == "__main__":
    unittest.main()
