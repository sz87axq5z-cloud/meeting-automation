"""
Slack へ議事要約 PNG を投稿する。
files.upload v2 フロー（getUploadURLExternal → completeUploadExternal）を slack_sdk がラップ。
"""

from __future__ import annotations

import logging
import ssl
from typing import Any, Dict, List, Optional

import certifi
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.config import settings

logger = logging.getLogger(__name__)

# initial_comment の安全な上限（公式のメッセージ上限より余裕を見る）
_MAX_COMMENT = 3500


def _slack_ssl_context() -> ssl.SSLContext:
    """
    macOS で python.org ビルドを使うと、urllib 経由の Slack SDK が
    「unable to get local issuer certificate」になりがち。
    certifi の CA バンドルを明示して検証する。
    """
    return ssl.create_default_context(cafile=certifi.where())


def _slack_web_client() -> WebClient:
    return WebClient(
        token=settings.slack_bot_token,
        ssl=_slack_ssl_context(),
    )


def _build_initial_comment(
    meeting_id: str,
    meeting_info: Dict[str, Any],
    trello_urls: Optional[List[str]] = None,
) -> str:
    name = str(meeting_info.get("name") or "会議")
    happened = str(meeting_info.get("happened_at") or "").strip()
    url = meeting_info.get("url")
    lines = [
        f"*{name}*",
        f"Meeting ID: `{meeting_id}`",
    ]
    if happened:
        lines.append(happened)
    if url:
        lines.append(f"<{url}|tl;dv で開く>")
    base = "\n".join(lines)

    if trello_urls:
        tl_lines: List[str] = ["", "*Trello*"]
        for u in trello_urls:
            tl_lines.append(f"• <{u}|カード>")
        while True:
            extra = "\n".join(tl_lines)
            if len(base) + len(extra) <= _MAX_COMMENT:
                base = base + extra
                break
            if len(tl_lines) <= 2:
                base = base + "\n\n*Trello*\n• …"
                break
            tl_lines.pop()

    if len(base) > _MAX_COMMENT:
        return base[: _MAX_COMMENT - 1] + "…"
    return base


def post_pipeline_failure_message(
    *,
    meeting_id: str,
    stage: str,
    error_detail: str | None = None,
) -> None:
    """
    パイプライン失敗を SLACK_CHANNEL_ID にテキストで通知する。
    通知自体が失敗しても例外は出さない（ログのみ）。
    """
    text_lines = [
        ":warning: *会議自動化エラー*",
        f"• 会議 ID: `{meeting_id}`",
        f"• 段階: `{stage}`",
    ]
    if error_detail:
        detail = error_detail.strip()
        if len(detail) > 400:
            detail = detail[:397] + "…"
        text_lines.append(f"• 詳細: ```{detail}```")
    text = "\n".join(text_lines)

    try:
        client = _slack_web_client()
        client.chat_postMessage(
            channel=settings.slack_channel_id,
            text=text,
        )
        logger.info(
            "slack pipeline failure message posted meeting_id=%s stage=%s",
            meeting_id,
            stage,
        )
    except SlackApiError as e:
        logger.error(
            "slack chat_postMessage failed meeting_id=%s stage=%s response=%s",
            meeting_id,
            stage,
            e.response,
        )
    except Exception:
        logger.exception(
            "slack pipeline failure message unexpected error meeting_id=%s stage=%s",
            meeting_id,
            stage,
        )


def post_meeting_summary_png(
    *,
    png_bytes: bytes,
    meeting_id: str,
    meeting_info: Dict[str, Any],
    trello_urls: Optional[List[str]] = None,
) -> str | None:
    """
    要約 PNG を投稿する。
    戻り値: Slack ファイル ID（取得できれば）。失敗時は例外。
    """
    client = _slack_web_client()
    name = str(meeting_info.get("name") or "会議")
    title = f"{name} — 要約"
    if len(title) > 255:
        title = title[:252] + "…"

    filename = f"meeting_summary_{meeting_id}.png"
    initial_comment = _build_initial_comment(meeting_id, meeting_info, trello_urls)

    try:
        resp = client.files_upload_v2(
            channel=settings.slack_channel_id,
            content=png_bytes,
            filename=filename,
            title=title,
            initial_comment=initial_comment,
        )
    except SlackApiError as e:
        logger.error(
            "Slack API error meeting_id=%s response=%s",
            meeting_id,
            e.response,
        )
        raise

    data = resp.data if hasattr(resp, "data") else resp
    file_obj = data.get("file") if isinstance(data, dict) else None
    if not file_obj and isinstance(data, dict):
        files = data.get("files")
        if files and isinstance(files, list):
            file_obj = files[0]
    fid = None
    if isinstance(file_obj, dict):
        fid = file_obj.get("id")
    logger.info(
        "slack files_upload_v2 ok meeting_id=%s channel=%s file_id=%s",
        meeting_id,
        settings.slack_channel_id,
        fid,
    )
    return str(fid) if fid else None
