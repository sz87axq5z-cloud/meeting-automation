import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_wrap_empty_line_preserved(self) -> None:
        draft = Image.new("RGB", (400, 20))
        draw = ImageDraw.Draw(draft)
        font = ImageFont.load_default()
        lines = image_generator._wrap_to_width(draw, "a\n\nb", font, 300)
        self.assertEqual(lines, ["a", "", "b"])


if __name__ == "__main__":
    unittest.main()
