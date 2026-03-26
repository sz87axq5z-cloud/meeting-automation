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
