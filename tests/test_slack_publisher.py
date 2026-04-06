import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import ImageFont

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import image_generator, slack_publisher


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
    def test_summary_html_url_in_comment(
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
            meeting_id="m1",
            meeting_info={"name": "N"},
            summary_html_url="https://example.com/meetings/m1.html",
        )
        comment = mock_inst.files_upload_v2.call_args.kwargs["initial_comment"]
        self.assertIn("要約（HTML）", comment)
        self.assertIn("https://example.com/meetings/m1.html", comment)
        self.assertIn("ブラウザで開く（図解ページ）", comment)

    @patch.object(slack_publisher, "WebClient")
    @patch.object(slack_publisher, "settings")
    def test_html_public_url_missing_hint_in_comment(
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
            meeting_id="m1",
            meeting_info={"name": "N"},
            html_public_url_missing=True,
        )
        comment = mock_inst.files_upload_v2.call_args.kwargs["initial_comment"]
        self.assertIn("MEETING_HTML_GCS_BUCKET", comment)
        self.assertIn("MEETING_HTML_S3_BUCKET", comment)
        self.assertNotIn("要約（HTML）", comment)

    @patch.object(slack_publisher, "WebClient")
    @patch.object(slack_publisher, "settings")
    def test_upload_summary_html_returns_permalink(
        self,
        mock_settings: MagicMock,
        mock_client_cls: MagicMock,
    ) -> None:
        mock_settings.slack_bot_token = "xoxb-test"
        mock_settings.slack_channel_id = "C111"
        mock_inst = MagicMock()
        mock_client_cls.return_value = mock_inst
        mock_resp = MagicMock()
        mock_resp.data = {
            "file": {
                "id": "Fhtml",
                "permalink": "https://example.slack.com/files/abc/meeting.html",
            }
        }
        mock_inst.files_upload_v2.return_value = mock_resp

        url = slack_publisher.upload_summary_html_to_slack(
            html_bytes=b"<!DOCTYPE html><html></html>",
            meeting_id="mid9",
            meeting_info={"name": "MTG"},
        )
        self.assertEqual(url, "https://example.slack.com/files/abc/meeting.html")
        mock_inst.files_upload_v2.assert_called_once()
        kw = mock_inst.files_upload_v2.call_args.kwargs
        self.assertTrue(kw["filename"].endswith(".html"))
        self.assertIn(b"html", kw["content"])

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

    @patch.object(slack_publisher, "WebClient")
    @patch.object(slack_publisher, "settings")
    def test_post_pipeline_failure_message(
        self,
        mock_settings: MagicMock,
        mock_client_cls: MagicMock,
    ) -> None:
        mock_settings.slack_bot_token = "xoxb-test"
        mock_settings.slack_channel_id = "C111"
        mock_inst = MagicMock()
        mock_client_cls.return_value = mock_inst

        slack_publisher.post_pipeline_failure_message(
            meeting_id="mid",
            stage="Claude",
            error_detail="RuntimeError: oops",
        )

        mock_inst.chat_postMessage.assert_called_once()
        kw = mock_inst.chat_postMessage.call_args.kwargs
        self.assertEqual(kw["channel"], "C111")
        self.assertIn("会議自動化エラー", kw["text"])
        self.assertIn("mid", kw["text"])
        self.assertIn("Claude", kw["text"])

    @patch.object(slack_publisher, "WebClient")
    @patch.object(slack_publisher, "settings")
    def test_upload_passes_realistic_png_from_renderer(
        self,
        mock_settings: MagicMock,
        mock_client_cls: MagicMock,
    ) -> None:
        """パイプライン相当の PNG が Slack に渡ること（マジックバイト・最小サイズ）。"""
        meeting = {"name": "検証MTG", "happened_at": "2026-03-01", "participants": []}
        summary = "## 要点\n- テスト\n\n## タスク一覧\n1. **A** - 作業 - 期限未定"
        fake_font = ImageFont.load_default()
        with patch.object(
            image_generator,
            "_resolve_font",
            side_effect=lambda _size: (fake_font, True),
        ):
            png = image_generator.render_summary_png(meeting, summary, width=720)

        mock_settings.slack_bot_token = "xoxb-test"
        mock_settings.slack_channel_id = "C111"
        mock_inst = MagicMock()
        mock_client_cls.return_value = mock_inst
        mock_resp = MagicMock()
        mock_resp.data = {"file": {"id": "Fz"}}
        mock_inst.files_upload_v2.return_value = mock_resp

        slack_publisher.post_meeting_summary_png(
            png_bytes=png,
            meeting_id="mid_png",
            meeting_info=meeting,
        )
        kw = mock_inst.files_upload_v2.call_args.kwargs
        content = kw["content"]
        self.assertTrue(content.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(content), 800)


if __name__ == "__main__":
    unittest.main()
