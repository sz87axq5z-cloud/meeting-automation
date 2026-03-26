"""
Claude の要約テキストを議事サマリー用 PNG にレンダリングする。
要件定義 HTML（ダークテーマ・カード・アクセント）に近いビジュアル。
日本語 TrueType: SUMMARY_FONT_PATH → fonts/ 同梱 → SUMMARY_FONT_DOWNLOAD_URL → OS 候補。
"""

from __future__ import annotations

import logging
import os
import re
import ssl
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

import certifi
from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.formatting import format_happened_at_display

logger = logging.getLogger(__name__)

# 要件定義_図解_v2.html の CSS 変数に合わせたパレット
COL_BG = "#0a0c10"
COL_SURFACE = "#13161f"
COL_BORDER = "#252d40"
COL_TEXT = "#e2e8f0"
COL_MUTED = "#64748b"
# .flow-step .s1 … s6 のアクセント（左ライン・見出し色）
COL_ACCENTS: Tuple[str, ...] = (
    "#06b6d4",
    "#8b5cf6",
    "#f59e0b",
    "#3b82f6",
    "#10b981",
    "#ef4444",
)

DEFAULT_WIDTH = 1080
MARGIN = 48
CARD_GAP = 18
CARD_PAD = 22
CARD_RADIUS = 14
ACCENT_BAR_W = 5
KICKER_SIZE = 17
MEETING_TITLE_SIZE = 36
DATE_SIZE = 20
SECTION_SIZE = 23
BODY_SIZE = 20
LINE_GAP_TIGHT = 6
LINE_GAP_SECTION = 10
HEADER_GAP_AFTER_DATE = 28
MAX_IMAGE_HEIGHT = 14_000
TRUNCATION_NOTICE = "\n\n…（画像の高さ上限のため省略）"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BUNDLED_JP_FONT_CANDIDATES: Tuple[Path, ...] = (
    _PROJECT_ROOT / "fonts" / "NotoSansJP-Regular.otf",
    _PROJECT_ROOT / "fonts" / "NotoSansCJKjp-Regular.otf",
)
_DEFAULT_JP_FONT_URL = (
    "https://raw.githubusercontent.com/notofonts/noto-cjk/main/"
    "Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf"
)
_TMP_FONT_NAME = "meeting_automation_NotoSansCJKjp-Regular.otf"
_MIN_FONT_BYTES = 500_000

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


def _cached_noto_font_path() -> Path:
    return Path(tempfile.gettempdir()) / _TMP_FONT_NAME


def _noto_download_url() -> str | None:
    raw = os.environ.get("SUMMARY_FONT_DOWNLOAD_URL")
    if raw is None:
        return _DEFAULT_JP_FONT_URL
    s = raw.strip()
    return None if s == "" else s


def _ensure_noto_sans_jp_otf() -> str | None:
    cache = _cached_noto_font_path()
    if cache.is_file() and cache.stat().st_size >= _MIN_FONT_BYTES:
        return str(cache)

    url = _noto_download_url()
    if not url:
        return None

    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "meeting-automation-summary-font/1.0"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=90) as resp:
            data = resp.read()
        if len(data) < _MIN_FONT_BYTES:
            logger.warning(
                "要約用フォントの取得結果が小さすぎます (%d bytes)。URL を確認してください。",
                len(data),
            )
            return None
        cache.write_bytes(data)
        return str(cache)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        logger.warning("要約用フォントのダウンロードに失敗しました: %s", exc)
        return None


