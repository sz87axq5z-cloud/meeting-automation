import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.claude_processor import summarize_and_extract_tasks


def main() -> None:
    dummy_transcript = """
[00:00] 田中: 今日は新しいプロジェクトの進め方について話します。
[00:10] 佐藤: スケジュール感としては来月末リリースを目指したいです。
[00:20] 田中: 私が仕様書をまとめます。締め切りは今週金曜日にします。
""".strip()

    meeting_info = {
        "name": "新プロジェクトMTG",
        "happened_at": "2026-03-16 10:00",
        "participants": ["田中", "佐藤"],
    }

    result = summarize_and_extract_tasks(dummy_transcript, meeting_info)
    print("===== Claude 出力（テスト）=====")
    print(result["raw_text"])


if __name__ == "__main__":
    main()

