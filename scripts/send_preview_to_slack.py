#!/usr/bin/env python3
"""
プレビューと同じ内容で要約 PNG を生成し、Slack チャンネルへ files.upload v2 で投稿する。

  cd meeting-automation
  source .venv/bin/activate
  # .env に SLACK_BOT_TOKEN / SLACK_CHANNEL_ID を設定済みであること
  python scripts/send_preview_to_slack.py

オプション:
  --meeting-id ID   Slack 上のファイル名用（既定: local-preview-<unixtime>）
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(
        description="ダミー要約 PNG を生成して Slack に投稿（ローカル検証用）",
    )
    p.add_argument(
        "--meeting-id",
        default="",
        help="ファイル名 meeting_summary_<id>.png 用（空なら local-preview-<時刻>）",
    )
    args = p.parse_args()

    from slack_sdk.errors import SlackApiError

    from app.summary_preview_sample import SAMPLE_MEETING, SAMPLE_SUMMARY
    from app.services.image_generator import render_summary_png
    from app.services.slack_publisher import post_meeting_summary_png

    meeting_id = (args.meeting_id or "").strip() or f"local-preview-{int(time.time())}"

    print("Rendering PNG (same as render_summary_preview.py)...", flush=True)
    png = render_summary_png(SAMPLE_MEETING, SAMPLE_SUMMARY)
    print(f"PNG size: {len(png)} bytes", flush=True)

    print("Uploading to Slack...", flush=True)
    try:
        fid = post_meeting_summary_png(
            png_bytes=png,
            meeting_id=meeting_id,
            meeting_info=SAMPLE_MEETING,
        )
    except SlackApiError as e:
        print(f"Slack API error: {e.response}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"OK — file_id={fid!r} meeting_id={meeting_id!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