def _resolve_font(size: int) -> Tuple[ImageFont.FreeTypeFont, bool]:
    env_path = (settings.summary_font_path or os.environ.get("SUMMARY_FONT_PATH") or "").strip()
    if env_path and Path(env_path).is_file():
        try:
            return _truetype(env_path, size), False
        except OSError:
            logger.warning("SUMMARY_FONT_PATH が読めません: %s", env_path)

    for bundled in _BUNDLED_JP_FONT_CANDIDATES:
        if bundled.is_file():
            try:
                return _truetype(str(bundled), size), False
            except OSError:
                logger.warning("同梱フォントが読めません: %s", bundled)

    dl_path = _ensure_noto_sans_jp_otf()
    if dl_path:
        try:
            return _truetype(dl_path, size), False
        except OSError:
            logger.warning("キャッシュしたフォントが読めません: %s", dl_path)

    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            try:
                return _truetype(candidate, size), False
            except OSError:
                continue

    logger.warning(
        "日本語向け TrueType が見つかりません。bitmap フォントにフォールバックします。"
        " SUMMARY_FONT_PATH、fonts/*.otf（NotoSansCJKjp-Regular 等）、または SUMMARY_FONT_DOWNLOAD_URL を確認してください。"
    )
    return ImageFont.load_default(), True


@dataclass(frozen=True)
class _FontSet:
    kicker: ImageFont.ImageFont
    title: ImageFont.ImageFont
    date: ImageFont.ImageFont
    section: ImageFont.ImageFont
    body: ImageFont.ImageFont


def _load_font_set() -> _FontSet:
    k, _ = _resolve_font(KICKER_SIZE)
    t, _ = _resolve_font(MEETING_TITLE_SIZE)
    d, _ = _resolve_font(DATE_SIZE)
    s, _ = _resolve_font(SECTION_SIZE)
    b, _ = _resolve_font(BODY_SIZE)
    return _FontSet(kicker=k, title=t, date=d, section=s, body=b)


def _strip_inline_markdown(text: str) -> str:
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    return t.strip()


def parse_summary_sections(raw: str) -> List[Tuple[str | None, str]]:
    """
    `## 見出し` で区切られたブロックを (見出し, 本文) のリストにする。
    先頭に ## が無い場合は [(None, 全文)]。
    ## より前のテキストは「概要」カードに入れる。
    """
    text = (raw or "").strip()
    if not text:
        return [(None, "（要約なし）")]

    pattern = re.compile(r"(?m)^##\s+(.+?)\s*$")
    if not pattern.search(text):
        return [(None, _strip_inline_markdown(text))]

    segments = pattern.split(text)
    out: List[Tuple[str | None, str]] = []
    preamble = segments[0].strip()
    if preamble:
        out.append(("概要", _strip_inline_markdown(preamble)))

    rest = segments[1:]
    for i in range(0, len(rest), 2):
        h = _strip_inline_markdown(rest[i])
        body = rest[i + 1].strip() if i + 1 < len(rest) else ""
        out.append((h or "（無題）", _strip_inline_markdown(body)))

    return out if out else [(None, _strip_inline_markdown(text))]


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


def _content_inner_width(width: int) -> int:
    return width - MARGIN * 2


def _card_inner_width(width: int) -> int:
    return _content_inner_width(width) - CARD_PAD * 2 - ACCENT_BAR_W - 12


def _draw_card_fixed_lines(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    accent: str,
    heading: str | None,
    heading_lines: List[str],
    body_lines: List[str],
    inner_left: int,
    inner_w: int,
    fonts: _FontSet,
) -> None:
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=CARD_RADIUS,
        fill=COL_SURFACE,
        outline=COL_BORDER,
        width=1,
    )
    bar_left = x0 + CARD_PAD // 2
    draw.rounded_rectangle(
        [bar_left, y0 + CARD_PAD, bar_left + ACCENT_BAR_W, y1 - CARD_PAD],
        radius=2,
        fill=accent,
    )

    tx = inner_left
    ty = y0 + CARD_PAD
    body_lh = _text_line_height(fonts.body, draw)
    sec_lh = _text_line_height(fonts.section, draw)

    if heading is not None and heading_lines:
        for i, line in enumerate(heading_lines):
            draw.text((tx, ty), line, font=fonts.section, fill=accent)
            ty += sec_lh + (LINE_GAP_TIGHT if i < len(heading_lines) - 1 else 0)
        ty += LINE_GAP_SECTION

    for i, line in enumerate(body_lines):
        color = COL_MUTED if not line.strip() else COL_TEXT
        draw.text((tx, ty), line, font=fonts.body, fill=color)
        ty += body_lh + (LINE_GAP_TIGHT if i < len(body_lines) - 1 else 0)


