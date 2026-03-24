#!/usr/bin/env python3
"""
Trello にタスクカードが実際に作られるかだけを確認するスクリプト。
PNG・Slack は行わない（tl;dv → Claude → パース → Trello のみ）。

  cd meeting-automation
  source .venv/bin/activate
  python scripts/verify_trello_cards.py あなたのmeetingId

  # Trello に投げず、Claude 出力から何件タスクとして認識されるかだけ見る:
  python scripts/verify_trello_cards.py あなたのmeetingId --dry-run

  .env の TRELLO_ASSIGNEE_FILTER で担当者に絞ると、カードはその人分だけ作成される。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="tl;dv → Claude → Trello だけ実行してカード作成を検証")
    parser.add_argument("meeting_id", help="tl;dv の会議 ID")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Trello API は呼ばず、抽出タスクの一覧だけ表示",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from app.config import settings
    from app.services.claude_processor import summarize_and_extract_tasks
    from app.services.tldv_client import fetch_meeting_context
    from app.services.trello_client import (
        assignee_filter_terms,
        create_cards_for_tasks,
        filter_tasks_by_assignee,
        parse_tasks_from_claude_text,
    )

    mid = args.meeting_id.strip()
    terms = assignee_filter_terms()
    print(f"\n=== 会議 ID: {mid} ===")
    print(f"=== Trello 担当フィルタ: {terms if terms else '(未設定 → 全員のタスクがカード化)'} ===")
    print(f"    (.env の TRELLO_ASSIGNEE_FILTER / settings 値: {settings.trello_assignee_filter!r})\n")

    try:
        meeting_info, transcript = fetch_meeting_context(mid)
    except Exception as e:
        print(f"tl;dv の取得に失敗しました: {e}", file=sys.stderr)
        return 1

    if not transcript.strip():
        print("文字起こしが空です。文字起こし済みの会議 ID を使ってください。", file=sys.stderr)
        return 1

    print(f"文字起こし: {len(transcript)} 文字\n")

    try:
        result = summarize_and_extract_tasks(transcript, meeting_info)
    except Exception as e:
        print(f"Claude の処理に失敗しました: {e}", file=sys.stderr)
        return 1

    raw = result.get("raw_text") or ""
    print("--- Claude 出力（タスク一覧の見出し付近を確認）---")
    if "## タスク" in raw:
        i = raw.find("## タスク")
        print(raw[i : i + 2000])
    else:
        print("(「## タスク一覧」が見つかりません。全文の一部を表示します)")
        print(raw[:2500])
        if len(raw) > 2500:
            print("…")
    print("--- ここまで ---\n")

    tasks = parse_tasks_from_claude_text(raw)
    print(f"パースで認識したタスク: {len(tasks)} 件")
    for i, t in enumerate(tasks, 1):
        preview = t if len(t) <= 120 else t[:117] + "…"
        print(f"  {i}. {preview}")

    if not tasks:
        print(
            "\nタスクが 0 件のため Trello には何も作りません。\n"
            "Claude の出力に「## タスク一覧」と「1. 〜」形式の行があるか確認してください。",
            file=sys.stderr,
        )
        return 1

    if terms:
        n_after = len(filter_tasks_by_assignee(tasks))
        print(
            f"\n※ 担当フィルタ {terms!r} により、"
            f"Trello に作るのは {len(tasks)} 件中 {n_after} 件だけです。\n",
        )
        if n_after == 0:
            print("フィルタ後 0 件のため Trello には何も作りません。", file=sys.stderr)
            return 1

    if args.dry_run:
        print("\n--dry-run のため Trello には投稿していません。")
        return 0

    print("\nTrello にカードを作成しています…")
    try:
        urls = create_cards_for_tasks(tasks, mid, meeting_info)
    except Exception as e:
        print(f"Trello API で失敗しました: {e}", file=sys.stderr)
        return 1

    print(f"\n成功: {len(urls)} 枚のカードを作成しました。\n")
    for i, u in enumerate(urls, 1):
        print(f"  {i}. {u}")
    print("\n上の URL をブラウザで開いてボード上のカードを確認してください。\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
