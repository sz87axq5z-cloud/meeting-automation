"""
tl;dv Webhook の冪等用。Upstash Redis REST（HTTPS）で SET NX / EXISTS。
URL・トークン未設定時は何もせず、重複防止はオフ（ローカル開発向け）。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_PREFIX_WH = "ma:wh:"
_PREFIX_DONE = "ma:done:"


def is_dedupe_configured() -> bool:
    u = (settings.upstash_redis_rest_url or "").strip()
    t = (settings.upstash_redis_rest_token or "").strip()
    return bool(u and t)


def _base_url() -> str:
    return (settings.upstash_redis_rest_url or "").strip().rstrip("/")


def _execute(command: list[Any]) -> Any:
    """Upstash: POST root URL、ボディに Redis コマンドの JSON 配列。"""
    url = _base_url()
    token = (settings.upstash_redis_rest_token or "").strip()
    resp = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=command,
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(str(data["error"]))
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    raise RuntimeError(f"unexpected Upstash response: {data!r}")


def try_acquire_webhook(webhook_id: str) -> bool:
    """
    この Webhook ペイロード id を初めて処理するなら True。
    既に処理済みなら False（SET NX が効かなかった）。
    未設定・Redis エラー時はフェイルオープンで True（処理は進める）。
    """
    if not is_dedupe_configured():
        return True
    wid = (webhook_id or "").strip()
    if not wid:
        return True
    key = f"{_PREFIX_WH}{wid}"
    try:
        result = _execute(
            [
                "SET",
                key,
                "1",
                "EX",
                int(settings.dedupe_webhook_ttl_seconds),
                "NX",
            ]
        )
        return result == "OK"
    except Exception:
        logger.exception(
            "dedupe try_acquire_webhook failed webhook_id=%s; allowing processing",
            wid,
        )
        return True


def meeting_already_completed(meeting_id: str) -> bool:
    """パイプラインが過去に最後まで成功した会議なら True。"""
    if not is_dedupe_configured():
        return False
    mid = (meeting_id or "").strip()
    if not mid:
        return False
    key = f"{_PREFIX_DONE}{mid}"
    try:
        n = _execute(["EXISTS", key])
        return int(n or 0) >= 1
    except Exception:
        logger.exception(
            "dedupe meeting_already_completed failed meeting_id=%s; assuming not done",
            mid,
        )
        return False


def mark_meeting_completed(meeting_id: str) -> None:
    """Slack 投稿まで成功したあとに呼ぶ。失敗時はログのみ。"""
    if not is_dedupe_configured():
        return
    mid = (meeting_id or "").strip()
    if not mid:
        return
    key = f"{_PREFIX_DONE}{mid}"
    try:
        _execute(["SET", key, "1", "EX", int(settings.dedupe_meeting_ttl_seconds)])
    except Exception:
        logger.exception("dedupe mark_meeting_completed failed meeting_id=%s", mid)
