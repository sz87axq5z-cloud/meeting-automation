"""
インフォグラフィック HTML 向け: 句読点直後に <wbr> を挿入し、モバイル幅での折り位置を改善する。
"""

from __future__ import annotations

import re
from bs4 import BeautifulSoup, NavigableString, Tag

# 全角読点・全角／半角句点・感嘆疑問
_PUNCT = frozenset("、，。！？")
_PUNCT_SPLIT_RE = re.compile(r"([、，。！？])")

# .header h1 は長いときだけ句読点処理（短いタイトルはそのまま）
_H1_MIN_LEN = 14

_SKIP_PARENT_NAMES = frozenset({"script", "style", "a", "svg", "textarea", "pre", "code"})

_TARGET_SELECTORS: tuple[str, ...] = (
    ".header p",
    ".header h1",
    ".section h2",
    ".section h3",
    ".section h4",
    ".section p",
    ".section li",
    ".flow-step p",
    ".timeline-item p",
    ".challenge-box p",
    ".improvement-box p",
    ".data-flow li",
    ".business-card p",
    ".business-card h3",
    "section.ma-embed-tasklist .ma-et-body li",
    "section.ma-embed-tasklist .task-assignee",
)


def _classes_of(tag: Tag) -> set[str]:
    c = tag.get("class")
    if not c:
        return set()
    if isinstance(c, str):
        return {c}
    return set(c)


def _skip_for_ancestors(tag: Tag | None) -> bool:
    cur: Tag | None = tag
    while cur is not None and isinstance(cur, Tag):
        if cur.name and cur.name.lower() in _SKIP_PARENT_NAMES:
            return True
        if "metric-number" in _classes_of(cur):
            return True
        cur = cur.parent
    return False


def _collect_target_elements(soup: BeautifulSoup) -> list[Tag]:
    seen: set[int] = set()
    out: list[Tag] = []
    for sel in _TARGET_SELECTORS:
        for el in soup.select(sel):
            if not isinstance(el, Tag):
                continue
            if id(el) in seen:
                continue
            if sel == ".header h1":
                text = el.get_text(strip=True)
                if len(text) <= _H1_MIN_LEN:
                    continue
            seen.add(id(el))
            out.append(el)
    return out


def _soften_text_to_nodes(soup: BeautifulSoup, text: str) -> list[NavigableString | Tag]:
    """1 つのテキスト断片を、句読点の直後に <wbr> を挟んだノード列に分解する。"""
    if not text:
        return []
    parts = _PUNCT_SPLIT_RE.split(text)
    if len(parts) == 1:
        return [NavigableString(text)]

    nodes: list[NavigableString | Tag] = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if chunk == "":
            i += 1
            continue
        nodes.append(NavigableString(chunk))
        if chunk in _PUNCT:
            tail = "".join(parts[i + 1 :])
            if tail.strip():
                nodes.append(soup.new_tag("wbr"))
        i += 1
    return nodes


def _replace_text_node(soup: BeautifulSoup, node: NavigableString) -> None:
    text = str(node)
    if not any(c in text for c in _PUNCT):
        return

    parent = node.parent
    if parent is None or not isinstance(parent, Tag):
        return

    new_nodes = _soften_text_to_nodes(soup, text)
    if len(new_nodes) <= 1:
        return

    node.replace_with(*new_nodes)


def apply_infographic_ja_softbreaks(html: str) -> str:
    """
    対象要素内のテキストノードに、句読点直後の <wbr> を挿入する。
    パース失敗時は元文字列を返す。
    """
    if not html or not html.strip():
        return html

    doctype_prefix = ""
    m = re.match(r"(\s*)(<!DOCTYPE[^>]*>)", html, re.IGNORECASE)
    if m:
        doctype_prefix = m.group(2) + "\n"

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return html

    targets = _collect_target_elements(soup)
    text_nodes: list[NavigableString] = []
    for el in targets:
        for t in el.find_all(string=True, recursive=True):
            if not isinstance(t, NavigableString):
                continue
            if not str(t).strip():
                continue
            parent = t.parent
            if not isinstance(parent, Tag):
                continue
            if _skip_for_ancestors(parent):
                continue
            text_nodes.append(t)

    # 末端から置換（ツリー変形でイテレータがずれないよう）
    for t in reversed(text_nodes):
        _replace_text_node(soup, t)

    body = str(soup)
    if doctype_prefix and not body.lstrip().upper().startswith("<!DOCTYPE"):
        return doctype_prefix + body
    return body
