import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.api.webhook import router as webhook_router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(webhook_router)
    return TestClient(app)


class TestWebhook(unittest.TestCase):
    @patch("app.api.webhook.run_pipeline")
    @patch("app.api.webhook.try_acquire_webhook", return_value=True)
    @patch("app.api.webhook.is_dedupe_configured", return_value=False)
    @patch("app.api.webhook.settings")
    def test_transcript_ready_accepted(
        self,
        mock_settings: MagicMock,
        _mock_dedupe_cfg: MagicMock,
        _mock_acquire: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_settings.webhook_secret = "s3cr3t"
        client = _make_client()
        r = client.post(
            "/webhook?token=s3cr3t",
            json={
                "event": "TranscriptReady",
                "data": {"meetingId": "m1"},
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), "accepted")
        mock_run.assert_called()

    @patch("app.api.webhook.run_pipeline")
    @patch("app.api.webhook.try_acquire_webhook", return_value=False)
    @patch("app.api.webhook.is_dedupe_configured", return_value=True)
    @patch("app.api.webhook.settings")
    def test_duplicate_when_acquire_fails(
        self,
        mock_settings: MagicMock,
        _mock_dedupe_cfg: MagicMock,
        _mock_acquire: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_settings.webhook_secret = "s3cr3t"
        client = _make_client()
        r = client.post(
            "/webhook?token=s3cr3t",
            json={
                "id": "wh-1",
                "event": "TranscriptReady",
                "data": {"meetingId": "m1"},
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), "duplicate")
        mock_run.assert_not_called()

    @patch("app.api.webhook.settings")
    def test_dedupe_requires_id(self, mock_settings: MagicMock) -> None:
        mock_settings.webhook_secret = "s3cr3t"
        with patch("app.api.webhook.is_dedupe_configured", return_value=True):
            client = _make_client()
            r = client.post(
                "/webhook?token=s3cr3t",
                json={
                    "event": "TranscriptReady",
                    "data": {"meetingId": "m1"},
                },
            )
        self.assertEqual(r.status_code, 400)

    @patch("app.api.webhook.settings")
    def test_wrong_token(self, mock_settings: MagicMock) -> None:
        mock_settings.webhook_secret = "s3cr3t"
        client = _make_client()
        r = client.post(
            "/webhook?token=wrong",
            json={"event": "TranscriptReady", "data": {"meetingId": "m1"}},
        )
        self.assertEqual(r.status_code, 401)

    @patch("app.api.webhook.run_pipeline")
    @patch("app.api.webhook.is_dedupe_configured", return_value=False)
    @patch("app.api.webhook.settings")
    def test_header_x_webhook_secret_accepted(
        self,
        mock_settings: MagicMock,
        _mock_dedupe: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_settings.webhook_secret = "s3cr3t"
        client = _make_client()
        r = client.post(
            "/webhook",
            headers={"X-Webhook-Secret": "s3cr3t"},
            json={"event": "TranscriptReady", "data": {"meetingId": "m1"}},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), "accepted")
        mock_run.assert_called()

    @patch("app.api.webhook.run_pipeline")
    @patch("app.api.webhook.is_dedupe_configured", return_value=False)
    @patch("app.api.webhook.settings")
    def test_header_authorization_bearer_accepted(
        self,
        mock_settings: MagicMock,
        _mock_dedupe: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_settings.webhook_secret = "s3cr3t"
        client = _make_client()
        r = client.post(
            "/webhook",
            headers={"Authorization": "Bearer s3cr3t"},
            json={"event": "TranscriptReady", "data": {"meetingId": "m1"}},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), "accepted")
        mock_run.assert_called()

    @patch("app.api.webhook.settings")
    def test_wrong_header_401(self, mock_settings: MagicMock) -> None:
        mock_settings.webhook_secret = "s3cr3t"
        client = _make_client()
        r = client.post(
            "/webhook",
            headers={"X-Webhook-Secret": "nope"},
            json={"event": "TranscriptReady", "data": {"meetingId": "m1"}},
        )
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
