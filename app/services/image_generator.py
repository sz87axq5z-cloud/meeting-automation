"""
Claude の要約テキストを議事サマリー用 PNG にレンダリングする。
ダークヒーロー + サマリ帯 + 円形ステップ + タグ付きカードのドキュメント調 UI（1200px 基準、モック PNG に近いサイズ感）。
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
from collections import OrderedDict
from typing import Any, Dict, List, Tuple

import certifi
from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.formatting import format_happened_at_display, normalize_western_number_commas

logger = logging.getLogger(__name__)

# モック寄せ: ページはやや青みのグレー
COL_PAGE_BG = "#e8edf3"
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
COL_CHIP_BG = "#334155"
COL_CHIP_BORDER = "#475569"
COL_BADGE_OK_BG = "#d1fae5"
COL_BADGE_OK_FG = "#059669"
COL_TAG_BG = "#f1f5f9"
COL_TAG_FG = "#475569"

COL_ACCENTS: Tuple[str, ...] = (
    "#2563eb",
    "#0ea5e9",
    "#7c3aed",
    "#0891b2",
    "#0369a1",
    "#6366f1",
)

LAYOUT_BASE = 1080
DEFAULT_WIDTH = 1200

MARGIN = 48
HERO_PAD_X = 52
HERO_PAD_TOP = 38
HERO_PAD_BOTTOM = 34
HERO_ACCENT_LINE_H = 4
CONTENT_TOP_GAP = 30
CARD_GAP = 22
CARD_PAD = 26
CARD_RADIUS = 14
ACCENT_BAR_W = 4
BAR_TO_TEXT_GAP = 12
TITLE_GAP_AFTER_PILL = 16
INNER_PAD = 22
INNER_RADIUS = 10
INSIGHT_BAR_W = 5
FLOW_ARROW_GAP = 8
KICKER_SIZE = 16
MEETING_TITLE_SIZE = 42
DATE_SIZE = 20
SECTION_SIZE = 26
BODY_SIZE = 22
BADGE_NUM_SIZE = 16
INSIGHT_LABEL_SIZE = 16
CHIP_TEXT_SIZE = 13
TAG_TEXT_SIZE = 11
FOOTER_TEXT_SIZE = 10
LINE_GAP_TIGHT = 9
LINE_GAP_SECTION = 11
MAX_IMAGE_HEIGHT = 14_000
TRUNCATION_NOTICE = "\n\n…（画像の高さ上限のため省略）"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BUNDLED_JP_FONT_CANDIDATES: Tuple[Path, ...] = (
    _PROJECT_ROOT / "fonts" / "NotoSansJP-Regular.otf",
    _PROJECT_ROOT / "fonts" / "NotoSansCJKjp-Regular.otf",
)
_BUNDLED_JP_FONT_BOLD_CANDIDATES: Tuple[Path, ...] = (
    _PROJECT_ROOT / "fonts" / "NotoSansJP-Bold.otf",
    _PROJECT_ROOT / "fonts" / "NotoSansCJKjp-Bold.otf",
)
_EMPHASIS_FONT_CANDIDATES: Tuple[str, ...] = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc",
    "/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/Library/Fonts/ヒラギノ角ゴシック W7.ttc",
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


@dataclass(frozen=True)
class _Layout:
    width: int
    margin: int
    hero_pad_x: int
    hero_pad_top: int
    hero_pad_bottom: int
    hero_accent_h: int
    hero_title_to_chips: int
    content_top_gap: int
    card_gap: int
    card_pad: int
    card_radius: int
    accent_bar_w: int
    bar_to_text_gap: int
    step_ring_d: int
    title_gap_after_step: int
    inner_pad: int
    inner_radius: int
    insight_bar_w: int
    flow_arrow_gap: int
    flow_line_h: int
    chip_pad_x: int
    chip_pad_y: int
    chip_gap: int
    badge_pad_x: int
    badge_pad_y: int
    tag_pill_pad_x: int
    tag_pill_pad_y: int
    footer_h: int
    chip_radius: int


def _layout_for(width: int) -> _Layout:
    def sx(x: int) -> int:
        return max(1, int(round(x * width / LAYOUT_BASE)))

    return _Layout(
        width=width,
        margin=sx(MARGIN),
        hero_pad_x=sx(HERO_PAD_X),
        hero_pad_top=sx(HERO_PAD_TOP),
        hero_pad_bottom=sx(HERO_PAD_BOTTOM),
        hero_accent_h=sx(HERO_ACCENT_LINE_H),
        hero_title_to_chips=sx(18),
        content_top_gap=sx(CONTENT_TOP_GAP),
        card_gap=sx(CARD_GAP),
        card_pad=sx(CARD_PAD),
        card_radius=sx(CARD_RADIUS),
        accent_bar_w=sx(ACCENT_BAR_W),
        bar_to_text_gap=sx(BAR_TO_TEXT_GAP),
        step_ring_d=sx(44),
        title_gap_after_step=sx(TITLE_GAP_AFTER_PILL),
        inner_pad=sx(INNER_PAD),
        inner_radius=sx(INNER_RADIUS),
        insight_bar_w=sx(INSIGHT_BAR_W),
        flow_arrow_gap=sx(FLOW_ARROW_GAP),
        flow_line_h=sx(14),
        chip_pad_x=sx(12),
        chip_pad_y=sx(8),
        chip_gap=sx(10),
        badge_pad_x=sx(10),
        badge_pad_y=sx(4),
        tag_pill_pad_x=sx(10),
        tag_pill_pad_y=sx(4),
        footer_h=sx(36),
        chip_radius=sx(8),
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


def _bold_sibling_path(regular_path: str) -> Path | None:
    """Noto 等の Regular パスから同階層の Bold を推測する。"""
    p = Path(regular_path)
    if not p.name:
        return None
    name = p.name
    for old, new in (
        ("CJKjp-Regular", "CJKjp-Bold"),
        ("Regular.otf", "Bold.otf"),
        ("-Regular.otf", "-Bold.otf"),
        ("Regular", "Bold"),
    ):
        if old in name:
            return p.with_name(name.replace(old, new, 1))
    return None


def _resolve_emphasis_font(size: int) -> Tuple[ImageFont.FreeTypeFont, bool]:
    """
    見出し・KPI 数値向けのやや強いウェイト。
    見つからなければ _resolve_font と同じ（Regular）にフォールバック。
    """
    env_bold = (
        settings.summary_font_bold_path
        or os.environ.get("SUMMARY_FONT_BOLD_PATH")
        or ""
    ).strip()
    if env_bold and Path(env_bold).is_file():
        try:
            return _truetype(env_bold, size), False
        except OSError:
            logger.warning("SUMMARY_FONT_BOLD_PATH が読めません: %s", env_bold)

    for bundled in _BUNDLED_JP_FONT_BOLD_CANDIDATES:
        if bundled.is_file():
            try:
                return _truetype(str(bundled), size), False
            except OSError:
                logger.warning("同梱太字フォントが読めません: %s", bundled)

    reg = (settings.summary_font_path or os.environ.get("SUMMARY_FONT_PATH") or "").strip()
    if reg:
        sib = _bold_sibling_path(reg)
        if sib is not None and sib.is_file():
            try:
                return _truetype(str(sib), size), False
            except OSError:
                logger.warning("Regular に対応する Bold が読めません: %s", sib)

    for candidate in _EMPHASIS_FONT_CANDIDATES:
        if Path(candidate).is_file():
            try:
                return _truetype(candidate, size), False
            except OSError:
                continue

    return _resolve_font(size)


def _font_px(width: int, base: int) -> int:
    return max(8, int(round(base * width / LAYOUT_BASE)))


@dataclass(frozen=True)
class _FontSet:
    kicker: ImageFont.ImageFont
    title: ImageFont.ImageFont
    date: ImageFont.ImageFont
    section: ImageFont.ImageFont
    body: ImageFont.ImageFont
    badge: ImageFont.ImageFont
    label: ImageFont.ImageFont
    chip: ImageFont.ImageFont
    tag: ImageFont.ImageFont
    footer: ImageFont.ImageFont


def _load_font_set(width: int) -> _FontSet:
    def px(base: int) -> int:
        return _font_px(width, base)

    k, _ = _resolve_font(px(KICKER_SIZE))
    t, _ = _resolve_emphasis_font(px(MEETING_TITLE_SIZE))
    d, _ = _resolve_font(px(DATE_SIZE))
    s, _ = _resolve_emphasis_font(px(SECTION_SIZE))
    b, _ = _resolve_font(px(BODY_SIZE))
    bg, _ = _resolve_font(px(BADGE_NUM_SIZE))
    lb, _ = _resolve_emphasis_font(px(INSIGHT_LABEL_SIZE))
    ch, _ = _resolve_font(px(CHIP_TEXT_SIZE))
    tg, _ = _resolve_font(px(TAG_TEXT_SIZE))
    ft, _ = _resolve_font(px(FOOTER_TEXT_SIZE))
    return _FontSet(
        kicker=k,
        title=t,
        date=d,
        section=s,
        body=b,
        badge=bg,
        label=lb,
        chip=ch,
        tag=tg,
        footer=ft,
    )


def _strip_inline_markdown(text: str) -> str:
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    return t.strip()


_MERMAID_FENCE_PNG_RE = re.compile(r"```\s*mermaid\s*\n[\s\S]*?```", re.IGNORECASE)

# PNG レンダラは Mermaid を描画しないため除去し、HTML 版を参照する一文に置く。
_MERMAID_PLACEHOLDER_JA = (
    "\n\n（この付近の処理フローは HTML 版の図で示しています。）\n\n"
)


def strip_mermaid_fences_for_png(text: str) -> str:
    if not text or not _MERMAID_FENCE_PNG_RE.search(text):
        return text
    return _MERMAID_FENCE_PNG_RE.sub(_MERMAID_PLACEHOLDER_JA, text)


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


def _tags_for_heading(hd: str | None) -> List[str]:
    if not hd:
        return []
    h = hd
    if "決定" in h:
        return ["スコープ設定", "デザイン"][:2]
    if "課題" in h or "リスク" in h:
        return ["コスト", "インフラ"][:2]
    if "タスク" in h:
        return ["開発期間", "範囲"][:2]
    if "概要" in h:
        return ["共有", "前提"][:2]
    return ["項目", "関連"][:2]


def _summary_badge_text(body: str) -> str:
    b = body or ""
    if "改善" in b or "提案" in b:
        return "改善案有"
    if "リスク" in b or "課題" in b:
        return "注意"
    if "合意" in b or "決定" in b:
        return "合意形成"
    return "要約"


def _truncate_text_to_pixel_width(
    draw_d: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_inner_w: int,
) -> str:
    """チップ1枚の横幅に収まるよう末尾を「…」付きで切り詰める。"""
    tw = lambda s: draw_d.textbbox((0, 0), s, font=font)[2] - draw_d.textbbox(
        (0, 0), s, font=font
    )[0]
    if tw(text) <= max_inner_w:
        return text
    ell = "…"
    if tw(ell) > max_inner_w:
        return ell
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        cand = text[:mid].rstrip() + ell
        if tw(cand) <= max_inner_w:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo].rstrip() + ell) if lo > 0 else ell


def _participant_chip_text(
    meeting_info: Dict[str, Any],
    draw_d: ImageDraw.ImageDraw,
    chip_font: ImageFont.ImageFont,
    max_chip_inner_w: int,
) -> str:
    """「参加者 N名 · 名前1、名前2…」形式（名前は meeting_info['participants']）。"""
    p = meeting_info.get("participants")
    if not isinstance(p, list):
        return "参加者 —"
    names = [str(x).strip() for x in p if str(x).strip()]
    if not names:
        return "参加者 —"
    n = len(names)
    joined = "、".join(names)
    full = f"参加者 {n}名 · {joined}"
    return _truncate_text_to_pixel_width(draw_d, full, chip_font, max_chip_inner_w)


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


def _content_inner_width(lt: _Layout) -> int:
    return lt.width - 2 * lt.margin


def _card_content_box(x0_card: int, x1_card: int, lt: _Layout) -> Tuple[int, int]:
    left = x0_card + lt.card_pad + lt.accent_bar_w + lt.bar_to_text_gap
    w = x1_card - lt.card_pad - left
    return left, w


_BULLET_LINE_RE = re.compile(r"^[\-\*・]\s*")
_ORDERED_LINE_RE = re.compile(r"^\s*(\d+)[\.\)]\s*(.*)$")
_TASK_SECTION_HD_RE = re.compile(r"タスク|TODO", re.I)
_TASK_ASSIGN_BOLD_REST = re.compile(r"^\*\*([^*]+)\*\*\s*[-–—]\s*(.+)$")
_TASK_ASSIGN_PLAIN_REST = re.compile(r"^([^*].+?)\s+[-–—]\s+(.+)$")


def _group_task_section_body(hd: str | None, body: str) -> str:
    """
    「## タスク一覧」相当のセクションで、同じ担当の行をまとめる。
    入力: 1. **名前** - 内容 - 期限
    出力: 名前\\n- 内容 - 期限\\n- …（担当の初出順）
    """
    if not (body or "").strip():
        return body
    h = (hd or "").strip()
    if not h or not _TASK_SECTION_HD_RE.search(h):
        return body

    lines = body.replace("\r\n", "\n").split("\n")
    groups: OrderedDict[str, List[str]] = OrderedDict()
    parsed = 0
    non_empty_unparsed = 0

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        om = _ORDERED_LINE_RE.match(line)
        if not om:
            non_empty_unparsed += 1
            continue
        rest = (om.group(2) or "").strip()
        mb = _TASK_ASSIGN_BOLD_REST.match(rest)
        if mb:
            name = _strip_inline_markdown(mb.group(1).strip())
            detail = _strip_inline_markdown(mb.group(2).strip())
            if name not in groups:
                groups[name] = []
            groups[name].append(detail)
            parsed += 1
            continue
        mp = _TASK_ASSIGN_PLAIN_REST.match(rest)
        if mp and not mp.group(1).strip().startswith("**"):
            name = _strip_inline_markdown(mp.group(1).strip())
            detail = _strip_inline_markdown(mp.group(2).strip())
            if name not in groups:
                groups[name] = []
            groups[name].append(detail)
            parsed += 1
            continue
        non_empty_unparsed += 1

    if parsed == 0 or non_empty_unparsed > 0:
        return body

    out: List[str] = []
    for i, (name, items) in enumerate(groups.items()):
        if i > 0:
            out.append("")
        out.append(name)
        for it in items:
            out.append(f"- {it}")
    return "\n".join(out)


def _followed_by_bullet_line(bl: List[str], idx: int) -> bool:
    """次の非空行が箇条書きなら True（タスク担当見出しの判定用）。"""
    for j in range(idx + 1, len(bl)):
        s2 = bl[j].strip()
        if not s2:
            continue
        return bool(_BULLET_LINE_RE.match(s2))
    return False


def _tag_row_height(draw_d: ImageDraw.ImageDraw, tags: List[str], fonts: _FontSet) -> int:
    if not tags:
        return 0
    th = _text_line_height(fonts.tag, draw_d)
    return th + 10


def _measure_section_card(
    draw_d: ImageDraw.ImageDraw,
    hd: str | None,
    body: str,
    fonts: _FontSet,
    content_w: int,
    lt: _Layout,
    sec_lh: int,
    body_lh: int,
) -> Tuple[List[str], List[str], int]:
    d = lt.step_ring_d
    title_max = content_w - d - lt.bar_to_text_gap if hd else content_w
    hl = _wrap_to_width(draw_d, hd, fonts.section, title_max) if hd else []
    inner_text_w = max(100, content_w - 2 * lt.inner_pad)
    body_eff = _group_task_section_body(hd, body)
    bl = _wrap_to_width(draw_d, body_eff, fonts.body, inner_text_w)
    tags = _tags_for_heading(hd)
    tag_rh = _tag_row_height(draw_d, tags, fonts)

    if hd:
        title_h = _measure_block_height(hl, sec_lh, LINE_GAP_TIGHT)
        title_block_h = max(d, title_h) + (8 + tag_rh if tags else 0)
        top_stack = lt.card_pad + title_block_h + lt.title_gap_after_step
    else:
        top_stack = lt.card_pad

    body_h = _measure_block_height(bl, body_lh, LINE_GAP_TIGHT)
    inner_h = 2 * lt.inner_pad + body_h
    card_h = top_stack + inner_h + lt.card_pad
    return hl, bl, card_h


def _card_height_from_lines(
    hd: str | None,
    hl: List[str],
    bl: List[str],
    lt: _Layout,
    sec_lh: int,
    body_lh: int,
    tag_rh: int,
) -> int:
    d = lt.step_ring_d
    if hd:
        title_h = _measure_block_height(hl, sec_lh, LINE_GAP_TIGHT)
        title_block_h = max(d, title_h) + (8 + tag_rh if tag_rh else 0)
        top_stack = lt.card_pad + title_block_h + lt.title_gap_after_step
    else:
        top_stack = lt.card_pad
    body_h = _measure_block_height(bl, body_lh, LINE_GAP_TIGHT)
    return top_stack + 2 * lt.inner_pad + body_h + lt.card_pad


def _measure_insight_block(
    draw_d: ImageDraw.ImageDraw,
    body: str,
    insight_raw: str,
    fonts: _FontSet,
    content_w: int,
    lt: _Layout,
    label_lh: int,
    body_lh: int,
) -> Tuple[List[str], int]:
    inner_text_w = max(100, content_w - 2 * lt.card_pad - lt.insight_bar_w - lt.bar_to_text_gap)
    bl = _wrap_to_width(draw_d, body, fonts.body, inner_text_w)
    body_h = _measure_block_height(bl, body_lh, LINE_GAP_TIGHT)
    badge = _summary_badge_text(insight_raw)
    bb = draw_d.textbbox((0, 0), badge, font=fonts.tag)
    badge_h = bb[3] - bb[1] + 2 * lt.badge_pad_y
    header_h = max(label_lh, badge_h)
    h = lt.card_pad + header_h + 14 + body_h + lt.card_pad
    return bl, h


def _measure_chip_row(
    draw_d: ImageDraw.ImageDraw,
    texts: List[str],
    fonts: _FontSet,
    max_w: int,
    lt: _Layout,
) -> int:
    if not texts:
        return 0
    ch_lh = _text_line_height(fonts.chip, draw_d)
    row_h = ch_lh + 2 * lt.chip_pad_y
    x = 0
    rows = 1
    gap = lt.chip_gap
    for t in texts:
        tw = draw_d.textbbox((0, 0), t, font=fonts.chip)[2] - draw_d.textbbox(
            (0, 0), t, font=fonts.chip
        )[0]
        w = tw + 2 * lt.chip_pad_x
        if x + w > max_w and x > 0:
            rows += 1
            x = w + gap
        else:
            x += w + gap
    return rows * row_h + (rows - 1) * gap


def _draw_chip_row(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    max_w: int,
    texts: List[str],
    fonts: _FontSet,
    lt: _Layout,
) -> int:
    if not texts:
        return y0
    ch_lh = _text_line_height(fonts.chip, draw)
    row_h = ch_lh + 2 * lt.chip_pad_y
    cx = x0
    cy = y0
    gap = lt.chip_gap
    for t in texts:
        tw = draw.textbbox((0, 0), t, font=fonts.chip)[2] - draw.textbbox(
            (0, 0), t, font=fonts.chip
        )[0]
        w = tw + 2 * lt.chip_pad_x
        if cx + w > x0 + max_w and cx > x0:
            cx = x0
            cy += row_h + gap
        x1b = cx + w
        y1b = cy + row_h
        draw.rounded_rectangle(
            [cx, cy, x1b, y1b],
            radius=lt.chip_radius,
            fill=COL_CHIP_BG,
            outline=COL_CHIP_BORDER,
            width=1,
        )
        draw.text(
            (cx + lt.chip_pad_x, cy + lt.chip_pad_y),
            t,
            font=fonts.chip,
            fill=COL_MUTED_ON_HERO,
        )
        cx = x1b + gap
    return cy + row_h


def _draw_insight_block(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    x1: int,
    insight_h: int,
    insight_raw: str,
    bl: List[str],
    fonts: _FontSet,
    lt: _Layout,
) -> None:
    y1 = y0 + insight_h
    draw.rounded_rectangle(
        [x0 + 2, y0 + 2, x1 + 2, y1 + 2],
        radius=lt.card_radius,
        fill=COL_SHADOW_SOFT,
    )
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=lt.card_radius,
        fill=COL_CARD,
        outline=COL_BORDER,
        width=1,
    )
    bar_x0 = x0 + lt.card_pad // 2
    draw.rectangle(
        [bar_x0, y0 + lt.card_pad, bar_x0 + lt.insight_bar_w, y1 - lt.card_pad],
        fill=COL_INSIGHT_BAR,
    )
    text_left = bar_x0 + lt.insight_bar_w + lt.bar_to_text_gap
    ty = y0 + lt.card_pad
    label_lh = _text_line_height(fonts.label, draw)
    badge = _summary_badge_text(insight_raw)
    bb = draw.textbbox((0, 0), badge, font=fonts.tag)
    bw = bb[2] - bb[0]
    bh = bb[3] - bb[1]
    pill_w = bw + 2 * lt.badge_pad_x
    pill_h = bh + 2 * lt.badge_pad_y
    pill_x1 = x1 - lt.card_pad
    pill_x0 = pill_x1 - pill_w
    draw.rounded_rectangle(
        [pill_x0, ty, pill_x1, ty + pill_h],
        radius=max(4, lt.chip_radius),
        fill=COL_BADGE_OK_BG,
        outline=COL_BADGE_OK_FG,
        width=1,
    )
    draw.text(
        (pill_x0 + lt.badge_pad_x, ty + lt.badge_pad_y),
        badge,
        font=fonts.tag,
        fill=COL_BADGE_OK_FG,
    )
    draw.text((text_left, ty), "サマリ", font=fonts.label, fill=COL_INSIGHT_LABEL)
    ty += max(label_lh, pill_h) + 14
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


def _draw_flow_row(
    draw: ImageDraw.ImageDraw,
    width: int,
    y: int,
    fonts: _FontSet,
    lt: _Layout,
) -> int:
    sec_lh = _text_line_height(fonts.section, draw)
    row_h = lt.flow_line_h + lt.flow_arrow_gap * 2 + sec_lh
    cx = width // 2
    y_line_top = y + lt.flow_arrow_gap
    y_line_bot = y_line_top + lt.flow_line_h
    draw.line([(cx, y_line_top), (cx, y_line_bot)], fill=COL_FLOW_MARK, width=max(1, lt.accent_bar_w))
    bb = draw.textbbox((0, 0), "▼", font=fonts.section)
    tw = bb[2] - bb[0]
    draw.text(
        ((width - tw) // 2, y_line_bot + lt.flow_arrow_gap),
        "▼",
        font=fonts.section,
        fill=COL_FLOW_MARK,
    )
    return row_h


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
    lt: _Layout,
    step_n: int | None,
) -> None:
    y1 = y0 + card_h
    x1 = x1_card
    content_left, content_w = _card_content_box(x0_card, x1_card, lt)
    tags = _tags_for_heading(hd)

    draw.rounded_rectangle(
        [x0_card + 2, y0 + 2, x1 + 2, y1 + 2],
        radius=lt.card_radius,
        fill=COL_SHADOW_SOFT,
    )
    draw.rounded_rectangle(
        [x0_card, y0, x1, y1],
        radius=lt.card_radius,
        fill=COL_CARD,
        outline=COL_BORDER,
        width=1,
    )
    bar_left = x0_card + lt.card_pad // 2
    draw.rounded_rectangle(
        [bar_left, y0 + lt.card_pad, bar_left + lt.accent_bar_w, y1 - lt.card_pad],
        radius=2,
        fill=accent,
    )

    sec_lh = _text_line_height(fonts.section, draw)
    body_lh = _text_line_height(fonts.body, draw)
    cy = y0 + lt.card_pad
    d = lt.step_ring_d
    gap = lt.bar_to_text_gap

    if hd and hl and step_n is not None:
        cxm = content_left + d // 2
        cym = cy + d // 2
        r = d // 2
        lw = max(2, min(4, lt.accent_bar_w + 1))
        draw.ellipse(
            [cxm - r, cym - r, cxm + r, cym + r],
            outline=accent,
            width=lw,
        )
        num = str(step_n)
        bb = draw.textbbox((0, 0), num, font=fonts.badge)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        draw.text(
            (cxm - tw // 2, cym - th // 2 - 1),
            num,
            font=fonts.badge,
            fill=accent,
        )
        tx = content_left + d + gap
        title_h = _measure_block_height(hl, sec_lh, LINE_GAP_TIGHT)
        title_y0 = cy + max(0, (d - title_h) // 2)
        title_y = title_y0
        for i, line in enumerate(hl):
            draw.text((tx, title_y), line, font=fonts.section, fill=COL_TEXT)
            title_y += sec_lh + (LINE_GAP_TIGHT if i < len(hl) - 1 else 0)
        title_used_h = max(d, title_h)
        tag_y = cy + title_used_h + 8
        tx_tag = tx
        for tg in tags:
            tbb = draw.textbbox((0, 0), tg, font=fonts.tag)
            twt = tbb[2] - tbb[0]
            p_w = twt + 2 * lt.tag_pill_pad_x
            p_h = tbb[3] - tbb[1] + 2 * lt.tag_pill_pad_y
            draw.rounded_rectangle(
                [tx_tag, tag_y, tx_tag + p_w, tag_y + p_h],
                radius=max(4, lt.chip_radius - 2),
                fill=COL_TAG_BG,
                outline=COL_BORDER_SOFT,
                width=1,
            )
            draw.text(
                (tx_tag + lt.tag_pill_pad_x, tag_y + lt.tag_pill_pad_y),
                tg,
                font=fonts.tag,
                fill=COL_TAG_FG,
            )
            tx_tag += p_w + gap
        inner_y0 = y0 + lt.card_pad + title_used_h + (8 + _tag_row_height(draw, tags, fonts) if tags else 0) + lt.title_gap_after_step
    elif hd and hl:
        tx = content_left
        title_y = cy
        for i, line in enumerate(hl):
            draw.text((tx, title_y), line, font=fonts.section, fill=COL_TEXT)
            title_y += sec_lh + (LINE_GAP_TIGHT if i < len(hl) - 1 else 0)
        title_used_h = _measure_block_height(hl, sec_lh, LINE_GAP_TIGHT)
        inner_y0 = y0 + lt.card_pad + title_used_h + lt.title_gap_after_step
    else:
        inner_y0 = y0 + lt.card_pad

    inner_y1 = y1 - lt.card_pad
    draw.rounded_rectangle(
        [content_left, inner_y0, content_left + content_w, inner_y1],
        radius=lt.inner_radius,
        fill=COL_CARD_INNER,
        outline=COL_BORDER_SOFT,
        width=1,
    )

    txb = content_left + lt.inner_pad
    tyb = inner_y0 + lt.inner_pad
    sq = max(16, body_lh - 2)
    task_hd = bool(hd and _TASK_SECTION_HD_RE.search(hd))
    for i, line in enumerate(bl):
        st = line.strip()
        mo = _ORDERED_LINE_RE.match(st)
        is_bullet = bool(_BULLET_LINE_RE.match(st)) if not mo else False
        if mo:
            _n, rest = mo.group(1), mo.group(2)
            disp = rest
            draw.rounded_rectangle(
                [txb, tyb + 1, txb + sq, tyb + sq + 1],
                radius=4,
                fill=accent,
            )
            nb = draw.textbbox((0, 0), _n, font=fonts.badge)
            nw, nh = nb[2] - nb[0], nb[3] - nb[1]
            draw.text(
                (txb + (sq - nw) // 2, tyb + (sq - nh) // 2),
                _n,
                font=fonts.badge,
                fill=COL_PILL_BG,
            )
            bx_off = sq + 10
        elif is_bullet:
            disp = _BULLET_LINE_RE.sub("", st, count=1)
            cr = 5
            cx = txb + cr
            cy_dot = tyb + body_lh // 2
            draw.ellipse([cx - cr, cy_dot - cr, cx + cr, cy_dot + cr], fill=accent)
            bx_off = 20
        else:
            disp = line
            bx_off = 0
        if not disp.strip():
            col = COL_MUTED
        elif (
            task_hd
            and not mo
            and not is_bullet
            and _followed_by_bullet_line(bl, i)
        ):
            col = COL_INSIGHT_LABEL
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
    summary_text = strip_mermaid_fences_for_png(summary_text or "")
    summary_text = normalize_western_number_commas(summary_text)

    lt = _layout_for(width)
    fonts = _load_font_set(width)

    draft = Image.new("RGB", (width, 40))
    draw_d = ImageDraw.Draw(draft)
    inner_hero_w = width - 2 * lt.hero_pad_x
    _x0g, _x1g = lt.margin, width - lt.margin
    _, content_w = _card_content_box(_x0g, _x1g, lt)

    name = _strip_inline_markdown(str(meeting_info.get("name") or "（無題）"))
    happened = format_happened_at_display(
        str(meeting_info.get("happened_at") or "").strip() or None
    )

    kicker_lh = _text_line_height(fonts.kicker, draw_d)
    title_lh = _text_line_height(fonts.title, draw_d)

    kicker_lines = _wrap_to_width(
        draw_d, "会議サマリー", fonts.kicker, inner_hero_w
    )
    title_lines = _wrap_to_width(draw_d, name, fonts.title, inner_hero_w)

    chip_max_inner = max(80, inner_hero_w - 2 * lt.chip_pad_x)
    chip_texts: List[str] = []
    if happened:
        chip_texts.append(happened)
    else:
        chip_texts.append("日時未設定")
    chip_texts.append(
        _participant_chip_text(meeting_info, draw_d, fonts.chip, chip_max_inner)
    )

    chip_area_h = _measure_chip_row(draw_d, chip_texts, fonts, inner_hero_w, lt)

    hero_content_h = (
        _measure_block_height(kicker_lines, kicker_lh, LINE_GAP_TIGHT)
        + 18
        + _measure_block_height(title_lines, title_lh, LINE_GAP_TIGHT)
        + lt.hero_title_to_chips
        + chip_area_h
        + 22
        + lt.hero_accent_h
    )
    hero_h = lt.hero_pad_top + hero_content_h + lt.hero_pad_bottom

    sections = parse_summary_sections(summary_text)
    rest_sections, insight_body = _split_insight_section(sections)

    sec_lh_d = _text_line_height(fonts.section, draw_d)
    body_lh_d = _text_line_height(fonts.body, draw_d)
    label_lh_d = _text_line_height(fonts.label, draw_d)

    insight_bl: List[str] = []
    insight_h = 0
    insight_raw = (insight_body or "").strip()
    if insight_body:
        insight_bl, insight_h = _measure_insight_block(
            draw_d,
            insight_body,
            insight_raw,
            fonts,
            content_w,
            lt,
            label_lh_d,
            body_lh_d,
        )

    prepared: List[Tuple[str | None, str, List[str], List[str], int, str, int | None]] = []
    step_counter = 0
    for idx, (hd, body) in enumerate(rest_sections):
        hl, bl, card_h = _measure_section_card(
            draw_d, hd, body, fonts, content_w, lt, sec_lh_d, body_lh_d
        )
        accent = COL_ACCENTS[idx % len(COL_ACCENTS)]
        sn: int | None = None
        if hd:
            step_counter += 1
            sn = step_counter
        prepared.append((hd, body, hl, bl, card_h, accent, sn))

    sec_lh_flow = _text_line_height(fonts.section, draw_d)
    flow_row_h = lt.flow_line_h + lt.flow_arrow_gap * 2 + sec_lh_flow
    num_flows = max(0, len(prepared) - 1) + (
        1 if (insight_bl and prepared) else 0
    )
    flow_extra = flow_row_h * num_flows

    body_stack_h = lt.content_top_gap
    if insight_body and insight_bl:
        body_stack_h += insight_h + lt.card_gap
    if prepared:
        body_stack_h += flow_extra + sum(p[4] + lt.card_gap for p in prepared) - lt.card_gap
    body_stack_h += lt.margin + lt.footer_h
    total_h = hero_h + body_stack_h

    body_lh_m = _text_line_height(fonts.body, draw_d)
    sec_lh_m = _text_line_height(fonts.section, draw_d)
    keep_insight = bool(insight_body and insight_bl)

    def _tag_rh_for_hd(hd: str | None) -> int:
        return _tag_row_height(draw_d, _tags_for_heading(hd), fonts)

    if total_h > MAX_IMAGE_HEIGHT:
        notice_lines = _wrap_to_width(
            draw_d,
            TRUNCATION_NOTICE.strip(),
            fonts.body,
            max(100, content_w - 2 * lt.inner_pad),
        )
        avail_total = MAX_IMAGE_HEIGHT - hero_h - lt.content_top_gap - lt.margin - lt.footer_h
        used = 0
        if keep_insight and insight_h + lt.card_gap <= avail_total:
            used = insight_h + lt.card_gap
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
            need_flow_before = (keep_insight and insight_bl and not final_prep) or bool(
                final_prep
            )
            prefix = (lt.card_gap + flow_row_h) if need_flow_before else 0
            trh = _tag_rh_for_hd(hd)
            full_card = _card_height_from_lines(hd, hl, bl, lt, sec_lh_m, body_lh_m, trh)
            if used_c + prefix + full_card <= card_avail:
                final_prep.append((hd, body, hl, bl, full_card, accent, sn))
                used_c += prefix + full_card
                continue

            room = card_avail - used_c - prefix
            trimmed = list(bl)
            while trimmed and _card_height_from_lines(
                hd, hl, trimmed + notice_lines, lt, sec_lh_m, body_lh_m, trh
            ) > room:
                trimmed.pop()
            bl2 = trimmed + notice_lines
            card_h2 = _card_height_from_lines(hd, hl, bl2, lt, sec_lh_m, body_lh_m, trh)
            if card_h2 <= room:
                final_prep.append((hd, body, hl, bl2, card_h2, accent, sn))
            break

        if not final_prep and prepared:
            hd0, body0, hl0, _, _, accent0, sn0 = prepared[0]
            bl_fallback = notice_lines
            trh0 = _tag_rh_for_hd(hd0)
            ch0 = _card_height_from_lines(hd0, hl0, bl_fallback, lt, sec_lh_m, body_lh_m, trh0)
            if ch0 > card_avail:
                hd0, hl0, sn0 = None, [], None
                trh0 = _tag_rh_for_hd(hd0)
                ch0 = _card_height_from_lines(hd0, hl0, bl_fallback, lt, sec_lh_m, body_lh_m, trh0)
            final_prep = [(hd0, body0, hl0, bl_fallback, ch0, accent0, sn0)]

        prepared = final_prep
        num_flows2 = max(0, len(prepared) - 1) + (
            1 if (keep_insight and insight_bl and prepared) else 0
        )
        flow_extra2 = flow_row_h * num_flows2
        body_stack_h = lt.content_top_gap + lt.margin + lt.footer_h
        if keep_insight and insight_bl:
            body_stack_h += insight_h + lt.card_gap
        if prepared:
            body_stack_h += flow_extra2 + sum(p[4] + lt.card_gap for p in prepared) - lt.card_gap
        total_h = min(hero_h + body_stack_h, MAX_IMAGE_HEIGHT)

    img = Image.new("RGB", (width, total_h), COL_PAGE_BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, hero_h], fill=COL_HERO_BG)

    y = lt.hero_pad_top
    x_text = lt.hero_pad_x
    for i, line in enumerate(kicker_lines):
        draw.text((x_text, y), line, font=fonts.kicker, fill=COL_MUTED_ON_HERO)
        y += kicker_lh + (LINE_GAP_TIGHT if i < len(kicker_lines) - 1 else 0)
    y += 14

    for i, line in enumerate(title_lines):
        draw.text((x_text, y), line, font=fonts.title, fill=COL_TEXT_ON_HERO)
        y += title_lh + (LINE_GAP_TIGHT if i < len(title_lines) - 1 else 0)

    y += lt.hero_title_to_chips
    _draw_chip_row(draw, x_text, y, inner_hero_w, chip_texts, fonts, lt)

    draw.rectangle(
        [0, hero_h - lt.hero_accent_h, width, hero_h],
        fill=COL_HERO_LINE,
    )

    y = hero_h + lt.content_top_gap
    x0_card = lt.margin
    x1_card = width - lt.margin

    if keep_insight and insight_bl:
        _draw_insight_block(
            draw, x0_card, y, x1_card, insight_h, insight_raw, insight_bl, fonts, lt
        )
        y += insight_h + lt.card_gap

    for i, (hd, _body, hl, bl, card_h, accent, sn) in enumerate(prepared):
        if (keep_insight and insight_bl and i == 0) or i > 0:
            y += _draw_flow_row(draw, width, y, fonts, lt)
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
            lt,
            sn,
        )
        y += card_h + lt.card_gap

    foot_y = total_h - lt.footer_h
    draw.text(
        (lt.margin, foot_y + lt.badge_pad_y),
        f"幅 {width}px · Noto Sans JP",
        font=fonts.footer,
        fill=COL_MUTED,
    )

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
