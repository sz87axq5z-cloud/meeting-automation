from fastapi import FastAPI

from app.api.webhook import router as webhook_router


app = FastAPI(title="Meeting Automation")

app.include_router(webhook_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

