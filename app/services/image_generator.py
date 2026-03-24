"""
Claude の要約テキストを議事サマリー用 PNG にレンダリングする。
日本語は TrueType のフォントが必要（macOS のヒラギノ / Noto 等、または SUMMARY_FONT_PATH）。
"""

from __future__ import annotations

import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.config import settings

logger = logging.getLogger(__name__)

# レイアウト（SNS 系の縦長サムネに寄せた幅）
DEFAULT_WIDTH = 1080
MARGIN = 56
ACCENT_W = 12
TITLE_SIZE = 30
BODY_SIZE = 24
LINE_GAP_TITLE = 10
LINE_GAP_BODY = 6
MAX_IMAGE_HEIGHT = 14_000
TRUNCATION_NOTICE = "\n\n…（画像の高さ上限のため省略）"

# macOS / 一般的な Linux の日本語フォント候補（先頭から存在チェック）
_FONT_CANDIDATES: Tuple[str, ...] = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc",
    "/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)


def _truetype(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _resolve_font(size: int) -> Tuple[ImageFont.FreeTypeFont, bool]:
    """
    (font, is_bitmap_fallback)
    """
    env_path = (settings.summary_font_path or os.environ.get("SUMMARY_FONT_PATH") or "").strip()
    if env_path and Path(env_path).is_file():
        try:
            return _truetype(env_path, size), False
        except OSError:
            logger.warning("SUMMARY_FONT_PATH が読めません: %s", env_path)

    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            try:
                return _truetype(candidate, size), False
            except OSError:
                continue

    logger.warning(
        "日本語向け TrueType が見つかりません。bitmap フォントにフォールバックします。"
        " SUMMARY_FONT_PATH に .ttf / .ttc を指定してください。"
    )
    return ImageFont.load_default(), True


def _text_line_height(font: ImageFont.ImageFont, draw: ImageDraw.ImageDraw) -> int:
    bbox = draw.textbbox((0, 0), "あAy", font=font)
    return bbox[3] - bbox[1]


def _wrap_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> List[str]:
    lines: List[str] = []
    for block in text.replace("\r\n", "\n").split("\n"):
        if not block:
            lines.append("")
            continue
        current = ""
        for ch in block:
            trial = current + ch
            bbox = draw.textbbox((0, 0), trial, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def _measure_block_height(
    lines: List[str],
    line_height: int,
    gap: int,
) -> int:
    if not lines:
        return 0
    return len(lines) * line_height + (len(lines) - 1) * gap


def render_summary_png(
    meeting_info: Dict[str, Any],
    summary_text: str,
    *,
    width: int = DEFAULT_WIDTH,
) -> bytes:
    """
    会議メタ情報と Claude 要約テキストから PNG バイト列を生成する。
    """
    title_font, title_fallback = _resolve_font(TITLE_SIZE)
    body_font, body_fallback = _resolve_font(BODY_SIZE)
    if title_fallback or body_fallback:
        pass  # ログは _resolve_font 側

    inner_left = MARGIN + ACCENT_W + 20
    content_w = width - inner_left - MARGIN

    draft = Image.new("RGB", (width, 20))
    draw_draft = ImageDraw.Draw(draft)

    title_line_h = _text_line_height(title_font, draw_draft)
    body_line_h = _text_line_height(body_font, draw_draft)

    name = str(meeting_info.get("name") or "（無題）")
    happened = str(meeting_info.get("happened_at") or "")
    header = f"{name}\n{happened}".strip()

    title_lines = _wrap_to_width(draw_draft, header, title_font, content_w)
    body_lines = _wrap_to_width(draw_draft, summary_text.strip() or "（要約なし）", body_font, content_w)

    title_h = _measure_block_height(title_lines, title_line_h, LINE_GAP_TITLE)
    body_h = _measure_block_height(body_lines, body_line_h, LINE_GAP_BODY)

    top_pad = MARGIN
    sep_h = 24
    height = top_pad + title_h + sep_h + body_h + MARGIN

    if height > MAX_IMAGE_HEIGHT:
        notice_lines = _wrap_to_width(
            draw_draft,
            TRUNCATION_NOTICE.strip(),
            body_font,
            content_w,
        )
        notice_h = _measure_block_height(notice_lines, body_line_h, LINE_GAP_BODY)
        budget = MAX_IMAGE_HEIGHT - top_pad - title_h - sep_h - notice_h - MARGIN
        if budget < body_line_h * 3:
            budget = body_line_h * 3
        used = 0
        trimmed: List[str] = []
        for ln in body_lines:
            need = body_line_h + (LINE_GAP_BODY if trimmed else 0)
            if used + need > budget:
                break
            trimmed.append(ln)
            used += need
        body_lines = trimmed + notice_lines
        body_h = _measure_block_height(body_lines, body_line_h, LINE_GAP_BODY)
        height = min(top_pad + title_h + sep_h + body_h + MARGIN, MAX_IMAGE_HEIGHT)

    img = Image.new("RGB", (width, height), "#f4f4f5")
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, ACCENT_W, height), fill="#0d9488")

    y = top_pad
    x = inner_left
    for i, line in enumerate(title_lines):
        draw.text((x, y), line, font=title_font, fill="#0f172a")
        y += title_line_h
        if i < len(title_lines) - 1:
            y += LINE_GAP_TITLE

    y += sep_h // 2
    draw.line((inner_left, y, width - MARGIN, y), fill="#cbd5e1", width=2)
    y += sep_h // 2 + 8

    for i, line in enumerate(body_lines):
        draw.text((x, y), line, font=body_font, fill="#334155")
        y += body_line_h
        if i < len(body_lines) - 1:
            y += LINE_GAP_BODY

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
