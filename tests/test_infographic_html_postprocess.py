import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.infographic_html_postprocess import (
    find_infographic_sources_section_span,
    patch_infographic_html,
)


class TestInfographicHtmlPostprocess(unittest.TestCase):
    def test_find_span_info_source(self) -> None:
        html = """<body><div class="wrap">
        <div class="info-source"><h3>情報ソース</h3><p>x</p></div>
        </div></body>"""
        span = find_infographic_sources_section_span(html)
        self.assertIsNotNone(span)
        start, end = span
        self.assertIn("info-source", html[start:end])
        self.assertIn("情報ソース", html[start:end])

    def test_find_span_sources(self) -> None:
        html = '<div class="sources"><h3>情報ソース</h3><p>a</p></div>'
        span = find_infographic_sources_section_span(html)
        self.assertIsNotNone(span)

    def test_find_span_nested_inner_div(self) -> None:
        html = (
            '<div class="info-source"><h3>情報ソース</h3>'
            '<div class="inner"><p>note</p></div><p>end</p></div>'
        )
        span = find_infographic_sources_section_span(html)
        self.assertIsNotNone(span)
        start, end = span
        self.assertTrue(html[start:end].endswith("</div>"))
        self.assertIn("inner", html[start:end])

    def test_patch_inserts_task_before_sources(self) -> None:
        html = """<main>
        <div class="info-source"><h3>情報ソース</h3><p>old</p></div>
        </main>"""
        raw = "## タスク一覧\n1. **田中** - 作業 - 4/1\n"
        out = patch_infographic_html(html, {"name": "定例MTG"}, raw)
        self.assertIn("ma-embed-tasklist", out)
        self.assertIn(">田中</div>", out)
        self.assertIn("定例MTG", out)
        self.assertNotIn("old", out)
        self.assertLess(out.index("ma-embed-tasklist"), out.index('class="sources"'))

    def test_patch_fallback_body(self) -> None:
        html = "<html><body><p>x</p></body></html>"
        raw = "## タスク一覧\n1. **A** - b - 期限未定\n"
        out = patch_infographic_html(html, {"name": "N"}, raw)
        self.assertIn("ma-embed-tasklist", out)
        self.assertIn("N", out)
        self.assertIn("</body>", out.lower())


if __name__ == "__main__":
    unittest.main()
