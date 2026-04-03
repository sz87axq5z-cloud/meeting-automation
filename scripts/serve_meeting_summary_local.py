#!/usr/bin/env python3
"""
tl;dv 会議 ID から要約 HTML を生成し、ローカルで HTTP サーバを立ち上げて
ブラウザで開ける URL を標準出力する（本番 Slack / S3 は使わない）。

  cd meeting-automation
  .venv/bin/python scripts/serve_meeting_summary_local.py <会議ID>

同一 LAN の別端末から試す場合は --lan（0.0.0.0 で待ち受け）と、表示される PC の IP を使う。
インターネット全体に公開する URL が必要なら、このスクリプトのポートに ngrok などを当てる。

前提: .env に TLDV_API_KEY / ANTHROPIC_API_KEY（--summary-file 利用時は不要）
"""

from __future__ import annotations

import argparse
import functools
import http.server
import re
import socketserver
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")


def _safe_filename_id(meeting_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", (meeting_id or "").strip())
    return (s[:200] or "meeting").strip("_") or "meeting"


def _pick_lan_ip() -> str:
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "（この PC の IP を確認してください）"


def main() -> int:
    p = argparse.ArgumentParser(
        description="要約 HTML をローカル HTTP で公開 URL 表示（テスト用）",
    )
    p.add_argument(
        "meeting_id",
        nargs="?",
        default="",
        help="tl;dv の会議 ID（--summary-file 未使用時は必須）",
    )
    p.add_argument(
        "--summary-file",
        type=Path,
        default=None,
        help="Claude 要約の Markdown をファイルから読む（tl;dv / Anthropic を呼ばない）",
    )
    p.add_argument(
        "--name",
        default="ローカルテスト会議",
        help="--summary-file 時の会議名",
    )
    p.add_argument(
        "-p",
        "--port",
        type=int,
        default=0,
        help="待ち受けポート（0 で空きポート自動）",
    )
    p.add_argument(
        "--lan",
        action="store_true",
        help="0.0.0.0 で待ち受け（同一 Wi‑Fi などからアクセス可）",
    )
    args = p.parse_args()

    mid = (args.meeting_id or "").strip()
    if args.summary_file:
        path = args.summary_file.resolve()
        if not path.is_file():
            print(f"Not found: {path}", file=sys.stderr)
            return 1
        raw_md = path.read_text(encoding="utf-8")
        meeting_info: dict = {"name": args.name, "happened_at": "", "participants": []}
        file_key = _safe_filename_id(path.stem)
    else:
        if not mid:
            print(
                "会議 ID を渡すか、--summary-file で要約 Markdown を指定してください。",
                file=sys.stderr,
            )
            return 2
        import httpx

        from app.services.claude_processor import summarize_and_extract_tasks
        from app.services.tldv_client import fetch_meeting_context

        print(f"tl;dv 取得中… {mid}", flush=True)
        try:
            meeting_info, transcript = fetch_meeting_context(mid)
        except httpx.HTTPStatusError as e:
            print(f"HTTP {e.response.status_code}: {e.request.url}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"tl;dv 失敗: {e}", file=sys.stderr)
            return 1
        if not transcript.strip():
            print("文字起こしが空です。", file=sys.stderr)
            return 1
        print(f"Claude 要約中… ({len(transcript)} 文字)", flush=True)
        try:
            result = summarize_and_extract_tasks(transcript, meeting_info)
        except Exception as e:
            print(f"Claude 失敗: {e}", file=sys.stderr)
            return 1
        raw_md = result.get("raw_text") or ""
        if not raw_md.strip():
            print("要約が空です。", file=sys.stderr)
            return 1
        file_key = _safe_filename_id(mid)

    from app.services.summary_html import build_summary_html_document

    html_doc = build_summary_html_document(meeting_info, raw_md)

    out_dir = _ROOT / "artifacts" / "local_public_http"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"meeting_{file_key}.html"
    out_path = out_dir / out_name
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"書き出し: {out_path}", flush=True)

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(out_dir),
    )

    try:
        httpd = socketserver.TCPServer((host, args.port), handler)
    except OSError as e:
        print(f"サーバ起動失敗: {e}", file=sys.stderr)
        return 1

    httpd.allow_reuse_address = True
    _, bound_port = httpd.server_address[:2]

    loopback_url = f"http://127.0.0.1:{bound_port}/{out_name}"
    print("", flush=True)
    print("======== ローカル公開 URL（この PC のブラウザ用） ========", flush=True)
    print(loopback_url, flush=True)
    if args.lan:
        lip = _pick_lan_ip()
        print("", flush=True)
        print("======== 同一 LAN から（例・スマホ等） ========", flush=True)
        print(f"http://{lip}:{bound_port}/{out_name}", flush=True)
    print("", flush=True)
    print("停止: Ctrl+C", flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。", flush=True)
    finally:
        httpd.shutdown()
        httpd.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
