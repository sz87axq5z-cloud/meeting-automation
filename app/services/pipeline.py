import logging

from app.services.claude_processor import summarize_and_extract_tasks
from app.services.dedupe import mark_meeting_completed, meeting_already_completed
from app.services.image_generator import render_summary_png
from app.services.slack_publisher import (
    post_meeting_summary_png,
    post_pipeline_failure_message,
)
from app.services.summary_html import build_summary_html_document
from app.services.summary_html_publish import publish_summary_html
from app.services.tldv_client import fetch_meeting_context
from app.services.trello_client import create_cards_for_tasks, parse_tasks_from_claude_text


logger = logging.getLogger(__name__)


def _exc_detail(exc: Exception | None) -> str | None:
    if exc is None:
        return None
    return f"{type(exc).__name__}: {exc}"


def _ensure_default_logging() -> None:
    """
    `python -c "… run_pipeline(…)"` のように単体実行するとき、
    ルートにハンドラが無く INFO がどこにも出ないため basicConfig する。
    uvicorn 等ですでに設定済みなら何もしない。
    """
    root = logging.getLogger()
    if root.handlers:
        return
    from app.config import settings

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def run_pipeline(meeting_id: str) -> None:
    """
    メインの自動化フローを実行する入り口。
    tl;dv → Claude → 要約 PNG → Trello カード → Slack（画像＋Trello リンク）。
    """
    _ensure_default_logging()
    logger.info("run_pipeline start meeting_id=%s", meeting_id)
    if meeting_already_completed(meeting_id):
        logger.info(
            "run_pipeline skip meeting already completed meeting_id=%s",
            meeting_id,
        )
        return

    try:
        meeting_info, transcript = fetch_meeting_context(meeting_id)
    except Exception as e:
        logger.exception("tl;dv fetch failed meeting_id=%s", meeting_id)
        post_pipeline_failure_message(
            meeting_id=meeting_id,
            stage="tl;dv",
            error_detail=_exc_detail(e),
        )
        return

    tchars = len(transcript.strip())
    logger.info("tl;dv transcript ready meeting_id=%s chars=%s", meeting_id, tchars)
    if not transcript.strip():
        logger.warning("empty transcript, skip Claude meeting_id=%s", meeting_id)
        return

    try:
        result = summarize_and_extract_tasks(transcript, meeting_info)
    except Exception as e:
        logger.exception("Claude failed meeting_id=%s", meeting_id)
        post_pipeline_failure_message(
            meeting_id=meeting_id,
            stage="Claude",
            error_detail=_exc_detail(e),
        )
        return

    raw_len = len(result.get("raw_text") or "")
    logger.info("run_pipeline Claude ok meeting_id=%s raw_chars=%s", meeting_id, raw_len)

    try:
        png_bytes = render_summary_png(meeting_info, result.get("raw_text") or "")
    except Exception as e:
        logger.exception("summary PNG failed meeting_id=%s", meeting_id)
        post_pipeline_failure_message(
            meeting_id=meeting_id,
            stage="画像",
            error_detail=_exc_detail(e),
        )
        return

    logger.info(
        "run_pipeline summary png ok meeting_id=%s png_bytes=%s",
        meeting_id,
        len(png_bytes),
    )

    raw_text = result.get("raw_text") or ""

    html_doc = build_summary_html_document(meeting_info, raw_text)
    html_bytes = html_doc.encode("utf-8")
    summary_html_url = publish_summary_html(
        html_bytes=html_bytes,
        meeting_id=meeting_id,
    )
    if summary_html_url:
        logger.info(
            "run_pipeline summary html public url meeting_id=%s",
            meeting_id,
        )
    else:
        logger.info(
            "run_pipeline summary html no public url (set MEETING_HTML_S3_BUCKET for browser link) meeting_id=%s",
            meeting_id,
        )

    task_titles = parse_tasks_from_claude_text(raw_text)
    trello_urls: list[str] = []
    if task_titles:
        try:
            trello_urls = create_cards_for_tasks(
                task_titles,
                meeting_id,
                meeting_info,
            )
            logger.info(
                "run_pipeline trello ok meeting_id=%s cards=%s",
                meeting_id,
                len(trello_urls),
            )
        except Exception as e:
            logger.exception("Trello failed meeting_id=%s", meeting_id)
            post_pipeline_failure_message(
                meeting_id=meeting_id,
                stage="Trello",
                error_detail=_exc_detail(e),
            )
    else:
        logger.info("run_pipeline trello skip no parsed tasks meeting_id=%s", meeting_id)

    try:
        file_id = post_meeting_summary_png(
            png_bytes=png_bytes,
            meeting_id=meeting_id,
            meeting_info=meeting_info,
            trello_urls=trello_urls or None,
            summary_html_url=summary_html_url,
            html_public_url_missing=not bool(summary_html_url),
        )
    except Exception as e:
        logger.exception("Slack post failed meeting_id=%s", meeting_id)
        post_pipeline_failure_message(
            meeting_id=meeting_id,
            stage="Slack",
            error_detail=_exc_detail(e),
        )
        return

    mark_meeting_completed(meeting_id)
    logger.info(
        "run_pipeline SUCCESS meeting_id=%s slack_file_id=%s",
        meeting_id,
        file_id,
    )

