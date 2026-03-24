import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import slack_publisher


class TestSlackPublisher(unittest.TestCase):
    @patch.object(slack_publisher, "WebClient")
    @patch.object(slack_publisher, "settings")
    def test_post_calls_upload_v2(
        self,
        mock_settings: MagicMock,
        mock_client_cls: MagicMock,
    ) -> None:
        mock_settings.slack_bot_token = "xoxb-test"
        mock_settings.slack_channel_id = "C111"
        mock_inst = MagicMock()
        mock_client_cls.return_value = mock_inst
        mock_resp = MagicMock()
        mock_resp.data = {"file": {"id": "Fabc"}}
        mock_inst.files_upload_v2.return_value = mock_resp

        fid = slack_publisher.post_meeting_summary_png(
            png_bytes=b"fakepng",
            meeting_id="mid1",
            meeting_info={"name": "定例", "happened_at": "2026-01-01", "url": "https://x"},
        )

        self.assertEqual(fid, "Fabc")
        mock_inst.files_upload_v2.assert_called_once()
        call_kw = mock_inst.files_upload_v2.call_args.kwargs
        self.assertEqual(call_kw["channel"], "C111")
        self.assertEqual(call_kw["content"], b"fakepng")
        self.assertIn("meeting_summary_mid1.png", call_kw["filename"])
        self.assertIn("定例", call_kw["initial_comment"])
        self.assertIn("tl;dv", call_kw["initial_comment"])

    @patch.object(slack_publisher, "WebClient")
    @patch.object(slack_publisher, "settings")
    def test_trello_links_in_comment(
        self,
        mock_settings: MagicMock,
        mock_client_cls: MagicMock,
    ) -> None:
        mock_settings.slack_bot_token = "xoxb-test"
        mock_settings.slack_channel_id = "C111"
        mock_inst = MagicMock()
        mock_client_cls.return_value = mock_inst
        mock_resp = MagicMock()
        mock_resp.data = {"file": {"id": "F"}}
        mock_inst.files_upload_v2.return_value = mock_resp

        slack_publisher.post_meeting_summary_png(
            png_bytes=b"x",
            meeting_id="m",
            meeting_info={"name": "N"},
            trello_urls=["https://trello.com/c/a"],
        )
        comment = mock_inst.files_upload_v2.call_args.kwargs["initial_comment"]
        self.assertIn("Trello", comment)
        self.assertIn("trello.com", comment)


if __name__ == "__main__":
    unittest.main()