def render_summary_png(
    meeting_info: Dict[str, Any],
    summary_text: str,
    *,
    width: int = DEFAULT_WIDTH,
) -> bytes:
    fonts = _load_font_set()

    draft = Image.new("RGB", (width, 40))
    draw_d = ImageDraw.Draw(draft)
    inner_w_full = _content_inner_width(width)
    card_text_w = _card_inner_width(width)

    name = _strip_inline_markdown(str(meeting_info.get("name") or "（無題）"))
    happened = format_happened_at_display(
        str(meeting_info.get("happened_at") or "").strip() or None
    )

    kicker_lh = _text_line_height(fonts.kicker, draw_d)
    title_lh = _text_line_height(fonts.title, draw_d)
    date_lh = _text_line_height(fonts.date, draw_d)

    kicker_lines = _wrap_to_width(draw_d, "MEETING SUMMARY  ·  議事サマリー", fonts.kicker, inner_w_full)
    title_lines = _wrap_to_width(draw_d, name, fonts.title, inner_w_full)
    date_lines = (
        _wrap_to_width(draw_d, happened, fonts.date, inner_w_full) if happened else []
    )

    header_h = (
        _measure_block_height(kicker_lines, kicker_lh, LINE_GAP_TIGHT)
        + 12
        + _measure_block_height(title_lines, title_lh, LINE_GAP_TIGHT)
        + (8 + _measure_block_height(date_lines, date_lh, LINE_GAP_TIGHT) if date_lines else 0)
    )

    sections = parse_summary_sections(summary_text)

    # (heading, body, heading_lines, body_lines, card_h, accent)
    prepared: List[Tuple[str | None, str, List[str], List[str], int, str]] = []
    for idx, (hd, body) in enumerate(sections):
        hl = _wrap_to_width(draw_d, hd, fonts.section, card_text_w) if hd else []
        bl = _wrap_to_width(draw_d, body, fonts.body, card_text_w)
        sec_lh = _text_line_height(fonts.section, draw_d)
        body_lh = _text_line_height(fonts.body, draw_d)
        if hd:
            h_h = _measure_block_height(hl, sec_lh, LINE_GAP_TIGHT)
            card_h = CARD_PAD + h_h + LINE_GAP_SECTION + _measure_block_height(bl, body_lh, LINE_GAP_TIGHT) + CARD_PAD
        else:
            card_h = CARD_PAD + _measure_block_height(bl, body_lh, LINE_GAP_TIGHT) + CARD_PAD
        accent = COL_ACCENTS[idx % len(COL_ACCENTS)]
        prepared.append((hd, body, hl, bl, card_h, accent))

    total_h = (
        MARGIN
        + header_h
        + HEADER_GAP_AFTER_DATE
        + sum(p[4] + CARD_GAP for p in prepared)
        - CARD_GAP
        + MARGIN
    )

    body_lh_m = _text_line_height(fonts.body, draw_d)
    sec_lh_m = _text_line_height(fonts.section, draw_d)

    def _card_shell_h(hd: str | None, hl: List[str]) -> int:
        shell = 2 * CARD_PAD
        if hd:
            shell += _measure_block_height(hl, sec_lh_m, LINE_GAP_TIGHT) + LINE_GAP_SECTION
        return shell

    if total_h > MAX_IMAGE_HEIGHT:
        notice_lines = _wrap_to_width(
            draw_d, TRUNCATION_NOTICE.strip(), fonts.body, card_text_w
        )
        notice_h = _measure_block_height(notice_lines, body_lh_m, LINE_GAP_TIGHT)
        avail = MAX_IMAGE_HEIGHT - MARGIN * 2 - header_h - HEADER_GAP_AFTER_DATE

        final_prep: List[Tuple[str | None, str, List[str], List[str], int, str]] = []
        used = 0
        for hd, body, hl, bl, _old_ch, accent in prepared:
            gap_before = CARD_GAP if final_prep else 0
            shell = _card_shell_h(hd, hl)
            full_body_h = _measure_block_height(bl, body_lh_m, LINE_GAP_TIGHT)
            full_card = shell + full_body_h
            if used + gap_before + full_card <= avail:
                final_prep.append((hd, body, hl, bl, full_card, accent))
                used += gap_before + full_card
                continue

            room = avail - used - gap_before
            if room < shell + body_lh_m + notice_h:
                break

            max_body_px = room - shell - notice_h
            trimmed: List[str] = []
            acc_px = 0
            for ln in bl:
                need = body_lh_m + (LINE_GAP_TIGHT if trimmed else 0)
                if acc_px + need > max_body_px:
                    break
                trimmed.append(ln)
                acc_px += need
            bl2 = trimmed + notice_lines
            card_h = shell + _measure_block_height(bl2, body_lh_m, LINE_GAP_TIGHT)
            if card_h <= room:
                final_prep.append((hd, body, hl, bl2, card_h, accent))
            break

        if not final_prep and prepared:
            hd0, body0, hl0, _, _, accent0 = prepared[0]
            shell0 = _card_shell_h(hd0, hl0)
            bl_fallback = notice_lines
            ch0 = shell0 + _measure_block_height(bl_fallback, body_lh_m, LINE_GAP_TIGHT)
            if ch0 > avail:
                hd0, hl0 = None, []
                shell0 = _card_shell_h(None, [])
                ch0 = shell0 + _measure_block_height(bl_fallback, body_lh_m, LINE_GAP_TIGHT)
            final_prep = [(hd0, body0, hl0, bl_fallback, ch0, accent0)]

        prepared = final_prep
        total_h = min(
            MARGIN
            + header_h
            + HEADER_GAP_AFTER_DATE
            + sum(p[4] + CARD_GAP for p in prepared)
            - CARD_GAP
            + MARGIN,
            MAX_IMAGE_HEIGHT,
        )

    img = Image.new("RGB", (width, total_h), COL_BG)
    draw = ImageDraw.Draw(img)

    y = MARGIN
    x_text = MARGIN

    for i, line in enumerate(kicker_lines):
        draw.text((x_text, y), line, font=fonts.kicker, fill=COL_MUTED)
        y += kicker_lh + (LINE_GAP_TIGHT if i < len(kicker_lines) - 1 else 0)
    y += 12

    for i, line in enumerate(title_lines):
        draw.text((x_text, y), line, font=fonts.title, fill=COL_TEXT)
        y += title_lh + (LINE_GAP_TIGHT if i < len(title_lines) - 1 else 0)

    if date_lines:
        y += 8
        for i, line in enumerate(date_lines):
            draw.text((x_text, y), line, font=fonts.date, fill=COL_MUTED)
            y += date_lh + (LINE_GAP_TIGHT if i < len(date_lines) - 1 else 0)

    y += HEADER_GAP_AFTER_DATE

    x0_card = MARGIN
    x1_card = width - MARGIN
    inner_left = x0_card + CARD_PAD + ACCENT_BAR_W + 12

    for hd, _body, hl, bl, card_h, accent in prepared:
        _draw_card_fixed_lines(
            draw,
            x0_card,
            y,
            x1_card,
            y + card_h,
            accent,
            hd,
            hl,
            bl,
            inner_left,
            card_text_w,
            fonts,
        )
        y += card_h + CARD_GAP

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
