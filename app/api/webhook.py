from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.config import settings
from app.services.dedupe import is_dedupe_configured, try_acquire_webhook
from app.services.pipeline import run_pipeline


router = APIRouter()


def _provided_webhook_secret(request: Request, query_token: str | None) -> str | None:
    """
    tl;dv 等がクエリ文字列を付けずに POST する場合があるため、
    次のいずれかで WEBHOOK_SECRET と同じ値を受け取る（先に見つかったものを採用）。

    1. クエリ `?token=`
    2. ヘッダー `X-Webhook-Secret`
    3. ヘッダー `X-Webhook-Token`
    4. ヘッダー `Authorization: Bearer <secret>`
    """
    if query_token is not None and str(query_token).strip() != "":
        return str(query_token).strip()
    h = request.headers.get("x-webhook-secret")
    if h and str(h).strip():
        return str(h).strip()
    h = request.headers.get("x-webhook-token")
    if h and str(h).strip():
        return str(h).strip()
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        rest = auth[7:].strip()
        if rest:
            return rest
    return None


def _webhook_secret_auth_ok(request: Request, query_token: str | None) -> bool:
    provided = _provided_webhook_secret(request, query_token)
    if provided is None:
        return False
    return provided == (settings.webhook_secret or "").strip()


def _tldv_x_api_key_auth_ok(request: Request) -> bool:
    """tl;dv Webhook の「APIキー」認証で送られる x-api-key と TLDV_API_KEY を照合。"""
    key = (request.headers.get("x-api-key") or "").strip()
    if not key:
        return False
    return key == (settings.tldv_api_key or "").strip()


def _webhook_authorized(request: Request, query_token: str | None) -> bool:
    return _webhook_secret_auth_ok(request, query_token) or _tldv_x_api_key_auth_ok(
        request
    )


@router.post("/webhook")
async def tldv_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    token: str | None = None,
) -> dict:
    if not _webhook_authorized(request, token):
        raise HTTPException(status_code=401, detail="Invalid token")

    payload = await request.json()

    event = payload.get("event")
    if event != "TranscriptReady":
        return {"status": "ignored"}

    data = payload.get("data") or {}
    meeting_id = data.get("meetingId")
    if not meeting_id:
        raise HTTPException(status_code=400, detail="meetingId is missing")

    if is_dedupe_configured():
        webhook_id = payload.get("id")
        if not webhook_id or not str(webhook_id).strip():
            raise HTTPException(
                status_code=400,
                detail="webhook id is missing (required when dedupe is configured)",
            )
        if not try_acquire_webhook(str(webhook_id).strip()):
            return {"status": "duplicate"}

    background_tasks.add_task(run_pipeline, meeting_id)

    return {"status": "accepted"}

