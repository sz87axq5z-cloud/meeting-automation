"""
Trello REST API でタスクをカードとして登録する。
Claude の「タスク一覧」セクションを行パースして 1 タスク 1 カード。
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TRELLO_API = "https://api.trello.com/1"
# Trello カード名・説明の実用上の上限
_MAX_NAME_LEN = 500
_MAX_DESC_LEN = 16_000


def _is_markdown_table_separator_row(cells: List[str]) -> bool:
    """| --- | --- | のような区切り行（英数字・日本語が無い）。"""
    blob = "|".join(cells)
    return bool(cells) and "-" in blob and not re.search(
        r"[0-9A-Za-z\u3040-\u30ff\u4e00-\u9fff]",
        blob,
    )


def _is_markdown_table_header_row(cells: List[str]) -> bool:
    j = " ".join(cells)
    return "タスク" in j and ("担当" in j or "内容" in j)


def _parse_tasks_from_markdown_table(block: str) -> List[str]:
    """
    Claude が Markdown 表でタスクを返したときのフォールバック。
    | 担当 | 内容 | 期限 | 形式（区切り行・ヘッダ行はスキップ）。
    """
    out: List[str] = []
    for line in block.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]
        if len(cells) < 2:
            continue
        if _is_markdown_table_separator_row(cells):
            continue
        if _is_markdown_table_header_row(cells):
            continue
        who, what = cells[0], cells[1]
        if not what:
            continue
        tail = f" - {cells[2]}" if len(cells) > 2 and cells[2] else ""
        item = f"{who} - {what}{tail}".strip()
        item = re.sub(r"\*+", "", item).strip()
        if item and "タスクはありません" not in item:
            out.append(item)
    return out


def parse_tasks_from_claude_text(raw_text: str) -> List[str]:
    """
    Claude 出力の「タスク一覧」ブロックからタスクを抽出する。
    主に番号付きリスト（1. ...）。無ければ Markdown 表行をフォールバック解析。
    「タスクはありませんでした」を含むブロックは空リスト。
    """
    text = (raw_text or "").strip()
    if not text:
        return []

    markers = (
        "## タスク一覧",
        "## タスク",
        "### タスク一覧",
        "### タスク",
        "# タスク一覧",
    )
    start = -1
    for m in markers:
        i = text.find(m)
        if i != -1:
            start = i + len(m)
            break
    if start < 0:
        logger.debug("no task section marker in claude output")
        return []

    rest = text[start:].lstrip("\n")
    # 次の H2（## ）までをタスクブロックとする
    m_next = re.search(r"\n##\s+\S", rest)
    if m_next:
        rest = rest[: m_next.start()]

    if "タスクはありませんでした" in rest:
        return []

    tasks: List[str] = []
    for line in rest.split("\n"):
        line = line.strip()
        m = re.match(r"^\d+\.\s+(.+)$", line)
        if not m:
            continue
        body = m.group(1).strip()
        body = re.sub(r"\*+", "", body).strip()
        if not body or "タスクはありません" in body:
            continue
        tasks.append(body)
    if tasks:
        return tasks
    return _parse_tasks_from_markdown_table(rest)


def _task_assignee_prefix(task: str) -> str:
    """
    「担当者 - 内容」の担当側。
    半角/全角ハイフン・en/em dash の揺れを許容（Claude の出力が `–` になることもある）。
    """
    t = task.strip()
    parts = re.split(r"\s*[-–—－]\s*", t, maxsplit=1)
    return parts[0].strip() if parts else t


def _prefix_matches_assignee_filter(prefix: str, filt: str) -> bool:
    f = filt.strip()
    if not f:
        return False
    if prefix == f:
        return True
    # 「高橋」と「高橋圭佑」のような部分一致
    return prefix.startswith(f) or f.startswith(prefix)


def assignee_filter_terms() -> Tuple[str, ...]:
    """
    .env の TRELLO_ASSIGNEE_FILTER（カンマまたは読点区切り）。
    pydantic で拾えない場合に os.environ も見る（実行 cwd や設定の差のフォールバック）。
    """
    raw = (settings.trello_assignee_filter or "").strip()
    if not raw:
        raw = (os.environ.get("TRELLO_ASSIGNEE_FILTER") or "").strip()
    if not raw:
        return ()
    parts = re.split(r"[,、]", raw)
    return tuple(x.strip() for x in parts if x.strip())


def filter_tasks_by_assignee(tasks: List[str]) -> List[str]:
    """
    TRELLO_ASSIGNEE_FILTER が空でなければ、担当名がいずれかにマッチするタスクだけ残す。
    """
    terms = assignee_filter_terms()
    if not terms:
        return list(tasks)
    out: List[str] = []
    for t in tasks:
        prefix = _task_assignee_prefix(t)
        if any(_prefix_matches_assignee_filter(prefix, term) for term in terms):
            out.append(t)
    logger.info(
        "trello assignee filter %s: %s -> %s tasks",
        terms,
        len(tasks),
        len(out),
    )
    return out


def _card_footer(meeting_id: str, meeting_info: Dict[str, Any]) -> str:
    lines = [f"Meeting ID: `{meeting_id}`"]
    url = meeting_info.get("url")
    if url:
        lines.append(f"tl;dv: {url}")
    return "\n".join(lines)


def create_cards_for_tasks(
    tasks: List[str],
    meeting_id: str,
    meeting_info: Dict[str, Any],
) -> List[str]:
    """
    各タスクを 1 枚のカードにする。戻り値はブラウザ用 shortUrl のリスト。
    """
    if not tasks:
        return []

    tasks = filter_tasks_by_assignee(tasks)
    if not tasks:
        logger.info("trello assignee filter: no tasks left after filter, skip POST")
        return []

    params = {
        "key": settings.trello_api_key,
        "token": settings.trello_token,
    }
    footer = _card_footer(meeting_id, meeting_info)
    urls: List[str] = []

    list_id = (settings.trello_list_id or "").strip()
    if not list_id:
        raise ValueError("TRELLO_LIST_ID が空です")

    with httpx.Client(timeout=60.0) as client:
        for title in tasks:
            name = title[:_MAX_NAME_LEN] if len(title) > _MAX_NAME_LEN else title
            desc = f"{footer}\n\n{title}"[:_MAX_DESC_LEN]
            r = client.post(
                f"{TRELLO_API}/cards",
                params=params,
                data={
                    "idList": list_id,
                    "name": name,
                    "desc": desc,
                },
            )
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                body = (e.response.text or "")[:800]
                logger.error(
                    "Trello POST /cards failed status=%s list_id=%s body=%s",
                    e.response.status_code,
                    list_id,
                    body,
                )
                if e.response.status_code == 404:
                    raise RuntimeError(
                        "Trello が 404 を返しました。TRELLO_LIST_ID が間違っている可能性が高いです "
                        "（よくあるのはボード ID を入れてしまうこと）。"
                        "`python scripts/show_trello_lists.py` でリスト ID を確認してください。"
                    ) from e
                raise
            data = r.json()
            u = data.get("shortUrl") or data.get("url")
            if u:
                urls.append(str(u))
            cid = data.get("id", "?")
            logger.info("trello card created id=%s name_prefix=%s", cid, name[:40])

    return urls
