#!/usr/bin/env python3
"""
既存の平文図解 HTML を読み、パスワード保護にして保存し、任意で GCS にアップロードする。
Claude / tl;dv は不要（GCS・Slack の動作確認用）。

  cd meeting-automation
  .venv/bin/python scripts/publish_infographic_html_from_file.py artifacts/meeting_xxx.html

  # GCS をスキップ（暗号化ファイルと .password.txt のみ）
  .venv/bin/python scripts/publish_infographic_html_from_file.py page.html --no-gcs

  # パスワードを自分で指定
  .venv/bin/python scripts/publish_infographic_html_from_file.py page.html --password 'my-secret'

  # GCS 後に Slack にも流す（.env の SLACK_* と任意で INFOGRAPHIC_SLACK_CHANNEL_ID）
  .venv/bin/python scripts/publish_infographic_html_from_file.py page.html --post-slack

前提: .env に GOOGLE_APPLICATION_CREDENTIALS（GCS 使うとき）。バケットは INFOGRAPHIC_GCS_BUCKET または --bucket。
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")


def main() -> int:
    p = argparse.ArgumentParser(
        description="既存HTMLを暗号化し、任意でGCSアップロード（API不要）",
    )
    p.add_argument(
        "html_file",
        type=Path,
        help="平文の図解HTMLファイル",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="暗号化後HTMLの保存先（省略時は入力と同じフォルダに <stem>_encrypted.html）",
    )
    p.add_argument(
        "--password",
        default="",
        help="省略時はランダム生成（.password.txt に保存）",
    )
    p.add_argument(
        "--no-gcs",
        action="store_true",
        help="GCS にアップロードしない",
    )
    p.add_argument(
        "--bucket",
        default="",
        help="GCS バケット名（省略時は .env の INFOGRAPHIC_GCS_BUCKET）",
    )
    p.add_argument(
        "--prefix",
        default="",
        help="オブジェクト接頭辞（省略時は .env の INFOGRAPHIC_GCS_PREFIX、通常 infographics）",
    )
    p.add_argument(
        "--post-slack",
        action="store_true",
        help="アップロード後に公開URLとパスワードを Slack に投稿する",
    )
    p.add_argument(
        "--meeting-name",
        default="ローカルテスト（既存HTML）",
        help="Slack 表示用の会議名",
    )
    args = p.parse_args()

    src = args.html_file.resolve()
    if not src.is_file():
        print(f"ファイルがありません: {src}", file=sys.stderr)
        return 1

    plain = src.read_text(encoding="utf-8")
    if not plain.strip():
        print("HTML が空です。", file=sys.stderr)
        return 1

    password = (args.password or "").strip()
    if not password:
        password = secrets.token_urlsafe(24)

    from app.services.infographic_password_html import encrypt_plain_html_to_password_gate

    try:
        encrypted = encrypt_plain_html_to_password_gate(plain, password)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2

    out_path = args.output
    if out_path is None:
        out_path = src.parent / f"{src.stem}_encrypted.html"
    else:
        out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(encrypted, encoding="utf-8")

    pw_path = out_path.with_name(out_path.stem + ".password.txt")
    pw_path.write_text(password + "\n", encoding="utf-8")

    print(f"暗号化HTMLを保存: {out_path}", flush=True)
    print(f"パスワードを保存: {pw_path}", flush=True)

    if args.no_gcs:
        print("（--no-gcs のため GCS はスキップ）", flush=True)
        return 0

    from app.config import settings

    bucket = (args.bucket or "").strip() or (settings.infographic_gcs_bucket or "").strip()
    if not bucket:
        print(
            "GCS バケットが未設定です。INFOGRAPHIC_GCS_BUCKET を .env に入れるか --bucket を指定してください。",
            file=sys.stderr,
        )
        return 1

    prefix = (args.prefix or "").strip()
    if not prefix:
        prefix = (settings.infographic_gcs_prefix or "").strip().strip("/")

    stem_safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", src.stem).strip("_")[:120] or "page"
    rand = secrets.token_hex(8)
    if prefix:
        object_name = f"{prefix}/{rand}_{stem_safe}.html"
    else:
        object_name = f"{rand}_{stem_safe}.html"

    from app.services.infographic_gcs import upload_html_public_read

    try:
        public_url = upload_html_public_read(
            bucket_name=bucket,
            object_name=object_name,
            html_bytes=encrypted.encode("utf-8"),
        )
    except Exception as e:
        print(f"GCS アップロードに失敗: {e}", file=sys.stderr)
        return 1

    print(f"公開URL: {public_url}", flush=True)

    if args.post_slack:
        from app.services.slack_publisher import post_infographic_gcs_share_notice

        channel = settings.infographic_slack_channel_id or settings.slack_channel_id
        meeting_info = {"name": args.meeting_name}
        ok = post_infographic_gcs_share_notice(
            meeting_id=f"local-{stem_safe[:40]}",
            meeting_info=meeting_info,
            public_url=public_url,
            password=password,
            channel_id=channel,
        )
        if not ok:
            print("Slack 投稿に失敗しました。", file=sys.stderr)
        else:
            print("Slack に投稿しました。", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
