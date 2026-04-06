import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.infographic_ja_softbreak import apply_infographic_ja_softbreaks
from app.services.infographic_html_postprocess import patch_infographic_html


class TestInfographicJaSoftbreak(unittest.TestCase):
    def test_punctuation_inserts_wbr_in_section_p(self) -> None:
        html = (
            "<html><head></head><body>"
            '<div class="section"><p>長い文、次の文。続き。</p></div>'
            "</body></html>"
        )
        out = apply_infographic_ja_softbreaks(html)
        self.assertRegex(out, r"、<wbr\s*/?>")
        self.assertRegex(out, r"。<wbr\s*/?>")

    def test_metric_number_not_split(self) -> None:
        html = (
            "<html><body>"
            '<div class="section"><p>売上は</p></div>'
            '<span class="metric-number">23,000</span>'
            "</body></html>"
        )
        out = apply_infographic_ja_softbreaks(html)
        self.assertEqual(out.count("<wbr>"), 0)
        self.assertIn("23,000", out)

    def test_link_text_not_touched(self) -> None:
        html = (
            "<html><body>"
            '<div class="section"><p><a href="#">ここ、内側。</a>外側で、続く。</p></div>'
            "</body></html>"
        )
        out = apply_infographic_ja_softbreaks(html)
        a_open = out.find("<a ")
        a_close = out.find("</a>")
        self.assertGreater(a_open, 0)
        self.assertGreater(a_close, a_open)
        anchor_region = out[a_open:a_close]
        self.assertNotIn("<wbr", anchor_region)
        self.assertRegex(out, r"外側で、<wbr\s*/?>")

    def test_patch_infographic_applies_softbreak(self) -> None:
        html = """<html><head></head><body><main>
        <div class="section"><p>あ、いう。次へ。</p></div>
        <div class="sources"><h3>情報ソース</h3><p>old</p></div>
        </main></body></html>"""
        raw = "## タスク一覧\n1. **田中** - 作業 - 4/1\n"
        out = patch_infographic_html(html, {"name": "定例MTG"}, raw)
        self.assertRegex(out, r"あ、<wbr\s*/?>")
        self.assertRegex(out, r"。<wbr\s*/?>")
        self.assertIn("ma-ja-linebreak", out)


if __name__ == "__main__":
    unittest.main()
