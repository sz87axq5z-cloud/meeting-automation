import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import dedupe


class TestDedupe(unittest.TestCase):
    def setUp(self) -> None:
        self.settings_patcher = patch.object(dedupe, "settings")
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.upstash_redis_rest_url = ""
        self.mock_settings.upstash_redis_rest_token = ""
        self.mock_settings.dedupe_webhook_ttl_seconds = 60
        self.mock_settings.dedupe_meeting_ttl_seconds = 120

    def tearDown(self) -> None:
        self.settings_patcher.stop()

    def test_not_configured_always_acquire_webhook(self) -> None:
        self.assertTrue(dedupe.try_acquire_webhook("wh-1"))
        self.assertFalse(dedupe.meeting_already_completed("m1"))

    @patch.object(dedupe, "httpx")
    def test_try_acquire_webhook_ok(self, mock_httpx: MagicMock) -> None:
        self.mock_settings.upstash_redis_rest_url = "https://redis.example"
        self.mock_settings.upstash_redis_rest_token = "tok"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"result": "OK"}
        mock_httpx.post.return_value = mock_resp

        self.assertTrue(dedupe.try_acquire_webhook("wh-1"))

    @patch.object(dedupe, "httpx")
    def test_try_acquire_webhook_duplicate(self, mock_httpx: MagicMock) -> None:
        self.mock_settings.upstash_redis_rest_url = "https://redis.example"
        self.mock_settings.upstash_redis_rest_token = "tok"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"result": None}
        mock_httpx.post.return_value = mock_resp

        self.assertFalse(dedupe.try_acquire_webhook("wh-1"))

    @patch.object(dedupe, "httpx")
    def test_meeting_already_completed(self, mock_httpx: MagicMock) -> None:
        self.mock_settings.upstash_redis_rest_url = "https://redis.example"
        self.mock_settings.upstash_redis_rest_token = "tok"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"result": 1}
        mock_httpx.post.return_value = mock_resp

        self.assertTrue(dedupe.meeting_already_completed("mid"))

    @patch.object(dedupe, "httpx")
    def test_mark_meeting_completed_calls_set(self, mock_httpx: MagicMock) -> None:
        self.mock_settings.upstash_redis_rest_url = "https://redis.example"
        self.mock_settings.upstash_redis_rest_token = "tok"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"result": "OK"}
        mock_httpx.post.return_value = mock_resp

        dedupe.mark_meeting_completed("mid")
        mock_httpx.post.assert_called()
        body = mock_httpx.post.call_args[1]["json"]
        self.assertEqual(body[0], "SET")
        self.assertEqual(body[1], "ma:done:mid")


if __name__ == "__main__":
    unittest.main()
