"""
ローカル PNG プレビュー・Slack 手動テスト用のダミー会議データ。
"""

from __future__ import annotations

from typing import Any, Dict

SAMPLE_MEETING: Dict[str, Any] = {
    "name": "プレビュー用ダミー会議",
    "happened_at": "2026-03-24T10:00:00.000Z",
    "participants": ["太郎", "花子"],
}

SAMPLE_SUMMARY = """## 決定事項
- 次回リリースは 4/1 を目標にする
- デザインは要件定義 HTML のダークテーマに合わせた

## 課題・リスク
- フォント同梱が未完了の環境では初回ダウンロードに時間がかかる

## タスク一覧
1. **太郎** - API 接続確認 - 2026-03-28
2. **花子** - Slack 通知文言調整 - 期限未定
"""
