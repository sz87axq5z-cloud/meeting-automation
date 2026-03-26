from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# cwd に依存しない（親ディレクトリからスクリプトを実行しても .env を読む）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tldv_api_key: str
    # https://doc.tldv.io/ — 本番は https://pasta.tldv.io
    tldv_base_url: str = "https://pasta.tldv.io"
    anthropic_api_key: str
    slack_bot_token: str
    slack_channel_id: str
    trello_api_key: str
    trello_token: str
    trello_board_id: str
    trello_list_id: str
    # カンマ区切り。設定時はこの名前にマッチする担当のタスクだけ Trello にカード化（空なら全員）
    trello_assignee_filter: str | None = None
    webhook_secret: str
    log_level: str = "INFO"
    # 要約 PNG 用。未設定時は macOS/Linux の一般的な日本語フォントを自動検出
    summary_font_path: str | None = None
    # Webhook 冪等用（Upstash Redis REST）。未設定なら重複防止はオフ
    upstash_redis_rest_url: str | None = None
    upstash_redis_rest_token: str | None = None
    # SET … EX の秒数（デフォルト 7 日）
    dedupe_webhook_ttl_seconds: int = 604_800
    dedupe_meeting_ttl_seconds: int = 604_800

    @field_validator(
        "tldv_api_key",
        "webhook_secret",
        "anthropic_api_key",
        "slack_bot_token",
        "slack_channel_id",
        "trello_api_key",
        "trello_token",
        mode="before",
    )
    @classmethod
    def _strip_secrets_and_ids(cls, v: object) -> object:
        """Vercel/.env の改行・前後空白で x-api-key 認証が不一致になるのを防ぐ。"""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("trello_board_id", "trello_list_id", mode="before")
    @classmethod
    def _strip_trello_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("trello_assignee_filter", mode="before")
    @classmethod
    def _strip_assignee_filter(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lstrip("\ufeff")
        return v


settings = Settings()

