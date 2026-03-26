import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import image_generator


class TestRenderSummaryPng(unittest.TestCase):
    def test_outputs_png_magic(self) -> None:
        fake_font = ImageFont.load_default()

        meeting = {"name": "Test MTG", "happened_at": "2026-01-01", "participants": []}
        text = "Summary line one.\nSummary line two."

        with patch.object(
            image_generator,
            "_resolve_font",
            side_effect=lambda _size: (fake_font, True),
        ):
            png = image_generator.render_summary_png(meeting, text, width=400)

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png), 200)
        im = Image.open(BytesIO(png)).convert("RGB")
        # 要件定義どおりダーク背景（旧ライトグレー #f4f4f5 ではない）
        # テキスト領域に入らない左上（MARGIN より手前は全面 COL_BG）
        px = im.getpixel((10, 10))
        self.assertLess(sum(px) / 3, 35)

    def test_parse_summary_sections(self) -> None:
        raw = "前置きのみ"
        self.assertEqual(
            image_generator.parse_summary_sections(raw),
            [(None, "前置きのみ")],
        )
        raw2 = "## 第一\n内容A\n\n## 第二\n内容B"
        sec = image_generator.parse_summary_sections(raw2)
        self.assertEqual(len(sec), 2)
        self.assertEqual(sec[0][0], "第一")
        self.assertIn("内容A", sec[0][1])
        self.assertEqual(sec[1][0], "第二")

    def test_parse_preamble_and_sections(self) -> None:
        raw = "導入文です。\n\n## 要点\n- あ"
        sec = image_generator.parse_summary_sections(raw)
        self.assertEqual(sec[0][0], "概要")
        self.assertIn("導入文", sec[0][1])
        self.assertEqual(sec[1][0], "要点")

    def test_wrap_empty_line_preserved(self) -> None:
        draft = Image.new("RGB", (400, 20))
        draw = ImageDraw.Draw(draft)
        font = ImageFont.load_default()
        lines = image_generator._wrap_to_width(draw, "a\n\nb", font, 300)
        self.assertEqual(lines, ["a", "", "b"])

    def test_noto_download_url_default_and_disable(self) -> None:
        with patch.dict(os.environ):
            os.environ.pop("SUMMARY_FONT_DOWNLOAD_URL", None)
            self.assertEqual(
                image_generator._noto_download_url(),
                image_generator._DEFAULT_JP_FONT_URL,
            )
        with patch.dict(os.environ, {"SUMMARY_FONT_DOWNLOAD_URL": ""}):
            self.assertIsNone(image_generator._noto_download_url())
        with patch.dict(os.environ, {"SUMMARY_FONT_DOWNLOAD_URL": "  "}):
            self.assertIsNone(image_generator._noto_download_url())
        with patch.dict(
            os.environ,
            {"SUMMARY_FONT_DOWNLOAD_URL": "https://example.com/font.otf"},
        ):
            self.assertEqual(
                image_generator._noto_download_url(),
                "https://example.com/font.otf",
            )

    def test_ensure_noto_writes_cache(self) -> None:
        fake_body = b"x" * image_generator._MIN_FONT_BYTES
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_body
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_resp
        mock_cm.__exit__.return_value = None

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / image_generator._TMP_FONT_NAME

            with patch.dict(os.environ, {"SUMMARY_FONT_DOWNLOAD_URL": "https://x/f.otf"}):
                with patch.object(image_generator, "_cached_noto_font_path", return_value=cache):
                    with patch.object(
                        image_generator.urllib.request,
                        "urlopen",
                        return_value=mock_cm,
                    ):
                        path = image_generator._ensure_noto_sans_jp_otf()

            self.assertEqual(path, str(cache))
            self.assertTrue(cache.is_file())
            self.assertEqual(cache.read_bytes(), fake_body)

    def test_ensure_noto_skips_when_download_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / image_generator._TMP_FONT_NAME
            with patch.dict(os.environ, {"SUMMARY_FONT_DOWNLOAD_URL": ""}):
                with patch.object(image_generator, "_cached_noto_font_path", return_value=cache):
                    with patch.object(image_generator.urllib.request, "urlopen") as mock_open:
                        out = image_generator._ensure_noto_sans_jp_otf()
            self.assertIsNone(out)
            mock_open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
