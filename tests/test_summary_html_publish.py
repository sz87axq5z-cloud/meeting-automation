import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import summary_html_publish as shp


class TestSummaryHtmlPublish(unittest.TestCase):
    def test_returns_none_when_no_bucket(self) -> None:
        with patch.object(shp.settings, "meeting_html_gcs_bucket", None):
            with patch.object(shp.settings, "meeting_html_s3_bucket", None):
                self.assertIsNone(
                    shp.publish_summary_html(html_bytes=b"<p>x</p>", meeting_id="abc"),
                )

    @patch("app.services.infographic_gcs.upload_html_public_read")
    @patch.object(shp.settings, "meeting_html_public_base_url", "")
    @patch.object(shp.settings, "meeting_html_s3_bucket", None)
    @patch.object(shp.settings, "meeting_html_gcs_prefix", "meetings")
    @patch.object(shp.settings, "meeting_html_gcs_bucket", "my-bucket")
    def test_gcs_upload_returns_storage_url(
        self,
        mock_upload: MagicMock,
    ) -> None:
        mock_upload.return_value = (
            "https://storage.googleapis.com/my-bucket/meetings/mid.html"
        )
        url = shp.publish_summary_html(html_bytes=b"<html/>", meeting_id="mid")
        mock_upload.assert_called_once()
        call_kw = mock_upload.call_args.kwargs
        self.assertEqual(call_kw["bucket_name"], "my-bucket")
        self.assertEqual(call_kw["object_name"], "meetings/mid.html")
        self.assertEqual(call_kw["html_bytes"], b"<html/>")
        self.assertEqual(
            url,
            "https://storage.googleapis.com/my-bucket/meetings/mid.html",
        )

    @patch("app.services.infographic_gcs.upload_html_public_read")
    @patch.object(shp.settings, "meeting_html_public_base_url", "https://cdn.example.com")
    @patch.object(shp.settings, "meeting_html_s3_bucket", None)
    @patch.object(shp.settings, "meeting_html_gcs_prefix", "meetings")
    @patch.object(shp.settings, "meeting_html_gcs_bucket", "my-bucket")
    def test_gcs_respects_public_base_url(
        self,
        mock_upload: MagicMock,
    ) -> None:
        mock_upload.return_value = (
            "https://storage.googleapis.com/my-bucket/meetings/x.html"
        )
        url = shp.publish_summary_html(html_bytes=b"h", meeting_id="x")
        self.assertEqual(url, "https://cdn.example.com/meetings/x.html")

    @patch("boto3.client")
    @patch.object(shp.settings, "meeting_html_gcs_bucket", None)
    @patch.object(shp.settings, "meeting_html_s3_bucket", "s3b")
    @patch.object(shp.settings, "meeting_html_s3_prefix", "meetings")
    @patch.object(shp.settings, "meeting_html_s3_region", "ap-northeast-1")
    @patch.object(shp.settings, "meeting_html_public_base_url", "")
    def test_s3_when_gcs_unset(self, mock_boto_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        url = shp.publish_summary_html(html_bytes=b"<p/>", meeting_id="m2")
        mock_client.put_object.assert_called_once()
        self.assertEqual(
            url,
            "https://s3b.s3.ap-northeast-1.amazonaws.com/meetings/m2.html",
        )

    @patch("boto3.client")
    @patch("app.services.infographic_gcs.upload_html_public_read")
    @patch.object(shp.settings, "meeting_html_public_base_url", "")
    @patch.object(shp.settings, "meeting_html_s3_bucket", "s3-fallback")
    @patch.object(shp.settings, "meeting_html_s3_prefix", "meetings")
    @patch.object(shp.settings, "meeting_html_gcs_prefix", "meetings")
    @patch.object(shp.settings, "meeting_html_gcs_bucket", "gcs-primary")
    def test_gcs_takes_precedence_over_s3(
        self,
        mock_upload: MagicMock,
        mock_boto_client: MagicMock,
    ) -> None:
        mock_upload.return_value = (
            "https://storage.googleapis.com/gcs-primary/meetings/z.html"
        )
        url = shp.publish_summary_html(html_bytes=b"x", meeting_id="z")
        mock_upload.assert_called_once()
        mock_boto_client.assert_not_called()
        self.assertIn("storage.googleapis.com", url or "")


if __name__ == "__main__":
    unittest.main()
