"""
要約 HTML の「公開 URL 文字列を組み立てる」部分のみの最小テスト（アップロードは含まない）。
"""

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.infographic_gcs import build_gcs_public_url
from app.services.summary_html_publish import (
    _object_key_for_meeting,
    _public_url_with_optional_base,
    _safe_object_key_segment,
)


class TestSummaryHtmlPublicUrl(unittest.TestCase):
    def test_public_url_empty_base_returns_default(self) -> None:
        u = _public_url_with_optional_base(
            base=None,
            key="meetings/abc.html",
            default_url="https://storage.googleapis.com/b/meetings/abc.html",
        )
        self.assertEqual(u, "https://storage.googleapis.com/b/meetings/abc.html")

    def test_public_url_custom_base_appends_encoded_key(self) -> None:
        u = _public_url_with_optional_base(
            base="https://cdn.example.com/",
            key="meetings/foo bar.html",
            default_url="ignored",
        )
        self.assertEqual(u, "https://cdn.example.com/meetings/foo%20bar.html")

    def test_object_key_prefix_and_safe_segment(self) -> None:
        self.assertEqual(
            _object_key_for_meeting("mid-1", "meetings"),
            "meetings/mid-1.html",
        )
        self.assertEqual(
            _object_key_for_meeting("a/b?c", "prefix"),
            "prefix/a_b_c.html",
        )

    def test_safe_segment_fallback(self) -> None:
        self.assertEqual(_safe_object_key_segment(""), "meeting")
        self.assertEqual(_safe_object_key_segment("___"), "meeting")

    def test_build_gcs_public_url_matches_storage_host(self) -> None:
        """GCS 既定 URL 形式（upload 成功時の default と同型）。"""
        u = build_gcs_public_url("my-bucket", "meetings/x.html")
        self.assertEqual(u, "https://storage.googleapis.com/my-bucket/meetings/x.html")


if __name__ == "__main__":
    unittest.main()
