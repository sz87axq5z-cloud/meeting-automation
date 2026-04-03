"""
Claude が返す図解 HTML のクラス名ブレ（sources / info-source 等）に対応し、
情報ソースを会議名のみに正規化し、直前にパイプライン要約と同型のタスク一覧を挿入する。
"""

from __future__ import annotations

import html as html_mod
import re
from typing import Any, Dict

from app.services.summary_html import build_embedded_task_list_block_html

# 情報ソース用フッタの class に使われがちな名前（部分一致ではなくトークンとして判定）
_SOURCE_CLASS_MARKERS = frozenset({"sources", "info-source", "source-footer", "page-sources"})

_OPEN_DIV_CLASS_RE = re.compile(
    r'<div\s+[^>]*\bclass\s*=\s*(["\'])([^"\']*)\1[^>]*>',
    re.IGNORECASE,
)


def _class_attr_contains_marker(class_val: str) -> bool:
    tokens = re.split(r"\s+", (class_val or "").strip())
    return bool(_SOURCE_CLASS_MARKERS.intersection(tokens))


def _span_outer_div_from(html: str, open_angle_start: int) -> tuple[int, int] | None:
    """open_angle_start は開き <div の位置。対応する閉じ </div> 直後までの [start, end)。"""
    gt = html.find(">", open_angle_start)
    if gt < 0:
        return None
    i = gt + 1
    depth = 1
    lowered = html.lower()
    n = len(html)
    while depth > 0 and i < n:
        no = lowered.find("<div", i)
        nc = lowered.find("</div>", i)
        if nc < 0:
            return None
        if no >= 0 and no < nc:
            depth += 1
            i = no + 4
        else:
            depth -= 1
            i = nc + len("</div>")
            if depth == 0:
                return (open_angle_start, i)
    return None


def find_infographic_sources_section_span(html: str) -> tuple[int, int] | None:
    """
    「情報ソース」フッタ想定の div を探す。
    class トークンが sources / info-source 等のいずれかを含む最も手前の候補から試す。
    """
    if not html:
        return None

    candidates: list[tuple[int, int]] = []
    for m in _OPEN_DIV_CLASS_RE.finditer(html):
        if _class_attr_contains_marker(m.group(2)):
            span = _span_outer_div_from(html, m.start())
            if span:
                candidates.append(span)

    if not candidates:
        # フォールバック: 見出しテキスト「情報ソース」直前の div
        h3 = re.search(
            r"<h3[^>]*>\s*情報ソース\s*</h3>",
            html,
            re.IGNORECASE,
        )
        if h3:
            before = html.rfind("<div", 0, h3.start())
            if before >= 0:
                span = _span_outer_div_from(html, before)
                if span and span[1] >= h3.end():
                    candidates.append(span)

    if not candidates:
        return None

    # 文書末尾に近いブロックを優先（メインコンテナ内のフッタ）
    return max(candidates, key=lambda s: s[0])


def patch_infographic_html(
    html: str,
    meeting_info: Dict[str, Any],
    summary_raw: str,
) -> str:
    """
    情報ソースを会議名のみに差し替え、その直前にタスク一覧を挿入。
    """
    name = str(meeting_info.get("name") or "会議")
    esc = html_mod.escape(name)

    new_sources = (
        '        <div class="sources">\n'
        "            <h3>情報ソース</h3>\n"
        f"            <p>{esc}</p>\n"
        "        </div>"
    )

    task_block = build_embedded_task_list_block_html(summary_raw)
    prefix = ""
    if task_block.strip():
        prefix = task_block + "\n"

    span = find_infographic_sources_section_span(html)
    if span is not None:
        start, end = span
        return html[:start] + prefix + new_sources + html[end:]

    # フッタが見つからないときは </body> 直前に追加
    insertion = prefix + new_sources
    out, n = re.subn(
        r"(</body\s*>)",
        insertion + r"\n\1",
        html,
        count=1,
        flags=re.IGNORECASE,
    )
    if n:
        return out
    return html + "\n" + insertion
