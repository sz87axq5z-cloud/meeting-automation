#!/usr/bin/env python3
"""
会議 ID で本番と同じパイプラインを1回実行する（手動テスト用）。

  tl;dv → Claude → 要約 PNG →（設定時）HTML を S3 に配置 → Trello → Slack
  PIPELINE_SKIP_TRELLO=1 で Trello を省略（Slack のみのテスト）

使い方:
  cd meeting-automation
  .venv/bin/python scripts/run_pipeline_for_meeting.py <tl;dv会議ID>

公開 HTML URL を Slack コメントに載せるには、.env に次を設定すること:
  • MEETING_HTML_S3_BUCKET
  • AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY（または IAM ロール）
  任意: MEETING_HTML_S3_PREFIX, MEETING_HTML_S3_REGION, MEETING_HTML_PUBLIC_BASE_URL

Upstash の重複防止が有効なとき、同一会議 ID は既に処理済みだと何もせず終了する。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")


def main() -> int:
    p = argparse.ArgumentParser(description="会議 ID で run_pipeline を実行（S3 HTML テスト可）")
    p.add_argument("meeting_id", help="tl;dv の会議 ID")
    p.add_argument(
        "--check-env",
        action="store_true",
        help="設定だけ表示して終了（API は呼ばない）",
    )
    args = p.parse_args()
    mid = (args.meeting_id or "").strip()
    if not mid:
        print("meeting_id が空です。", file=sys.stderr)
        return 2

    from app.config import settings

    bucket = (settings.meeting_html_s3_bucket or "").strip()
    region = (settings.meeting_html_s3_region or "ap-northeast-1").strip()
    base = (settings.meeting_html_public_base_url or "").strip() or (
        f"https://{bucket}.s3.{region}.amazonaws.com" if bucket else "(未設定)"
    )
    prefix = (settings.meeting_html_s3_prefix or "meetings").strip().strip("/")

    print("--- 要約 HTML（S3）設定 ---", flush=True)
    print(f"  MEETING_HTML_S3_BUCKET: {bucket or '(未設定 → HTML は Slack ファイルのみ)'}", flush=True)
    print(f"  MEETING_HTML_S3_PREFIX: {prefix}", flush=True)
    print(f"  MEETING_HTML_S3_REGION: {region}", flush=True)
    print(f"  公開 URL のベース: {base}", flush=True)
    if bucket:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", mid).strip("_")[:200] or "meeting"
        print(f"  想定オブジェクト URL 例: {base.rstrip('/')}/{prefix}/{safe}.html", flush=True)
    print("", flush=True)
    print("--- Trello ---", flush=True)
    print(
        f"  PIPELINE_SKIP_TRELLO: {getattr(settings, 'pipeline_skip_trello', False)}",
        flush=True,
    )
    print("", flush=True)

    if args.check_env:
        return 0

    from app.services.pipeline import run_pipeline

    print(f"run_pipeline 開始 meeting_id={mid}", flush=True)
    run_pipeline(mid)
    print("run_pipeline 終了（ログを確認してください）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
