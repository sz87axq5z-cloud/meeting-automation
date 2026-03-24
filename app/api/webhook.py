from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.config import settings
from app.services.pipeline import run_pipeline


router = APIRouter()


@router.post("/webhook")
async def tldv_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    token: str | None = None,
) -> dict:
    if token != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid token")

    payload = await request.json()

    event = payload.get("event")
    if event != "TranscriptReady":
        return {"status": "ignored"}

    data = payload.get("data") or {}
    meeting_id = data.get("meetingId")
    if not meeting_id:
        raise HTTPException(status_code=400, detail="meetingId is missing")

    background_tasks.add_task(run_pipeline, meeting_id)

    return {"status": "accepted"}

