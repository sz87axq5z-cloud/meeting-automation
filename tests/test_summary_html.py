import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.summary_html import (
    build_embedded_task_list_block_html,
    build_summary_html_document,
    extract_task_list_body,
)


class TestSummaryHtml(unittest.TestCase):
    def test_build_escapes_xss_in_heading_and_body(self) -> None:
        raw = """悪意あるタイトル<script>

## 見出し<script>
- 項目<b>x</b>
"""
        html_out = build_summary_html_document(
            {"name": '会議"><script>', "happened_at": "", "participants": []},
            raw,
        )
        # ページ末尾にスクロール用の正当な <script> があるため、ユーザー由来文字列だけ検証する
        self.assertNotIn("悪意あるタイトル<script>", html_out)
        self.assertIn("悪意あるタイトル&lt;script&gt;", html_out)
        self.assertIn("&lt;b&gt;", html_out)

    def test_bold_and_lists(self) -> None:
        raw = """概要段落の**太字**です。

## 決定
- 一点
1. **A** - 作業 - 4/1
"""
        html_out = build_summary_html_document(
            {"name": "定例", "happened_at": "2026-01-01", "participants": ["田中"]},
            raw,
        )
        self.assertIn("<strong>太字</strong>", html_out)
        self.assertIn("<strong>A</strong>", html_out)
        self.assertIn("<ul", html_out)
        self.assertIn("<ol", html_out)
        self.assertIn("定例", html_out)

    def test_guide_style_markers(self) -> None:
        raw = "## 決定\n- x\n"
        html_out = build_summary_html_document(
            {"name": "N", "happened_at": "", "participants": [], "url": "https://t.example/m"},
            raw,
        )
        self.assertIn("read-progress", html_out)
        self.assertIn("IntersectionObserver", html_out)
        self.assertNotIn("情報ソース", html_out)
        self.assertNotIn("https://t.example/m", html_out)
        self.assertIn("縦スクロール図解", html_out)
        self.assertIn("fonts.googleapis.com", html_out)
        self.assertIn("mermaid@11", html_out)

    def test_japanese_line_break_css_present(self) -> None:
        """要約HTMLの<style>に日本語向け折り返し（レスポンシブ）が含まれること。"""
        html_out = build_summary_html_document(
            {"name": "定例", "happened_at": "", "participants": []},
            "## x\ny",
        )
        self.assertIn("line-break: strict", html_out)
        self.assertIn("word-break: normal", html_out)
        self.assertIn("overflow-wrap: break-word", html_out)

    def test_extract_task_list_and_embedded_block(self) -> None:
        raw = """## 決定\n- x\n\n## タスク一覧\n1. **田中** - 作業 - 4/1\n"""
        self.assertIn("1. **田中**", extract_task_list_body(raw))
        emb = build_embedded_task_list_block_html(raw)
        self.assertIn("ma-embed-tasklist", emb)
        self.assertIn("タスク一覧", emb)
        self.assertIn(">田中</div>", emb)
        self.assertIn("作業", emb)

    def test_mermaid_block_renders_figure(self) -> None:
        raw = """概要です。

## フロー
次の流れです。

```mermaid
flowchart LR
  A[開始] --> B[終了]
```

- 補足
"""
        html_out = build_summary_html_document(
            {"name": "M", "happened_at": "", "participants": []},
            raw,
        )
        self.assertIn('class="mermaid-wrap"', html_out)
        self.assertIn("flowchart LR", html_out)
        self.assertIn("開始", html_out)

    def test_task_list_groups_by_assignee(self) -> None:
        raw = """## タスク一覧
1. **田中** - 資料作成 - 4/1
1. **田中** - レビュー - 4/3
1. **佐藤** - 連絡 - 期限未定
"""
        html_out = build_summary_html_document(
            {"name": "MTG", "happened_at": "", "participants": []},
            raw,
        )
        self.assertIn('class="task-group"', html_out)
        self.assertIn(">田中</div>", html_out)
        self.assertIn(">佐藤</div>", html_out)
        # 担当名はブロック見出し1回ずつ
        self.assertEqual(html_out.count(">田中</div>"), 1)
        self.assertEqual(html_out.count(">佐藤</div>"), 1)
        self.assertIn("資料作成", html_out)
        self.assertIn("レビュー", html_out)


if __name__ == "__main__":
    unittest.main()
