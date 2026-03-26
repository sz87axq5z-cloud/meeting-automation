from typing import Any, Dict, List

from anthropic import Anthropic

from app.config import settings


client = Anthropic(api_key=settings.anthropic_api_key)


def summarize_and_extract_tasks(
    transcript_text: str,
    meeting_info: Dict[str, Any],
) -> Dict[str, Any]:
    """
    文字起こしテキストと会議情報を受け取り、
    Claude に要約＋タスク抽出をさせる。

    まずは素のテキストを返し、挙動を確認する段階とする。
    """

    system_prompt = """
あなたは議事録の要約とタスク抽出の専門家です。
以下の会議の文字起こしを分析し、「要約」と「タスク一覧」を日本語で分かりやすく出力してください。

ルール:
1. 要約は会議の重要ポイントを3〜7個に分け、それぞれ Markdown の ## 見出し（例: ## 決定事項）の直後に本文・箇条書きを書く（Slack用の図解画像でカード分けされる）
2. タスクは「誰が」「何を」「いつまでに」を明確に書く
3. 期限が明示されていない場合は「期限未定」と書く
4. タスクが見つからない場合は「タスクはありませんでした」と明記する
5. 最後に必ず「## タスク一覧」セクションを付け、番号付きリストで書くこと（例: 1. **名前** - 内容 - 期限）。表（Markdownテーブル）は使わないこと
""".strip()

    participants: List[str] = list(meeting_info.get("participants", []))

    user_content = f"""
## 会議情報
- 会議名: {meeting_info.get('name')}
- 日時: {meeting_info.get('happened_at')}
- 参加者: {', '.join(participants) if participants else '不明'}

## 文字起こし
{transcript_text}
""".strip()

    # Anthropic ドキュメントの現行 ID（古い sonnet は 404）
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_content},
        ],
    )

    # Claude からの返答は content の最初の text に入っている想定
    text = message.content[0].text

    return {"raw_text": text}

