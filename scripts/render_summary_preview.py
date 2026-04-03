#!/usr/bin/env python3
"""
要約 PNG をローカルに書き出してビジュアル確認する（Slack には送らない）。

  cd meeting-automation && .venv/bin/python scripts/render_summary_preview.py -o /tmp/preview.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.summary_preview_sample import SAMPLE_MEETING, SAMPLE_SUMMARY  # noqa: E402
from app.services.image_generator import render_summary_png  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="要約 PNG プレビュー生成")
    p.add_argument(
        "-o",
        "--output",
        default=str(_ROOT / "artifacts" / "summary_preview.png"),
        help="出力 PNG パス",
    )
    args = p.parse_args()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    data = render_summary_png(SAMPLE_MEETING, SAMPLE_SUMMARY)
    out.write_bytes(data)
    print(f"Wrote {out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
