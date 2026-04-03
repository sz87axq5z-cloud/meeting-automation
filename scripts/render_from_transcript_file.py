#!/usr/bin/env python3
"""
実録の文字起こしテキストから Claude 要約 → 要約 PNG を書き出す。

  cd meeting-automation
  .venv/bin/python scripts/render_from_transcript_file.py \\
    --transcript artifacts/fixtures/sample_real_mtg_transcript.txt \\
    -o artifacts/real_mtg_summary.png

tl;dv からエクスポートした .txt を渡してもよい（行頭が [mm:ss] 形式でなくても可）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.claude_processor import summarize_and_extract_tasks  # noqa: E402
from app.services.image_generator import render_summary_png  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="文字起こし → Claude → 要約 PNG")
    p.add_argument(
        "--transcript",
        type=Path,
        required=True,
        help="文字起こし全文のテキストファイル",
    )
    p.add_argument("--name", default="", help="会議名（空ならファイル名ベース）")
    p.add_argument(
        "--happened-at",
        default="",
        help="ISO 日時など（空なら未設定扱い）",
    )
    p.add_argument(
        "--participants",
        default="",
        help="カンマ区切り（例: 高橋,磯田）",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_ROOT / "artifacts" / "real_mtg_summary.png",
        help="出力 PNG パス",
    )
    args = p.parse_args()

    path = args.transcript.resolve()
    if not path.is_file():
        print(f"Not found: {path}", file=sys.stderr)
        return 1

    raw_transcript = path.read_text(encoding="utf-8").strip()
    if not raw_transcript:
        print("Transcript is empty.", file=sys.stderr)
        return 1

    name = (args.name or "").strip() or path.stem
    happened = (args.happened_at or "").strip() or None
    parts = [x.strip() for x in args.participants.split(",") if x.strip()]

    meeting_info: dict = {"name": name, "happened_at": happened or ""}
    if parts:
        meeting_info["participants"] = parts

    print("Calling Claude…", flush=True)
    result = summarize_and_extract_tasks(raw_transcript, meeting_info)
    summary = result.get("raw_text") or ""
    if not summary.strip():
        print("Claude returned empty text.", file=sys.stderr)
        return 1

    print("Rendering PNG…", flush=True)
    png = render_summary_png(meeting_info, summary)

    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"Wrote {out} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
