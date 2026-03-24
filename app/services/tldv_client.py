"""
tl;dv Public API (v1alpha1) クライアント。
https://doc.tldv.io/
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

JsonDict = Dict[str, Any]
TranscriptData = Union[List[JsonDict], JsonDict, None]


def _client_headers() -> Dict[str, str]:
    return {
        "x-api-key": settings.tldv_api_key,
        "Content-Type": "application/json",
    }


def _api_base() -> str:
    return settings.tldv_base_url.rstrip("/")


def _get_json(path: str, params: Dict[str, Any] | None = None) -> Any:
    url = f"{_api_base()}{path}"
    with httpx.Client(timeout=120.0) as client:
        response = client.get(url, headers=_client_headers(), params=params)
        response.raise_for_status()
        return response.json()


def list_meetings(
    *,
    page: int = 1,
    page_size: int = 50,
    meeting_type: str | None = None,
) -> JsonDict:
    """
    GET /v1alpha1/meetings — 会議一覧（ページネーションあり）。
    tl;dv API は page を 1 始まりの正の整数とする（0 は 400）。
    meeting_type は API の meetingType フィルタ（例: internal / external）があれば指定。
    """
    params: Dict[str, Any] = {"page": page, "pageSize": page_size}
    if meeting_type:
        params["meetingType"] = meeting_type
    return _get_json("/v1alpha1/meetings", params=params)


def get_meeting(meeting_id: str) -> JsonDict:
    """GET /v1alpha1/meetings/{meetingId}"""
    return _get_json(f"/v1alpha1/meetings/{meeting_id}")


def get_transcript_payload(meeting_id: str) -> JsonDict:
    """GET /v1alpha1/meetings/{meetingId}/transcript"""
    return _get_json(f"/v1alpha1/meetings/{meeting_id}/transcript")


def get_transcript_text_if_available(meeting_id: str) -> Optional[str]:
    """
    文字起こしが取得でき、かつ本文が空でないときだけテキストを返す。
    未生成・権限なしなどは GET が 403/404 になり得る → None。
    セグメントが空配列のときも None。
    """
    url = f"{_api_base()}/v1alpha1/meetings/{meeting_id}/transcript"
    with httpx.Client(timeout=120.0) as client:
        response = client.get(url, headers=_client_headers())
    if response.status_code in (403, 404):
        return None
    response.raise_for_status()
    raw = (response.text or "").strip()
    if not raw:
        return None
    try:
        payload = response.json()
    except json.JSONDecodeError:
        logger.debug(
            "transcript response not JSON meeting_id=%s status=%s body_prefix=%r",
            meeting_id,
            response.status_code,
            raw[:120],
        )
        return None
    if not isinstance(payload, dict):
        return None
    text = transcript_data_to_text(payload.get("data"))
    return text if text.strip() else None


def meeting_to_claude_info(meeting: JsonDict) -> JsonDict:
    """claude_processor.summarize_and_extract_tasks 向けの会議メタ情報。"""
    participants: List[str] = []
    organizer = meeting.get("organizer") or {}
    oname = organizer.get("name")
    if oname:
        participants.append(str(oname))
    for inv in meeting.get("invitees") or []:
        label = inv.get("name") or inv.get("email")
        if label and label not in participants:
            participants.append(str(label))
    return {
        "id": meeting.get("id"),
        "name": meeting.get("name") or "（無題）",
        "happened_at": meeting.get("happenedAt") or "",
        "participants": participants,
        "url": meeting.get("url"),
    }


def transcript_data_to_text(data: TranscriptData) -> str:
    """
    transcript エンドポイントの `data` を Claude 投入用のプレーンテキストにする。

    ドキュメント上は data がセグメントの配列:
    [{ "speaker", "text", "startTime", "endTime" }, ...]

    Webhook サンプルでは transcript 文字列 + segments があるためその形も許容する。
    """
    if data is None:
        return ""

    if isinstance(data, list):
        lines: List[str] = []
        for seg in data:
            if not isinstance(seg, dict):
                continue
            speaker = seg.get("speaker") or "不明"
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            start = seg.get("startTime", 0)
            try:
                sec = int(float(start))
            except (TypeError, ValueError):
                sec = 0
            mm, ss = divmod(sec, 60)
            lines.append(f"[{mm:02d}:{ss:02d}] {speaker}: {text}")
        return "\n".join(lines)

    if isinstance(data, dict):
        full = (data.get("transcript") or "").strip()
        segments = data.get("segments")
        if isinstance(segments, list) and segments:
            lines = []
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                text = (seg.get("text") or "").strip()
                if not text:
                    continue
                start = seg.get("startTime", 0)
                try:
                    sec = int(float(start))
                except (TypeError, ValueError):
                    sec = 0
                mm, ss = divmod(sec, 60)
                sp = seg.get("speaker")
                prefix = f"{sp}: " if sp else ""
                lines.append(f"[{mm:02d}:{ss:02d}] {prefix}{text}")
            return "\n".join(lines) if lines else full
        return full

    return str(data)


def fetch_meeting_context(meeting_id: str) -> Tuple[JsonDict, str]:
    """
    会議メタ情報と文字起こし全文を取得する。
    戻り値: (meeting_to_claude_info の dict, transcript テキスト)
    """
    logger.debug("tldv fetch meeting_id=%s", meeting_id)
    meeting = get_meeting(meeting_id)
    info = meeting_to_claude_info(meeting)
    payload = get_transcript_payload(meeting_id)
    raw_data = payload.get("data")
    transcript_text = transcript_data_to_text(raw_data)
    return info, transcript_text
