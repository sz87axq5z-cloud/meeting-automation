"""
Claude の要約テキストを議事サマリー用 PNG にレンダリングする。
トラスポ上流設計図解（https://truspo-ca-system-design.surge.sh/）系の
ダークヒーロー + ライト本文・サマリ帯・白カードのドキュメント調 UI。
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

# トラスポ CA 上流設計図解風（ライトドキュメント + ネイビーヒーロー）
COL_PAGE_BG = "#e8ecf4"
COL_HERO_BG = "#1e293b"
COL_HERO_LINE = "#3b82f6"
COL_TEXT = "#1e293b"
COL_TEXT_ON_HERO = "#ffffff"
COL_MUTED = "#64748b"
COL_MUTED_ON_HERO = "#94a3b8"
COL_CARD = "#ffffff"
COL_CARD_INNER = "#f1f5f9"
COL_BORDER = "#e2e8f0"
COL_BORDER_SOFT = "#f1f5f9"
COL_SHADOW_SOFT = "#b8c4d4"
COL_INSIGHT_BAR = "#2563eb"
COL_INSIGHT_LABEL = "#2563eb"
COL_PILL_BG = "#ffffff"
COL_FLOW_MARK = "#94a3b8"
# セクション左ライン・箇条書き（青〜ティール系で統一感）
COL_ACCENTS: Tuple[str, ...] = (
    "#2563eb",
    "#0ea5e9",
    "#4f46e5",
    "#0891b2",
    "#0369a1",
    "#6366f1",
)

DEFAULT_WIDTH = 1080
MARGIN = 48
HERO_PAD_X = 52
HERO_PAD_TOP = 36
HERO_PAD_BOTTOM = 32
HERO_ACCENT_LINE_H = 4
CONTENT_TOP_GAP = 28
CARD_GAP = 20
CARD_PAD = 22
CARD_RADIUS = 14
ACCENT_BAR_W = 4
STEP_PILL_W = 38
STEP_PILL_H = 30
TITLE_GAP_AFTER_PILL = 14
INNER_PAD = 18
INNER_RADIUS = 10
INSIGHT_BAR_W = 5
FLOW_ARROW_GAP = 6
KICKER_SIZE = 16
MEETING_TITLE_SIZE = 40
DATE_SIZE = 20
SECTION_SIZE = 25
BODY_SIZE = 21
BADGE_NUM_SIZE = 16
INSIGHT_LABEL_SIZE = 15
LINE_GAP_TIGHT = 7
LINE_GAP_SECTION = 10
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
    badge: ImageFont.ImageFont
    label: ImageFont.ImageFont


def _load_font_set() -> _FontSet:
    k, _ = _resolve_font(KICKER_SIZE)
    t, _ = _resolve_font(MEETING_TITLE_SIZE)
    d, _ = _resolve_font(DATE_SIZE)
    s, _ = _resolve_font(SECTION_SIZE)
    b, _ = _resolve_font(BODY_SIZE)
    bg, _ = _resolve_font(BADGE_NUM_SIZE)
    lb, _ = _resolve_font(INSIGHT_LABEL_SIZE)
    return _FontSet(kicker=k, title=t, date=d, section=s, body=b, badge=bg, label=lb)


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


def _split_insight_section(
    sections: List[Tuple[str | None, str]],
) -> tuple[List[Tuple[str | None, str]], str | None]:
    """先頭が「概要」のとき本文をサマリ帯用に切り出す（Truspo のサマリ欄相当）。"""
    if not sections:
        return [], None
    h0, b0 = sections[0]
    if h0 == "概要" and (b0 or "").strip():
        return sections[1:], b0
    return sections, None


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


def _card_content_box(x0_card: int, x1_card: int) -> Tuple[int, int]:
    """カード内の本文エリア左端と幅（アクセントバー右）。"""
    left = x0_card + CARD_PAD + ACCENT_BAR_W + 12
    w = x1_card - CARD_PAD - left
    return left, w


_BULLET_LINE_RE = re.compile(r"^[\-\*・]\s*")


def _measure_section_card(
    draw_d: ImageDraw.ImageDraw,
    hd: str | None,
    body: str,
    fonts: _FontSet,
    content_w: int,
    sec_lh: int,
    body_lh: int,
) -> Tuple[List[str], List[str], int]:
    title_max = content_w - STEP_PILL_W - 10 if hd else content_w
    hl = _wrap_to_width(draw_d, hd, fonts.section, title_max) if hd else []
    inner_text_w = max(100, content_w - 2 * INNER_PAD)
    bl = _wrap_to_width(draw_d, body, fonts.body, inner_text_w)
    if hd:
        title_block_h = max(STEP_PILL_H, _measure_block_height(hl, sec_lh, LINE_GAP_TIGHT))
        top_stack = CARD_PAD + title_block_h + TITLE_GAP_AFTER_PILL
    else:
        top_stack = CARD_PAD
    body_h = _measure_block_height(bl, body_lh, LINE_GAP_TIGHT)
    inner_h = 2 * INNER_PAD + body_h
    card_h = top_stack + inner_h + CARD_PAD
    return hl, bl, card_h


def _card_height_from_lines(
    hd: str | None,
    hl: List[str],
    bl: List[str],
    sec_lh: int,
    body_lh: int,
) -> int:
    if hd:
        title_block_h = max(STEP_PILL_H, _measure_block_height(hl, sec_lh, LINE_GAP_TIGHT))
        top_stack = CARD_PAD + title_block_h + TITLE_GAP_AFTER_PILL
    else:
        top_stack = CARD_PAD
    body_h = _measure_block_height(bl, body_lh, LINE_GAP_TIGHT)
    return top_stack + 2 * INNER_PAD + body_h + CARD_PAD


def _measure_insight_block(
    draw_d: ImageDraw.ImageDraw,
    body: str,
    fonts: _FontSet,
    content_w: int,
    label_lh: int,
    body_lh: int,
) -> Tuple[List[str], int]:
    inner_text_w = max(100, content_w - 2 * CARD_PAD - INSIGHT_BAR_W - 14)
    bl = _wrap_to_width(draw_d, body, fonts.body, inner_text_w)
    body_h = _measure_block_height(bl, body_lh, LINE_GAP_TIGHT)
    h = CARD_PAD + label_lh + 12 + body_h + CARD_PAD
    return bl, h


def _draw_insight_block(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    x1: int,
    insight_h: int,
    bl: List[str],
    fonts: _FontSet,
) -> None:
    y1 = y0 + insight_h
    draw.rounded_rectangle(
        [x0 + 2, y0 + 2, x1 + 2, y1 + 2],
        radius=CARD_RADIUS,
        fill=COL_SHADOW_SOFT,
    )
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=CARD_RADIUS,
        fill=COL_CARD,
        outline=COL_BORDER,
        width=1,
    )
    bar_x0 = x0 + CARD_PAD // 2
    draw.rectangle(
        [bar_x0, y0 + CARD_PAD, bar_x0 + INSIGHT_BAR_W, y1 - CARD_PAD],
        fill=COL_INSIGHT_BAR,
    )
    text_left = bar_x0 + INSIGHT_BAR_W + 14
    ty = y0 + CARD_PAD
    draw.text((text_left, ty), "サマリ", font=fonts.label, fill=COL_INSIGHT_LABEL)
    label_lh = _text_line_height(fonts.label, draw)
    ty += label_lh + 12
    body_lh = _text_line_height(fonts.body, draw)
    for i, line in enumerate(bl):
        st = line.strip()
        is_bullet = bool(_BULLET_LINE_RE.match(st))
        disp = _BULLET_LINE_RE.sub("", st, count=1) if is_bullet else line
        bx_off = 0
        if is_bullet:
            cr = 4
            cx = text_left + cr
            cy_dot = ty + body_lh // 2
            draw.ellipse([cx - cr, cy_dot - cr, cx + cr, cy_dot + cr], fill=COL_INSIGHT_BAR)
            bx_off = 18
        col = COL_MUTED if not disp.strip() else COL_TEXT
        draw.text((text_left + bx_off, ty), disp, font=fonts.body, fill=col)
        ty += body_lh + (LINE_GAP_TIGHT if i < len(bl) - 1 else 0)


def _draw_section_card(
    draw: ImageDraw.ImageDraw,
    x0_card: int,
    y0: int,
    x1_card: int,
    card_h: int,
    accent: str,
    hd: str | None,
    hl: List[str],
    bl: List[str],
    fonts: _FontSet,
    step_n: int | None,
) -> None:
    y1 = y0 + card_h
    x1 = x1_card
    content_left, content_w = _card_content_box(x0_card, x1_card)

    draw.rounded_rectangle(
        [x0_card + 2, y0 + 2, x1 + 2, y1 + 2],
        radius=CARD_RADIUS,
        fill=COL_SHADOW_SOFT,
    )
    draw.rounded_rectangle(
        [x0_card, y0, x1, y1],
        radius=CARD_RADIUS,
        fill=COL_CARD,
        outline=COL_BORDER,
        width=1,
    )
    bar_left = x0_card + CARD_PAD // 2
    draw.rounded_rectangle(
        [bar_left, y0 + CARD_PAD, bar_left + ACCENT_BAR_W, y1 - CARD_PAD],
        radius=2,
        fill=accent,
    )

    sec_lh = _text_line_height(fonts.section, draw)
    body_lh = _text_line_height(fonts.body, draw)
    cy = y0 + CARD_PAD

    if hd and hl and step_n is not None:
        px1 = content_left + STEP_PILL_W
        py1 = cy + STEP_PILL_H
        draw.rounded_rectangle(
            [content_left, cy, px1, py1],
            radius=8,
            fill=COL_PILL_BG,
            outline=accent,
            width=2,
        )
        num = str(step_n)
        bb = draw.textbbox((0, 0), num, font=fonts.badge)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        draw.text(
            (content_left + (STEP_PILL_W - tw) // 2, cy + (STEP_PILL_H - th) // 2 - 1),
            num,
            font=fonts.badge,
            fill=accent,
        )
        tx = content_left + STEP_PILL_W + 10
        v_off = max(0, (STEP_PILL_H - sec_lh) // 2)
        title_y = cy + v_off
        for i, line in enumerate(hl):
            draw.text((tx, title_y), line, font=fonts.section, fill=COL_TEXT)
            title_y += sec_lh + (LINE_GAP_TIGHT if i < len(hl) - 1 else 0)
        title_used_h = max(STEP_PILL_H, _measure_block_height(hl, sec_lh, LINE_GAP_TIGHT))
        inner_y0 = y0 + CARD_PAD + title_used_h + TITLE_GAP_AFTER_PILL
    elif hd and hl:
        tx = content_left
        title_y = cy
        for i, line in enumerate(hl):
            draw.text((tx, title_y), line, font=fonts.section, fill=COL_TEXT)
            title_y += sec_lh + (LINE_GAP_TIGHT if i < len(hl) - 1 else 0)
        title_used_h = _measure_block_height(hl, sec_lh, LINE_GAP_TIGHT)
        inner_y0 = y0 + CARD_PAD + title_used_h + TITLE_GAP_AFTER_PILL
    else:
        inner_y0 = y0 + CARD_PAD

    inner_y1 = y1 - CARD_PAD
    draw.rounded_rectangle(
        [content_left, inner_y0, content_left + content_w, inner_y1],
        radius=INNER_RADIUS,
        fill=COL_CARD_INNER,
        outline=COL_BORDER_SOFT,
        width=1,
    )

    txb = content_left + INNER_PAD
    tyb = inner_y0 + INNER_PAD
    for i, line in enumerate(bl):
        st = line.strip()
        is_bullet = bool(_BULLET_LINE_RE.match(st))
        disp = _BULLET_LINE_RE.sub("", st, count=1) if is_bullet else line
        bx_off = 0
        if is_bullet:
            cr = 5
            cx = txb + cr
            cy_dot = tyb + body_lh // 2
            draw.ellipse([cx - cr, cy_dot - cr, cx + cr, cy_dot + cr], fill=accent)
            bx_off = 20
        if not disp.strip():
            col = COL_MUTED
        else:
            col = COL_TEXT
        draw.text((txb + bx_off, tyb), disp, font=fonts.body, fill=col)
        tyb += body_lh + (LINE_GAP_TIGHT if i < len(bl) - 1 else 0)


def render_summary_png(
    meeting_info: Dict[str, Any],
    summary_text: str,
    *,
    width: int = DEFAULT_WIDTH,
) -> bytes:
    fonts = _load_font_set()

    draft = Image.new("RGB", (width, 40))
    draw_d = ImageDraw.Draw(draft)
    inner_hero_w = width - 2 * HERO_PAD_X
    _x0g, _x1g = MARGIN, width - MARGIN
    _, content_w = _card_content_box(_x0g, _x1g)

    name = _strip_inline_markdown(str(meeting_info.get("name") or "（無題）"))
    happened = format_happened_at_display(
        str(meeting_info.get("happened_at") or "").strip() or None
    )

    kicker_lh = _text_line_height(fonts.kicker, draw_d)
    title_lh = _text_line_height(fonts.title, draw_d)
    date_lh = _text_line_height(fonts.date, draw_d)

    kicker_lines = _wrap_to_width(
        draw_d, "VISUAL GUIDE  ·  議事サマリー", fonts.kicker, inner_hero_w
    )
    title_lines = _wrap_to_width(draw_d, name, fonts.title, inner_hero_w)
    date_lines = (
        _wrap_to_width(draw_d, happened, fonts.date, inner_hero_w) if happened else []
    )

    hero_content_h = (
        _measure_block_height(kicker_lines, kicker_lh, LINE_GAP_TIGHT)
        + 14
        + _measure_block_height(title_lines, title_lh, LINE_GAP_TIGHT)
        + (
            10 + _measure_block_height(date_lines, date_lh, LINE_GAP_TIGHT)
            if date_lines
            else 0
        )
        + 22
        + HERO_ACCENT_LINE_H
    )
    hero_h = HERO_PAD_TOP + hero_content_h + HERO_PAD_BOTTOM

    sections = parse_summary_sections(summary_text)
    rest_sections, insight_body = _split_insight_section(sections)

    sec_lh_d = _text_line_height(fonts.section, draw_d)
    body_lh_d = _text_line_height(fonts.body, draw_d)
    label_lh_d = _text_line_height(fonts.label, draw_d)

    insight_bl: List[str] = []
    insight_h = 0
    if insight_body:
        insight_bl, insight_h = _measure_insight_block(
            draw_d, insight_body, fonts, content_w, label_lh_d, body_lh_d
        )

    prepared: List[Tuple[str | None, str, List[str], List[str], int, str, int | None]] = []
    step_counter = 0
    for idx, (hd, body) in enumerate(rest_sections):
        hl, bl, card_h = _measure_section_card(
            draw_d, hd, body, fonts, content_w, sec_lh_d, body_lh_d
        )
        accent = COL_ACCENTS[idx % len(COL_ACCENTS)]
        sn: int | None = None
        if hd:
            step_counter += 1
            sn = step_counter
        prepared.append((hd, body, hl, bl, card_h, accent, sn))

    flow_row_h = body_lh_d + FLOW_ARROW_GAP * 2
    flow_extra = flow_row_h * max(0, len(prepared) - 1)

    body_stack_h = CONTENT_TOP_GAP
    if insight_body and insight_bl:
        body_stack_h += insight_h + CARD_GAP
    if prepared:
        body_stack_h += flow_extra + sum(p[4] + CARD_GAP for p in prepared) - CARD_GAP
    body_stack_h += MARGIN
    total_h = hero_h + body_stack_h

    body_lh_m = _text_line_height(fonts.body, draw_d)
    sec_lh_m = _text_line_height(fonts.section, draw_d)
    keep_insight = bool(insight_body and insight_bl)

    if total_h > MAX_IMAGE_HEIGHT:
        notice_lines = _wrap_to_width(
            draw_d,
            TRUNCATION_NOTICE.strip(),
            fonts.body,
            max(100, content_w - 2 * INNER_PAD),
        )
        avail_total = MAX_IMAGE_HEIGHT - hero_h - CONTENT_TOP_GAP - MARGIN
        used = 0
        if keep_insight and insight_h + CARD_GAP <= avail_total:
            used = insight_h + CARD_GAP
        elif keep_insight:
            keep_insight = False
            insight_bl = []
            insight_h = 0

        card_avail = avail_total - used
        final_prep: List[
            Tuple[str | None, str, List[str], List[str], int, str, int | None]
        ] = []
        used_c = 0
        for hd, body, hl, bl, _och, accent, sn in prepared:
            prefix = (CARD_GAP + flow_row_h) if final_prep else 0
            full_card = _card_height_from_lines(hd, hl, bl, sec_lh_m, body_lh_m)
            if used_c + prefix + full_card <= card_avail:
                final_prep.append((hd, body, hl, bl, full_card, accent, sn))
                used_c += prefix + full_card
                continue

            room = card_avail - used_c - prefix
            trimmed = list(bl)
            while trimmed and _card_height_from_lines(
                hd, hl, trimmed + notice_lines, sec_lh_m, body_lh_m
            ) > room:
                trimmed.pop()
            bl2 = trimmed + notice_lines
            card_h = _card_height_from_lines(hd, hl, bl2, sec_lh_m, body_lh_m)
            if card_h <= room:
                final_prep.append((hd, body, hl, bl2, card_h, accent, sn))
            break

        if not final_prep and prepared:
            hd0, body0, hl0, _, _, accent0, sn0 = prepared[0]
            bl_fallback = notice_lines
            ch0 = _card_height_from_lines(hd0, hl0, bl_fallback, sec_lh_m, body_lh_m)
            if ch0 > card_avail:
                hd0, hl0, sn0 = None, [], None
                ch0 = _card_height_from_lines(hd0, hl0, bl_fallback, sec_lh_m, body_lh_m)
            final_prep = [(hd0, body0, hl0, bl_fallback, ch0, accent0, sn0)]

        prepared = final_prep
        flow_extra2 = flow_row_h * max(0, len(prepared) - 1)
        body_stack_h = CONTENT_TOP_GAP + MARGIN
        if keep_insight and insight_bl:
            body_stack_h += insight_h + CARD_GAP
        if prepared:
            body_stack_h += flow_extra2 + sum(p[4] + CARD_GAP for p in prepared) - CARD_GAP
        total_h = min(hero_h + body_stack_h, MAX_IMAGE_HEIGHT)

    img = Image.new("RGB", (width, total_h), COL_PAGE_BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, hero_h], fill=COL_HERO_BG)

    y = HERO_PAD_TOP
    x_text = HERO_PAD_X
    for i, line in enumerate(kicker_lines):
        draw.text((x_text, y), line, font=fonts.kicker, fill=COL_MUTED_ON_HERO)
        y += kicker_lh + (LINE_GAP_TIGHT if i < len(kicker_lines) - 1 else 0)
    y += 14

    for i, line in enumerate(title_lines):
        draw.text((x_text, y), line, font=fonts.title, fill=COL_TEXT_ON_HERO)
        y += title_lh + (LINE_GAP_TIGHT if i < len(title_lines) - 1 else 0)

    if date_lines:
        y += 10
        for i, line in enumerate(date_lines):
            draw.text((x_text, y), line, font=fonts.date, fill=COL_MUTED_ON_HERO)
            y += date_lh + (LINE_GAP_TIGHT if i < len(date_lines) - 1 else 0)

    draw.rectangle(
        [0, hero_h - HERO_ACCENT_LINE_H, width, hero_h],
        fill=COL_HERO_LINE,
    )

    y = hero_h + CONTENT_TOP_GAP
    x0_card = MARGIN
    x1_card = width - MARGIN

    if keep_insight and insight_bl:
        _draw_insight_block(draw, x0_card, y, x1_card, insight_h, insight_bl, fonts)
        y += insight_h + CARD_GAP

    for i, (hd, _body, hl, bl, card_h, accent, sn) in enumerate(prepared):
        if i > 0:
            bb = draw.textbbox((0, 0), "▼", font=fonts.body)
            tw = bb[2] - bb[0]
            draw.text(
                ((width - tw) // 2, y + FLOW_ARROW_GAP),
                "▼",
                font=fonts.body,
                fill=COL_FLOW_MARK,
            )
            y += flow_row_h
        _draw_section_card(
            draw,
            x0_card,
            y,
            x1_card,
            card_h,
            accent,
            hd,
            hl,
            bl,
            fonts,
            sn,
        )
        y += card_h + CARD_GAP

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
