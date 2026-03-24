#!/usr/bin/env python3
"""
tl;dv Public API で会議一覧を取得して表示する。
meeting-automation ディレクトリで .env を置き、ここから実行する。

  cd meeting-automation
  source .venv/bin/activate
  python scripts/list_tldv_meetings.py

文字起こしがある会議だけ（各会議に transcript API を1回ずつ叩く）:

  python scripts/list_tldv_meetings.py --only-with-transcript --scan-all-pages --ids-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _collect_meetings(
    *,
    page: int,
    page_size: int,
    meeting_type: str | None,
    scan_all_pages: bool,
    max_pages: int,
) -> tuple[dict, list[dict]]:
    """一覧 API を呼び、(最後に取得した raw, results のリスト) を返す。"""
    import httpx

    from app.services.tldv_client import list_meetings

    if not scan_all_pages:
        data = list_meetings(page=page, page_size=page_size, meeting_type=meeting_type)
        return data, list(data.get("results") or [])

    combined: list[dict] = []
    last: dict = {}
    p = 1
    while p <= max_pages:
        data = list_meetings(page=p, page_size=page_size, meeting_type=meeting_type)
        last = data
        batch = list(data.get("results") or [])
        if not batch:
            break
        combined.extend(batch)
        total_pages = data.get("pages")
        if total_pages is not None:
            try:
                if p >= int(total_pages):
                    break
            except (TypeError, ValueError):
                pass
        p += 1
    return last, combined


def main() -> int:
    parser = argparse.ArgumentParser(description="tl;dv GET /v1alpha1/meetings で会議 ID を確認")
    parser.add_argument("--page", type=int, default=1, help="ページ番号（API は 1 始まり）。--scan-all-pages 未指定時のみ有効")
    parser.add_argument("--page-size", type=int, default=50, dest="page_size")
    parser.add_argument(
        "--meeting-type",
        type=str,
        default=None,
        metavar="TYPE",
        help="API の meetingType フィルタ（例: internal / external）",
    )
    parser.add_argument("--json", action="store_true", help="一覧 API のレスポンス全文を JSON で出力（フィルタ未使用時）")
    parser.add_argument(
        "--only-with-transcript",
        action="store_true",
        help="各会議の transcript エンドポイントで確認し、本文があるものだけ残す",
    )
    parser.add_argument(
        "--scan-all-pages",
        action="store_true",
        help="1 ページ目から最大 --max-pages まで一覧を結合してからフィルタ（--only-with-transcript と併用推奨）",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=30,
        help="--scan-all-pages 時の最大ページ数（安全のため上限）",
    )
    parser.add_argument(
        "--ids-only",
        action="store_true",
        help="会議 id のみ 1 行ずつ出力（--only-with-transcript と併用が主用途）",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="チェック中の meeting id を stderr に出す")
    args = parser.parse_args()

    import httpx

    from app.services.tldv_client import get_transcript_text_if_available

    try:
        data, results = _collect_meetings(
            page=args.page,
            page_size=args.page_size,
            meeting_type=args.meeting_type,
            scan_all_pages=args.scan_all_pages,
            max_pages=args.max_pages,
        )
    except httpx.HTTPStatusError as e:
        print(f"HTTP {e.response.status_code}: {e.request.url}", file=sys.stderr)
        print(e.response.text, file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json and not args.only_with_transcript:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.only_with_transcript:
        with_transcript: list[dict] = []
        for m in results:
            mid = m.get("id")
            if not mid:
                continue
            if args.verbose:
                print(f"… transcript 確認: {mid}", file=sys.stderr)
            try:
                text = get_transcript_text_if_available(str(mid))
            except httpx.HTTPStatusError as e:
                print(f"HTTP {e.response.status_code} meeting={mid}: {e.response.text[:200]}", file=sys.stderr)
                return 1
            if text is not None:
                with_transcript.append(m)

        if args.ids_only:
            for m in with_transcript:
                print(m.get("id", ""))
            print(f"# {len(with_transcript)} meeting(s) with transcript", file=sys.stderr)
            return 0

        if args.json:
            out = [
                {
                    "id": m.get("id"),
                    "name": m.get("name"),
                    "happenedAt": m.get("happenedAt"),
                    "url": m.get("url"),
                }
                for m in with_transcript
            ]
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0

        print(
            f"文字起こしあり: {len(with_transcript)} 件 "
            f"（候補 {len(results)} 件をチェック）\n",
            file=sys.stderr,
        )
        for m in with_transcript:
            mid = m.get("id", "?")
            name = m.get("name", "（無題）")
            happened = m.get("happenedAt", "")
            print(f"id: {mid}")
            print(f"  name:       {name}")
            print(f"  happenedAt: {happened}")
            url = m.get("url")
            if url:
                print(f"  url:        {url}")
            print()
        return 0

    total = data.get("total")
    page = data.get("page", args.page)
    pages = data.get("pages", "?")
    print(f"total={total}  page={page}/{pages}  このページの件数={len(results)}\n")
    for m in results:
        mid = m.get("id", "?")
        name = m.get("name", "（無題）")
        happened = m.get("happenedAt", "")
        print(f"id: {mid}")
        print(f"  name:       {name}")
        print(f"  happenedAt: {happened}")
        url = m.get("url")
        if url:
            print(f"  url:        {url}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
