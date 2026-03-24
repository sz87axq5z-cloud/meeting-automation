#!/usr/bin/env python3
"""
.env の TRELLO_BOARD_ID から、そのボード上のリスト一覧と ID を表示する。
TRELLO_LIST_ID に誤ってボード ID を入れていると POST /cards が 404 になる。

  cd meeting-automation
  source .venv/bin/activate
  python scripts/show_trello_lists.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def normalize_trello_board_id(raw: str) -> str:
    """
    .env のよくあるミスを直す: 前後の空白・引用符、ボード URL 全体の貼り付け。
    API は「24 文字の id」または URL の /b/ 直後の shortLink を受け付ける。
    """
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    m = re.search(r"trello\.com/b/([a-zA-Z0-9]+)", s, re.IGNORECASE)
    if m:
        return m.group(1)
    return s


def main() -> int:
    import httpx

    from app.config import settings

    raw_board = settings.trello_board_id or ""
    board_id = normalize_trello_board_id(raw_board)
    if not board_id:
        print("TRELLO_BOARD_ID が .env にありません。", file=sys.stderr)
        return 1

    if raw_board.strip() != board_id:
        print(f"（注意: .env の値を次のように解釈しました → `{board_id}`）\n")

    params = {
        "key": settings.trello_api_key,
        "token": settings.trello_token,
        "filter": "open",
    }
    url = f"https://api.trello.com/1/boards/{board_id}/lists"
    try:
        r = httpx.get(url, params=params, timeout=60.0)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "")[:500]
        print(f"API エラー {e.response.status_code}: {body}", file=sys.stderr)
        if e.response.status_code == 400 and "invalid id" in body.lower():
            print(
                "\nヒント:\n"
                "  • TRELLO_BOARD_ID には「ボード」の識別子が必要です（リスト ID ではありません）。\n"
                "  • Trello でボードをブラウザで開き、URL が\n"
                "      https://trello.com/b/xxxxxxxx/ボード名\n"
                "    のとき、`xxxxxxxx` の部分だけを .env に書くか、URL 全体を貼ってもこのスクリプトで抜き出します。\n"
                "  • 24 文字の英数字（Trello が表示するボード id）でも OK です。\n"
                f"  • いま API に渡した値（先頭 40 文字）: {board_id[:40]!r}\n",
                file=sys.stderr,
            )
        return 1

    lists = r.json()
    if not isinstance(lists, list):
        print(json.dumps(lists, ensure_ascii=False, indent=2))
        return 0

    current = (settings.trello_list_id or "").strip()
    print(f"ボード ID: {board_id}\n")
    print("開いているリスト（.env の TRELLO_LIST_ID はこのどれかの「id」を使う）:\n")
    for item in lists:
        lid = item.get("id", "")
        name = item.get("name", "")
        mark = "  ← いま .env と一致" if lid == current else ""
        print(f"  name: {name}")
        print(f"  id:   {lid}{mark}")
        print()
    if current and not any(item.get("id") == current for item in lists):
        print(
            f"注意: いまの TRELLO_LIST_ID はこのボードのリストに含まれていません。\n"
            f"  .env の値: {current}\n",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
