"""
会議メタの表示用フォーマット（PNG / Slack 共通）。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")
_UTC = ZoneInfo("UTC")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 小数の前後を触らない。カンマ紛れ込みの整数を 1,234,567 形式に揃える。
_DIGIT_TOKEN_RE = re.compile(r"(?<![\d.])([\d,]+)(?![\d.])")


def normalize_western_number_commas(text: str) -> str:
    """
    文中の整数トークンを、カンマを3桁ごとに振り直す（英米式）。

    - 「5213,213」「23000,000」のような誤った区切りを「5,213,213」「23,000,000」に直す。
    - 4桁でカンマなし（例: 2024）は年号の可能性があるためそのまま。
    - 小数点付き数字の一部はマッチしない（例: 3.14 の 14 は対象外）。
    """
    if not text:
        return text

    def repl(m: re.Match[str]) -> str:
        raw = m.group(1)
        plain = raw.replace(",", "")
        if not plain.isdigit():
            return raw
        n = len(plain)
        if n < 4:
            return plain
        if n == 4 and "," not in raw:
            return raw
        try:
            return f"{int(plain):,}"
        except ValueError:
            return raw

    return _DIGIT_TOKEN_RE.sub(repl, text)


def format_happened_at_display(raw: Any) -> str:
    """
    tl;dv の happenedAt を「YYYY-MM-DD HH:MM」にする（24h・ゼロ埋め）。

    - `YYYY-MM-DD` のみ → その日の JST 00:00 として表示
    - ISO（`T` 付き・`Z` 可）→ タイムゾーン解釈後に JST へ換算
    - パース不可 → 元文字列（strip 済み）を返す
    """
    text = ("" if raw is None else str(raw)).strip()
    if not text:
        return ""
    if _DATE_ONLY.fullmatch(text):
        d = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=_JST)
        return d.strftime("%Y-%m-%d %H:%M")
    normalized = text.replace("Z", "+00:00").replace("z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    jst = dt.astimezone(_JST)
    return jst.strftime("%Y-%m-%d %H:%M")
