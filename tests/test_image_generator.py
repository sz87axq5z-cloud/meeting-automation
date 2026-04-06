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
from app.summary_preview_sample import SAMPLE_MEETING, SAMPLE_SUMMARY


class TestRenderSummaryPng(unittest.TestCase):
    def test_strip_mermaid_for_png(self) -> None:
        raw = """Line one.

```mermaid
flowchart TD
  A-->B
```

Line two."""
        out = image_generator.strip_mermaid_fences_for_png(raw)
        self.assertNotIn("flowchart TD", out)
        self.assertIn("HTML 版", out)
        self.assertIn("Line one", out)
        self.assertIn("Line two", out)

    def test_slack_diagram_sample_full_layout(self) -> None:
        """Slack 投稿と同じサンプルで図解 PNG を生成し、既定幅・構造を検証する。"""
        fake_font = ImageFont.load_default()
        with patch.object(
            image_generator,
            "_resolve_font",
            side_effect=lambda _size: (fake_font, True),
        ):
            png = image_generator.render_summary_png(
                SAMPLE_MEETING,
                SAMPLE_SUMMARY,
            )

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png), 5_000)
        im = Image.open(BytesIO(png)).convert("RGB")
        self.assertEqual(im.width, image_generator.DEFAULT_WIDTH)
        self.assertGreater(im.height, 400)
        px_top = im.getpixel((10, 10))
        self.assertLess(sum(px_top) / 3, 80)

    def test_infographic_png_from_static_text_no_claude_api(self) -> None:
        """
        Claude / Anthropic API を呼ばず、固定の日本語要約だけで図解 PNG を生成できること。
        （本番は Claude 出力を渡すが、レンダラ単体テストではネットワーク・API キー不要）
        """
        meeting = {
            "name": "静的テスト・図解PNG",
            "happened_at": "2026-03-29",
            "participants": ["テスト太郎"],
        }
        summary = """求職者と企業をマッチングするプラットフォームでは、戦略的な運用が特徴です。良い情報が埋もれている状況です。

## 決定事項
- マッチングフローを現行のまま継続する

## 課題
- 表示幅が狭い端末での改行確認用の長い文をここに置く

## タスク一覧
1. **テスト太郎** - 動作確認 - 未定
"""
        fake_font = ImageFont.load_default()
        with patch.object(
            image_generator,
            "_resolve_font",
            side_effect=lambda _size: (fake_font, True),
        ):
            png = image_generator.render_summary_png(meeting, summary)

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png), 5_000)
        im = Image.open(BytesIO(png)).convert("RGB")
        self.assertEqual(im.width, image_generator.DEFAULT_WIDTH)
        self.assertGreater(im.height, 400)

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
        # 上部ダークヒーロー + 下部ライト本文（Truspo 風）
        px = im.getpixel((10, 10))
        self.assertLess(sum(px) / 3, 55)
        if im.height > 280:
            mid = im.getpixel((im.width // 2, min(im.height - 40, 220)))
            self.assertGreater(sum(mid) / 3, 180)

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

    def test_split_insight_section(self) -> None:
        rest, ins = image_generator._split_insight_section(
            [("概要", "導入"), ("要点", "本文")],
        )
        self.assertEqual(ins, "導入")
        self.assertEqual(len(rest), 1)
        self.assertEqual(rest[0][0], "要点")
        r2, i2 = image_generator._split_insight_section([("要点", "のみ")])
        self.assertIsNone(i2)
        self.assertEqual(len(r2), 1)

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

    def test_group_task_section_body_merges_same_assignee(self) -> None:
        body = (
            "1. **高橋** - A - 4/1\n"
            "2. **濱上** - B\n"
            "3. **高橋** - C - 未定"
        )
        out = image_generator._group_task_section_body("タスク一覧", body)
        self.assertIn("高橋", out)
        self.assertIn("- A - 4/1", out)
        self.assertIn("- C - 未定", out)
        self.assertIn("濱上", out)
        self.assertIn("- B", out)
        self.assertLess(out.count("高橋"), 3)

    def test_group_task_section_body_skips_non_task_heading(self) -> None:
        body = "1. **太郎** - x"
        self.assertEqual(
            image_generator._group_task_section_body("決定事項", body),
            body,
        )

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
