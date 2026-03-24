import logging

from app.services.claude_processor import summarize_and_extract_tasks
from app.services.image_generator import render_summary_png
from app.services.slack_publisher import post_meeting_summary_png
from app.services.tldv_client import fetch_meeting_context
from app.services.trello_client import create_cards_for_tasks, parse_tasks_from_claude_text


logger = logging.getLogger(__name__)


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
    try:
        meeting_info, transcript = fetch_meeting_context(meeting_id)
    except Exception:
        logger.exception("tl;dv fetch failed meeting_id=%s", meeting_id)
        return

    tchars = len(transcript.strip())
    logger.info("tl;dv transcript ready meeting_id=%s chars=%s", meeting_id, tchars)
    if not transcript.strip():
        logger.warning("empty transcript, skip Claude meeting_id=%s", meeting_id)
        return

    try:
        result = summarize_and_extract_tasks(transcript, meeting_info)
    except Exception:
        logger.exception("Claude failed meeting_id=%s", meeting_id)
        return

    raw_len = len(result.get("raw_text") or "")
    logger.info("run_pipeline Claude ok meeting_id=%s raw_chars=%s", meeting_id, raw_len)

    try:
        png_bytes = render_summary_png(meeting_info, result.get("raw_text") or "")
    except Exception:
        logger.exception("summary PNG failed meeting_id=%s", meeting_id)
        return

    logger.info(
        "run_pipeline summary png ok meeting_id=%s png_bytes=%s",
        meeting_id,
        len(png_bytes),
    )

    raw_text = result.get("raw_text") or ""
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
        except Exception:
            logger.exception("Trello failed meeting_id=%s", meeting_id)
    else:
        logger.info("run_pipeline trello skip no parsed tasks meeting_id=%s", meeting_id)

    try:
        file_id = post_meeting_summary_png(
            png_bytes=png_bytes,
            meeting_id=meeting_id,
            meeting_info=meeting_info,
            trello_urls=trello_urls or None,
        )
    except Exception:
        logger.exception("Slack post failed meeting_id=%s", meeting_id)
        return

    logger.info(
        "run_pipeline slack ok meeting_id=%s slack_file_id=%s",
        meeting_id,
        file_id,
    )

