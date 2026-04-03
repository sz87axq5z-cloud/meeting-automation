"""
図解用 HTML を Google Cloud Storage の公開バケットにアップロードし、共有用 https URL を返す。
認証は google-cloud-storage の既定（GOOGLE_APPLICATION_CREDENTIALS 等）に従う。
"""

from __future__ import annotations

import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)


def build_gcs_public_url(bucket_name: str, object_name: str) -> str:
    """https://storage.googleapis.com/BUCKET/OBJECT 形式（パスは安全にエンコード）。"""
    enc = quote(object_name, safe="/")
    return f"https://storage.googleapis.com/{bucket_name}/{enc}"


def upload_html_public_read(
    *,
    bucket_name: str,
    object_name: str,
    html_bytes: bytes,
    content_type: str = "text/html; charset=utf-8",
) -> str:
    """
    バイト列を GCS にアップロードする。
    公開 URL を返す（オブジェクト／バケット側で allUsers 等の公開設定は利用者が行う）。
    """
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(html_bytes, content_type=content_type)
    url = build_gcs_public_url(bucket_name, object_name)
    logger.info("gcs upload ok bucket=%s object=%s", bucket_name, object_name)
    return url
