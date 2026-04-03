#!/usr/bin/env python3
"""
tl;dv の会議 ID で API から文字起こしを取り、Claude 要約 → 議事図解 PNG をローカルに保存する。
Slack・Trello・Webhook パイプラインは呼ばない（本番と同じ要約・描画ロジックのみ）。

前提:
  meeting-automation/.env に TLDV_API_KEY / ANTHROPIC_API_KEY など（既存プロジェクトと同じ）

会議 ID の渡し方（どちらか）:
  1) 環境変数 TLDV_TEST_MEETING_ID に会議 ID を書く
  2) 第1引数に会議 ID を渡す（引数が優先）

例:
  cd meeting-automation
  # .env に TLDV_TEST_MEETING_ID=... を書いても可（このスクリプトが読み込む）
  export TLDV_TEST_MEETING_ID='あなたの会議ID'
  .venv/bin/python scripts/render_from_tldv_meeting.py

  .venv/bin/python scripts/render_from_tldv_meeting.py 'あなたの会議ID' -o artifacts/my_mtg.png
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# .env の TLDV_TEST_MEETING_ID を export なしで使えるようにする
load_dotenv(_ROOT / ".env")


def main() -> int:
    p = argparse.ArgumentParser(
        description="tl;dv 会議 ID → Claude → 要約 PNG（ローカルのみ）",
    )
    p.add_argument(
        "meeting_id",
        nargs="?",
        default="",
        help="tl;dv の会議 ID（省略時は環境変数 TLDV_TEST_MEETING_ID）",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_ROOT / "artifacts" / "tldv_meeting_diagram.png",
        help="出力 PNG パス",
    )
    args = p.parse_args()

    mid = (args.meeting_id or "").strip() or (
        os.environ.get("TLDV_TEST_MEETING_ID") or ""
    ).strip()
    if not mid:
        print(
            "会議 ID が必要です。次のいずれかで指定してください:\n"
            "  • 引数: python scripts/render_from_tldv_meeting.py <会議ID>\n"
            "  • meeting-automation/.env に TLDV_TEST_MEETING_ID=<会議ID>\n"
            "  • 環境変数: export TLDV_TEST_MEETING_ID=<会議ID>",
            file=sys.stderr,
        )
        return 2

    from app.services.claude_processor import summarize_and_extract_tasks
    from app.services.image_generator import render_summary_png
    from app.services.tldv_client import fetch_meeting_context

    print(f"tl;dv 取得中… meeting_id={mid}", flush=True)
    try:
        meeting_info, transcript = fetch_meeting_context(mid)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            print(
                "tl;dv が 401 Unauthorized を返しました（API キーが通っていません）。\n"
                "  • meeting-automation/.env の TLDV_API_KEY を確認してください。\n"
                "  • 入れるのは tl;dv の「Public API 用」キーです（アプリ左下の自分のアイコン → "
                "Settings → Personal settings → API keys で発行）。\n"
                "  • WEBHOOK_SECRET や Slack のトークンなど、別の値を入れていると 401 になります。\n"
                "  • キーを作り直したら .env を保存し、ターミナルを開き直すかそのシェルで再実行してください。",
                file=sys.stderr,
            )
        print(f"HTTP {e.response.status_code}: {e.request.url}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"tl;dv の取得に失敗しました: {e}", file=sys.stderr)
        return 1

    if not transcript.strip():
        print(
            "文字起こしが空です。文字起こし済みの会議 ID を使ってください。",
            file=sys.stderr,
        )
        return 1

    print(f"文字起こし: {len(transcript)} 文字。Claude 呼び出し中…", flush=True)
    try:
        result = summarize_and_extract_tasks(transcript, meeting_info)
    except Exception as e:
        print(f"Claude の処理に失敗しました: {e}", file=sys.stderr)
        return 1

    summary = result.get("raw_text") or ""
    if not summary.strip():
        print("Claude が空の要約を返しました。", file=sys.stderr)
        return 1

    print("PNG 描画中…", flush=True)
    try:
        png = render_summary_png(meeting_info, summary)
    except Exception as e:
        print(f"PNG の生成に失敗しました: {e}", file=sys.stderr)
        return 1

    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"保存しました: {out} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
