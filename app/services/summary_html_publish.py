"""
要約 HTML を S3 に置き、HTTPS の公開 URL を返す（任意設定時のみ）。
"""

from __future__ import annotations

import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)


def _safe_object_key_segment(meeting_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", (meeting_id or "").strip())
    return (s[:200] or "meeting").strip("_") or "meeting"


def publish_summary_html(*, html_bytes: bytes, meeting_id: str) -> str | None:
    """
    `MEETING_HTML_S3_BUCKET` が設定されているときだけアップロードし、閲覧用 URL を返す。
    未設定・失敗時は None（PNG / Slack は継続可）。

    認証: 標準の AWS 環境変数を boto3 が解釈。
    バケットは公開読み取りポリシー、または MEETING_HTML_PUBLIC_BASE_URL で CloudFront 等を指定。
    """
    bucket = (settings.meeting_html_s3_bucket or "").strip()
    if not bucket:
        return None

    prefix = (settings.meeting_html_s3_prefix or "meetings").strip().strip("/")
    key = f"{prefix}/{_safe_object_key_segment(meeting_id)}.html"

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        logger.error(
            "summary html publish skipped: boto3 not installed (pip install boto3)"
        )
        return None

    region = (settings.meeting_html_s3_region or "ap-northeast-1").strip()
    client = boto3.client("s3", region_name=region)

    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=html_bytes,
            ContentType="text/html; charset=utf-8",
            CacheControl="public, max-age=300",
        )
    except (ClientError, BotoCoreError) as e:
        logger.exception(
            "S3 put_object failed for summary html meeting_id=%s: %s",
            meeting_id,
            e,
        )
        return None

    base = (settings.meeting_html_public_base_url or "").strip().rstrip("/")
    if not base:
        base = f"https://{bucket}.s3.{region}.amazonaws.com"

    url = f"{base}/{key}"
    logger.info("summary html published meeting_id=%s url=%s", meeting_id, url)
    return url
