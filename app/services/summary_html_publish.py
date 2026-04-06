"""
要約 HTML を GCS または S3 に置き、HTTPS の公開 URL を返す（任意設定時のみ）。
GCS（MEETING_HTML_GCS_BUCKET）が設定されていればそちらを優先する。
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from app.config import settings

logger = logging.getLogger(__name__)


def _safe_object_key_segment(meeting_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", (meeting_id or "").strip())
    return (s[:200] or "meeting").strip("_") or "meeting"


def _object_key_for_meeting(meeting_id: str, prefix_setting: str) -> str:
    prefix = (prefix_setting or "meetings").strip().strip("/")
    return f"{prefix}/{_safe_object_key_segment(meeting_id)}.html"


def _public_url_with_optional_base(*, base: str | None, key: str, default_url: str) -> str:
    b = (base or "").strip().rstrip("/")
    if not b:
        return default_url
    enc = quote(key, safe="/")
    return f"{b}/{enc}"


def publish_summary_html(*, html_bytes: bytes, meeting_id: str) -> str | None:
    """
    `MEETING_HTML_GCS_BUCKET` または `MEETING_HTML_S3_BUCKET` が設定されているときだけ
    アップロードし、閲覧用 URL を返す。未設定・失敗時は None（PNG / Slack は継続可）。

    GCS: google-cloud-storage（GOOGLE_APPLICATION_CREDENTIALS 等）。
    S3: boto3（AWS 標準環境変数）。
    """
    gcs_bucket = (settings.meeting_html_gcs_bucket or "").strip()
    if gcs_bucket:
        key = _object_key_for_meeting(meeting_id, settings.meeting_html_gcs_prefix)
        try:
            from app.services.infographic_gcs import upload_html_public_read
        except ImportError:
            logger.error(
                "summary html GCS publish skipped: google-cloud-storage not installed"
            )
            return None

        try:
            default_url = upload_html_public_read(
                bucket_name=gcs_bucket,
                object_name=key,
                html_bytes=html_bytes,
            )
        except Exception as e:
            logger.exception(
                "GCS upload failed for summary html meeting_id=%s: %s",
                meeting_id,
                e,
            )
            return None

        url = _public_url_with_optional_base(
            base=settings.meeting_html_public_base_url,
            key=key,
            default_url=default_url,
        )
        logger.info("summary html published (GCS) meeting_id=%s url=%s", meeting_id, url)
        return url

    bucket = (settings.meeting_html_s3_bucket or "").strip()
    if not bucket:
        return None

    key = _object_key_for_meeting(meeting_id, settings.meeting_html_s3_prefix)

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

    default_base = f"https://{bucket}.s3.{region}.amazonaws.com"
    base = (settings.meeting_html_public_base_url or "").strip().rstrip("/")
    if not base:
        base = default_base
    url = f"{base}/{key}"
    logger.info("summary html published (S3) meeting_id=%s url=%s", meeting_id, url)
    return url
