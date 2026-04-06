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
    # true / 1 / yes のとき Trello にカードを作らず Slack まで実行（結合テスト用）
    pipeline_skip_trello: bool = False
    webhook_secret: str
    log_level: str = "INFO"
    # 要約 PNG 用。未設定時は macOS/Linux の一般的な日本語フォントを自動検出
    summary_font_path: str | None = None
    # 見出し・KPI 数値用の太字（任意。未設定時はヒラギノ W6 候補や Regular の兄弟 Bold を試す）
    summary_font_bold_path: str | None = None
    # Webhook 冪等用（Upstash Redis REST）。未設定なら重複防止はオフ
    upstash_redis_rest_url: str | None = None
    upstash_redis_rest_token: str | None = None
    # SET … EX の秒数（デフォルト 7 日）
    dedupe_webhook_ttl_seconds: int = 604_800
    dedupe_meeting_ttl_seconds: int = 604_800
    # 要約 HTML を GCS に置いて公開 URL を Slack に載せる（任意。設定時は S3 より優先）
    meeting_html_gcs_bucket: str | None = None
    meeting_html_gcs_prefix: str = "meetings"
    # 要約 HTML を S3 に置く（任意。GCS 未設定時のみ使用）
    meeting_html_s3_bucket: str | None = None
    meeting_html_s3_prefix: str = "meetings"
    meeting_html_s3_region: str = "ap-northeast-1"
    # 例: https://xxxx.cloudfront.net 。GCS 時は storage.googleapis.com の代わりにこのベース＋オブジェクトキー
    # S3 時は未設定なら https://{bucket}.s3.{region}.amazonaws.com を使用
    meeting_html_public_base_url: str | None = None
    # 図解 HTML: GCS 公開バケットへアップロード（未設定ならローカル保存のみ）
    infographic_gcs_bucket: str | None = None
    infographic_gcs_prefix: str = "infographics"
    # 未設定時は slack_channel_id と同じチャンネルへ図解URL・パスワードを投稿
    infographic_slack_channel_id: str | None = None

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

    @field_validator("summary_font_bold_path", mode="before")
    @classmethod
    def _strip_summary_font_bold_path(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator(
        "meeting_html_gcs_bucket",
        "meeting_html_s3_bucket",
        "meeting_html_public_base_url",
        mode="before",
    )
    @classmethod
    def _strip_optional_meeting_html(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("meeting_html_gcs_prefix", mode="before")
    @classmethod
    def _strip_meeting_html_gcs_prefix(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().strip("/")
        return v

    @field_validator(
        "infographic_gcs_bucket",
        "infographic_slack_channel_id",
        mode="before",
    )
    @classmethod
    def _strip_optional_infographic(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("infographic_gcs_prefix", mode="before")
    @classmethod
    def _strip_infographic_prefix(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().strip("/")
        return v

    @field_validator(
        "meeting_html_s3_prefix",
        "meeting_html_s3_region",
        mode="before",
    )
    @classmethod
    def _strip_meeting_html_parts(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


settings = Settings()

