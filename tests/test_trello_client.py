import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import trello_client


class TestParseTasks(unittest.TestCase):
    def test_parses_numbered_lines(self) -> None:
        raw = """## 要約
- a

## タスク一覧
1. **田中** - 仕様書 - 金曜
2. 佐藤: レビュー

## その他
x
"""
        tasks = trello_client.parse_tasks_from_claude_text(raw)
        self.assertEqual(len(tasks), 2)
        self.assertIn("田中", tasks[0])
        self.assertIn("佐藤", tasks[1])

    def test_no_tasks_message(self) -> None:
        raw = "## タスク一覧\nタスクはありませんでした\n"
        self.assertEqual(trello_client.parse_tasks_from_claude_text(raw), [])

    def test_no_section(self) -> None:
        self.assertEqual(trello_client.parse_tasks_from_claude_text("hello"), [])

    def test_assignee_filter_keeps_matching_only(self) -> None:
        from app.services.trello_client import filter_tasks_by_assignee

        tasks = [
            "三嶋 - A",
            "高橋 - Meet 設定",
            "高橋圭佑 - 資料",
        ]
        with patch.object(trello_client, "settings") as m:
            m.trello_assignee_filter = "高橋圭佑,高橋"
            got = filter_tasks_by_assignee(tasks)
        self.assertEqual(len(got), 2)
        self.assertTrue(any("高橋 - Meet" in x for x in got))
        self.assertTrue(any("高橋圭佑" in x for x in got))

    def test_task_assignee_prefix_various_dashes(self) -> None:
        from app.services.trello_client import _task_assignee_prefix

        self.assertEqual(_task_assignee_prefix("高橋 - Meet"), "高橋")
        self.assertEqual(_task_assignee_prefix("高橋 – Meet"), "高橋")
        self.assertEqual(_task_assignee_prefix("今林-フォーム"), "今林")

    def test_assignee_filter_empty_means_all(self) -> None:
        from app.services.trello_client import filter_tasks_by_assignee

        tasks = ["a - 1", "b - 2"]
        with patch.object(trello_client, "settings") as m:
            m.trello_assignee_filter = None
            self.assertEqual(filter_tasks_by_assignee(tasks), tasks)
            m.trello_assignee_filter = "  "
            self.assertEqual(filter_tasks_by_assignee(tasks), tasks)

    def test_parses_markdown_table(self) -> None:
        raw = """## タスク一覧
| 担当者 | タスク内容 | 期限 |
|--------|------------|------|
| 三嶋 | 高須さんにアイデアを伝える | 期限未定 |
| 松尾 | リリース | 来週中 |
"""
        tasks = trello_client.parse_tasks_from_claude_text(raw)
        self.assertEqual(len(tasks), 2)
        self.assertIn("三嶋", tasks[0])
        self.assertIn("高須", tasks[0])
        self.assertIn("松尾", tasks[1])


class TestCreateCards(unittest.TestCase):
    @patch.object(trello_client.httpx, "Client")
    @patch.object(trello_client, "settings")
    def test_posts_cards(
        self,
        mock_settings: MagicMock,
        mock_client_cls: MagicMock,
    ) -> None:
        mock_settings.trello_api_key = "k"
        mock_settings.trello_token = "t"
        mock_settings.trello_list_id = "L1"
        mock_settings.trello_assignee_filter = None
        mock_http = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_http
        resp = MagicMock()
        resp.json.return_value = {"id": "c1", "shortUrl": "https://trello.com/c/x"}
        resp.raise_for_status = MagicMock()
        mock_http.post.return_value = resp

        urls = trello_client.create_cards_for_tasks(
            ["task one", "task two"],
            "mid",
            {"url": "https://tldv"},
        )

        self.assertEqual(urls, ["https://trello.com/c/x", "https://trello.com/c/x"])
        self.assertEqual(mock_http.post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
