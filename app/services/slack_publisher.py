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
from app.formatting import format_happened_at_display

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
    summary_html_url: Optional[str] = None,
    *,
    html_public_url_missing: bool = False,
) -> str:
    name = str(meeting_info.get("name") or "会議")
    happened = format_happened_at_display(meeting_info.get("happened_at"))
    url = meeting_info.get("url")
    lines = [
        f"*{name}*",
        f"Meeting ID: `{meeting_id}`",
    ]
    if happened:
        lines.append(happened)
    if url:
        lines.append(f"<{url}|tl;dv で開く>")
    if summary_html_url and str(summary_html_url).strip():
        u = str(summary_html_url).strip()
        lines.append("")
        lines.append("*要約（HTML）*")
        lines.append(f"<{u}|ブラウザで開く（図解ページ）>")
    elif html_public_url_missing:
        lines.append("")
        lines.append(
            "※ 要約の *HTML 図解* をタップ1回でブラウザ表示するには、"
            "`MEETING_HTML_S3_BUCKET` と AWS 認証を `.env` に設定してください（README「要約 HTML の公開 URL」）。"
        )
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


def _file_obj_from_upload_response(resp: Any) -> dict | None:
    data = resp.data if hasattr(resp, "data") else resp
    if not isinstance(data, dict):
        return None
    file_obj = data.get("file")
    if isinstance(file_obj, dict):
        return file_obj
    files = data.get("files")
    if files and isinstance(files, list) and isinstance(files[0], dict):
        return files[0]
    return None


def upload_summary_html_to_slack(
    *,
    html_bytes: bytes,
    meeting_id: str,
    meeting_info: Dict[str, Any],
) -> str | None:
    """
    要約 HTML をチャンネルにファイル投稿する（デバッグ・手動用途向け）。
    Slack アプリ内では .html はソース表示になりやすく、パイプラインからは呼ばない。
    失敗時は None（ログのみ）。
    """
    client = _slack_web_client()
    name = str(meeting_info.get("name") or "会議")
    title = f"{name} — 要約（HTML）"
    if len(title) > 255:
        title = title[:252] + "…"
    filename = f"meeting_summary_{meeting_id}.html"
    if len(filename) > 255:
        filename = filename[:252] + ".html"

    try:
        resp = client.files_upload_v2(
            channel=settings.slack_channel_id,
            content=html_bytes,
            filename=filename,
            title=title,
        )
    except SlackApiError as e:
        logger.error(
            "slack html files_upload_v2 failed meeting_id=%s response=%s",
            meeting_id,
            e.response,
        )
        return None
    except Exception:
        logger.exception("slack html files_upload_v2 unexpected meeting_id=%s", meeting_id)
        return None

    file_obj = _file_obj_from_upload_response(resp)
    if not file_obj:
        logger.warning(
            "slack html upload ok but no file object meeting_id=%s",
            meeting_id,
        )
        return None
    permalink = file_obj.get("permalink")
    if permalink:
        logger.info(
            "slack summary html file ok meeting_id=%s file_id=%s",
            meeting_id,
            file_obj.get("id"),
        )
        return str(permalink).strip()
    logger.warning(
        "slack html file missing permalink meeting_id=%s file_id=%s",
        meeting_id,
        file_obj.get("id"),
    )
    return None


def post_infographic_gcs_share_notice(
    *,
    meeting_id: str,
    meeting_info: Dict[str, Any],
    public_url: str,
    password: str,
    channel_id: str,
) -> bool:
    """
    図解 GCS 公開 URL とパスワードを Slack にテキスト投稿する。
    失敗時は False（例外は出さない）。
    """
    name = str(meeting_info.get("name") or "会議")
    lines = [
        ":lock: *図解HTML（パスワード保護）*",
        f"• 会議: {name}",
        f"• Meeting ID: `{meeting_id}`",
        f"• 公開URL: {public_url}",
        f"• パスワード: `{password}`",
        "",
        "関係者へ URL とパスワードの両方を共有してください。ブラウザで入力すると表示されます。",
    ]
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "…"

    try:
        client = _slack_web_client()
        client.chat_postMessage(channel=channel_id, text=text)
        logger.info(
            "slack infographic share notice ok meeting_id=%s channel=%s",
            meeting_id,
            channel_id,
        )
        return True
    except SlackApiError as e:
        logger.error(
            "slack infographic chat_postMessage failed meeting_id=%s response=%s",
            meeting_id,
            e.response,
        )
        return False
    except Exception:
        logger.exception(
            "slack infographic share notice unexpected meeting_id=%s",
            meeting_id,
        )
        return False


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
    summary_html_url: Optional[str] = None,
    html_public_url_missing: bool = False,
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
    initial_comment = _build_initial_comment(
        meeting_id,
        meeting_info,
        trello_urls,
        summary_html_url=summary_html_url,
        html_public_url_missing=html_public_url_missing,
    )

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

    file_obj = _file_obj_from_upload_response(resp)
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
