import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import tldv_client


class TestTranscriptFormat(unittest.TestCase):
    def test_list_segments(self) -> None:
        data = [
            {"speaker": "田中", "text": "こんにちは", "startTime": 65},
            {"speaker": "佐藤", "text": "よろしく", "startTime": 0},
        ]
        text = tldv_client.transcript_data_to_text(data)
        self.assertIn("[00:00] 佐藤: よろしく", text)
        self.assertIn("[01:05] 田中: こんにちは", text)

    def test_dict_with_segments(self) -> None:
        data = {
            "transcript": "",
            "segments": [{"startTime": 10, "text": "Hello", "speaker": "A"}],
        }
        text = tldv_client.transcript_data_to_text(data)
        self.assertEqual(text, "[00:10] A: Hello")

    def test_empty(self) -> None:
        self.assertEqual(tldv_client.transcript_data_to_text(None), "")
        self.assertEqual(tldv_client.transcript_data_to_text([]), "")


class TestMeetingInfo(unittest.TestCase):
    def test_meeting_to_claude_info(self) -> None:
        meeting = {
            "id": "m1",
            "name": "定例",
            "happenedAt": "2026-01-01T10:00:00Z",
            "organizer": {"name": "主催", "email": "a@ex.com"},
            "invitees": [{"name": "ゲスト", "email": "b@ex.com"}],
            "url": "https://app.tldv.io/meetings/m1",
        }
        info = tldv_client.meeting_to_claude_info(meeting)
        self.assertEqual(info["name"], "定例")
        self.assertEqual(info["happened_at"], "2026-01-01T10:00:00Z")
        self.assertEqual(info["participants"], ["主催", "ゲスト"])
        self.assertEqual(info["url"], meeting["url"])


class TestTranscriptAvailability(unittest.TestCase):
    def test_get_transcript_text_if_available_404(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status = MagicMock()
        with patch.object(tldv_client.httpx, "Client") as mock_cm:
            mock_client = MagicMock()
            mock_cm.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            self.assertIsNone(tldv_client.get_transcript_text_if_available("mid"))

    def test_get_transcript_text_if_available_ok(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data":[]}'
        mock_response.json.return_value = {
            "data": [{"speaker": "A", "text": "hello", "startTime": 0}],
        }
        mock_response.raise_for_status = MagicMock()
        with patch.object(tldv_client.httpx, "Client") as mock_cm:
            mock_client = MagicMock()
            mock_cm.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            text = tldv_client.get_transcript_text_if_available("mid")
            self.assertIn("hello", text or "")

    def test_get_transcript_text_if_available_empty_body(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_response.json.side_effect = ValueError("should not call")
        mock_response.raise_for_status = MagicMock()
        with patch.object(tldv_client.httpx, "Client") as mock_cm:
            mock_client = MagicMock()
            mock_cm.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            self.assertIsNone(tldv_client.get_transcript_text_if_available("mid"))

    def test_get_transcript_text_if_available_bad_json(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "not json"
        mock_response.json.side_effect = __import__("json").JSONDecodeError("msg", "doc", 0)
        mock_response.raise_for_status = MagicMock()
        with patch.object(tldv_client.httpx, "Client") as mock_cm:
            mock_client = MagicMock()
            mock_cm.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            self.assertIsNone(tldv_client.get_transcript_text_if_available("mid"))


class TestListMeetings(unittest.TestCase):
    @patch.object(tldv_client, "_get_json")
    def test_list_meetings_params(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {"page": 1, "pages": 1, "total": 1, "pageSize": 50, "results": []}
        tldv_client.list_meetings(page=1, page_size=50)
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertEqual(call_args[0][0], "/v1alpha1/meetings")
        self.assertEqual(call_args[1]["params"], {"page": 1, "pageSize": 50})

    @patch.object(tldv_client, "_get_json")
    def test_list_meetings_default_page_is_one(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {"results": []}
        tldv_client.list_meetings()
        self.assertEqual(mock_get.call_args[1]["params"]["page"], 1)

    @patch.object(tldv_client, "_get_json")
    def test_list_meetings_with_type(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {"results": []}
        tldv_client.list_meetings(meeting_type="internal")
        params = mock_get.call_args[1]["params"]
        self.assertEqual(params["meetingType"], "internal")


class TestFetchMeetingContext(unittest.TestCase):
    @patch.object(tldv_client, "get_transcript_payload")
    @patch.object(tldv_client, "get_meeting")
    def test_fetch(self, mock_meeting: MagicMock, mock_tr: MagicMock) -> None:
        mock_meeting.return_value = {
            "id": "x",
            "name": "MTG",
            "happenedAt": "2026-03-01T12:00:00Z",
            "organizer": {"name": "A"},
            "invitees": [],
        }
        mock_tr.return_value = {
            "meetingId": "x",
            "data": [{"speaker": "A", "text": "テスト", "startTime": 0}],
        }
        info, transcript = tldv_client.fetch_meeting_context("x")
        self.assertEqual(info["name"], "MTG")
        self.assertIn("テスト", transcript)
        mock_meeting.assert_called_once_with("x")
        mock_tr.assert_called_once_with("x")


if __name__ == "__main__":
    unittest.main()
