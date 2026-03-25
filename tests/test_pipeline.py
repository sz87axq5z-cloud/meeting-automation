import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import pipeline as pipeline_mod


class TestPipeline(unittest.TestCase):
    @patch.object(pipeline_mod, "post_pipeline_failure_message")
    @patch.object(pipeline_mod, "meeting_already_completed", return_value=True)
    @patch.object(pipeline_mod, "fetch_meeting_context")
    def test_skip_when_meeting_done(
        self,
        mock_fetch: MagicMock,
        _mock_done: MagicMock,
        mock_notify: MagicMock,
    ) -> None:
        pipeline_mod.run_pipeline("mid")
        mock_fetch.assert_not_called()
        mock_notify.assert_not_called()

    @patch.object(pipeline_mod, "mark_meeting_completed")
    @patch.object(pipeline_mod, "post_meeting_summary_png", return_value="F1")
    @patch.object(pipeline_mod, "create_cards_for_tasks", return_value=[])
    @patch.object(pipeline_mod, "parse_tasks_from_claude_text", return_value=[])
    @patch.object(pipeline_mod, "render_summary_png", return_value=b"png")
    @patch.object(
        pipeline_mod,
        "summarize_and_extract_tasks",
        return_value={"raw_text": "x"},
    )
    @patch.object(
        pipeline_mod,
        "fetch_meeting_context",
        return_value=({"name": "N"}, "hello transcript"),
    )
    @patch.object(pipeline_mod, "meeting_already_completed", return_value=False)
    @patch.object(pipeline_mod, "post_pipeline_failure_message")
    def test_success_marks_completed(
        self,
        mock_notify: MagicMock,
        _mock_done: MagicMock,
        _fetch: MagicMock,
        _claude: MagicMock,
        _png: MagicMock,
        _parse: MagicMock,
        _trello: MagicMock,
        _slack: MagicMock,
        mock_mark: MagicMock,
    ) -> None:
        pipeline_mod.run_pipeline("mid")
        mock_mark.assert_called_once_with("mid")
        mock_notify.assert_not_called()

    @patch.object(pipeline_mod, "post_pipeline_failure_message")
    @patch.object(pipeline_mod, "meeting_already_completed", return_value=False)
    @patch.object(
        pipeline_mod,
        "fetch_meeting_context",
        side_effect=RuntimeError("boom"),
    )
    def test_tldv_failure_notifies(
        self,
        mock_fetch: MagicMock,
        _mock_done: MagicMock,
        mock_notify: MagicMock,
    ) -> None:
        pipeline_mod.run_pipeline("mid")
        mock_notify.assert_called_once()
        kw = mock_notify.call_args.kwargs
        self.assertEqual(kw["meeting_id"], "mid")
        self.assertEqual(kw["stage"], "tl;dv")


if __name__ == "__main__":
    unittest.main()
