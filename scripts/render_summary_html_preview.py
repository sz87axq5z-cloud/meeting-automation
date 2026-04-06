#!/usr/bin/env python3
"""
要約HTML（縦スクロール図解）をローカルに書き出す。Claude / API は使わない。

  cd meeting-automation && .venv/bin/python scripts/render_summary_html_preview.py -o artifacts/my.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.summary_html import build_summary_html_document  # noqa: E402
from app.summary_preview_sample import SAMPLE_MEETING, SAMPLE_SUMMARY  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="要約HTML（図解）プレビュー生成")
    p.add_argument(
        "-o",
        "--output",
        default=str(_ROOT / "artifacts" / "summary_html_preview.html"),
        help="出力 HTML パス",
    )
    p.add_argument(
        "-f",
        "--from-markdown",
        type=Path,
        help="このファイルの内容を要約Markdownとして使う（省略時はサンプル要約）",
    )
    args = p.parse_args()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    raw = (
        args.from_markdown.read_text(encoding="utf-8")
        if args.from_markdown
        else SAMPLE_SUMMARY
    )
    html = build_summary_html_document(SAMPLE_MEETING, raw)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({len(html)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
