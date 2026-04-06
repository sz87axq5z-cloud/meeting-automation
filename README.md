# Meeting Automation Backend (議事録自動化サーバー)

このプロジェクトは、tl;dv の文字起こしをもとに Claude で要約とタスク抽出を行い、Trello と Slack に自動連携するためのバックエンドです。

## ローカルでの動かし方（ざっくり）

1. Python 仮想環境を作る

```bash
cd meeting-automation
python3 -m venv .venv
source .venv/bin/activate
```

2. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

3. `.env` ファイルを作成し、`.env.example` を参考に各種APIキーを設定

4. 開発サーバーを起動

```bash
uvicorn app.main:app --reload
```

5. ブラウザで `http://localhost:8000/health` にアクセスして `{\"status\":\"ok\"}` が返れば準備完了です。

### テストの実行

`meeting-automation` をカレントにしてから実行する（推奨）:

```bash
cd meeting-automation
source .venv/bin/activate
python -m unittest discover -s tests -p 'test_*.py' -v
```

個別ファイルを直接実行する場合も、上記と同じディレクトリから `python tests/test_trello_client.py` で動くようにパスを補正済みです。`/usr/local/bin/python3` で親フォルダがパスに入っていないと `ModuleNotFoundError: No module named 'app'` になるので、**必ず `meeting-automation` に `cd` してから**実行してください。

- **要約 PNG**: `tests/test_image_generator.py` でダークテーマ背景・`##` セクション分割を検証します。
- **Slack へ渡すバイト列**: `tests/test_slack_publisher.py` の `test_upload_passes_realistic_png_from_renderer` で、レンダラが出力した PNG のマジックバイトとサイズを確認します。
- **実 Slack 投稿（任意）**: 有効な Bot トークンで `MEETING_AUTOMATION_LIVE_SLACK=1 python -m unittest tests.test_live_slack_png` を実行。
- **ローカルで PNG を目視**: `python scripts/render_summary_preview.py -o /tmp/summary.png`（初回は `fonts/NotoSansCJKjp-Regular.otf` 同梱推奨。未取得時は notofonts の OTF をダウンロードしますがサイズ約16MBです）
- **ローカルで Slack に PNG 投稿テスト**（プレビューと同じダミー要約）: `.env` に `SLACK_BOT_TOKEN` / `SLACK_CHANNEL_ID` を入れたうえで `python scripts/send_preview_to_slack.py`（`--meeting-id` でファイル名用 ID を任意指定可）
- **要約 HTML のローカル公開 URL（テスト）**: `python scripts/serve_meeting_summary_local.py <tl;dv会議ID>` で `artifacts/local_public_http/` に HTML を書き、`http://127.0.0.1:（自動割当ポート）/meeting_….html` を表示。同一 Wi‑Fi から試すときは `--lan`。インターネット向けにはそのポートに ngrok 等を当てる。

## Vercel へのデプロイ

1. このディレクトリを GitHub リポジトリとして登録
2. Vercel ダッシュボードから「New Project」を作成し、このリポジトリを選択
3. Vercel の「Environment Variables」に `.env.example` と同じキーを登録
4. デプロイ後、`https://xxx.vercel.app/health` で動作確認

### Webhook 認証（`WEBHOOK_SECRET`）

`POST /webhook` は、次の **どちらか**で通ります。

**A. `WEBHOOK_SECRET` と一致**（次のいずれかで渡す）

1. クエリ `?token=`
2. ヘッダー `X-Webhook-Secret` / `X-Webhook-Token`
3. ヘッダー `Authorization: Bearer <secret>`

**B. tl;dv の API キー** — ヘッダー `x-api-key` が環境変数 `TLDV_API_KEY` と一致（tl;dv の Webhook「APIキー」認証向け）

`TLDV_API_KEY` / `WEBHOOK_SECRET` などは読み込み時に前後空白を除去します（Vercel のコピペで `Invalid token` になるのを防ぐため）。

tl;dv が登録 URL のクエリを POST に付けない場合は、`x-api-key` か上記ヘッダーで `WEBHOOK_SECRET` を渡してください。

### 要約 HTML の公開 URL（任意）

Claude の要約から **単一ページの HTML** を生成します。**公開 HTTPS URL** を PNG 投稿のコメントに **「ブラウザで開く（図解ページ）」** として載せるには、次のいずれかを設定します。

1. **GCS（推奨・図解と同じ認証で可）**  
   `MEETING_HTML_GCS_BUCKET` と `GOOGLE_APPLICATION_CREDENTIALS`（図解の `INFOGRAPHIC_GCS_BUCKET` と同じバケットでも別プレフィックスでも可）。**設定されているときは S3 より優先**されます。
2. **S3**  
   `MEETING_HTML_S3_BUCKET` と AWS 認証（`MEETING_HTML_GCS_BUCKET` が空のときのみ使用）。

Slack に `.html` を添付するとアプリ内で **ソース表示**になりやすいため、パイプラインからは **HTML ファイルを Slack に投稿しません**。GCS/S3 とも未設定のときはコメントに設定案内が1行付きます（手動で `upload_summary_html_to_slack` を使うデバッグ用関数は `slack_publisher` に残しています）。

- `.env.example` の `MEETING_HTML_GCS_*` / `MEETING_HTML_S3_*` を参照
- オブジェクトは **匿名で GET できる**ようにする（または `MEETING_HTML_PUBLIC_BASE_URL` に CDN のベース URL を指定）

#### 本番に近い手動テスト（GCS または S3 ＋ パイプライン）

**GCS の場合**

1. 公開読み取り可能な GCS バケットを用意し、サービスアカウントに `storage.objects.create` を付与（図解用と共通でよい）。
2. `.env` に `MEETING_HTML_GCS_BUCKET` と `GOOGLE_APPLICATION_CREDENTIALS` を設定（任意で `MEETING_HTML_GCS_PREFIX=meetings`）。

**S3 の場合**

1. AWS で S3 バケットを用意し、**公開読み取り**（または CloudFront 経由）で HTML を配信できるようにする。
2. IAM に `s3:PutObject` を付与し、`.env` に `MEETING_HTML_S3_BUCKET` と `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` を設定。

**共通**

```bash
cd meeting-automation
.venv/bin/python scripts/run_pipeline_for_meeting.py --check-env あなたの会議ID   # 設定確認のみ
.venv/bin/python scripts/run_pipeline_for_meeting.py あなたの会議ID
```

Slack の PNG 投稿コメントに **要約（HTML）／ブラウザで開く** の URL が付いているか確認。シークレットウィンドウで開き、ログインなしで HTML が表示されるかも確認する。

**注意**: `UPSTASH_REDIS_REST_*` が有効なとき、**同じ会議 ID は一度成功すると再実行されない**（重複防止）。再テストする場合は Redis のキーを消すか、別の会議 ID を使う。

### 図解 HTML（インフォグラフィック）の GCS 公開 ＋ パスワード ＋ Slack（任意）

`scripts/generate_meeting_infographic_html.py` は、`.env` に **`INFOGRAPHIC_GCS_BUCKET`** を設定し、かつ **Google Cloud 認証**（例: `GOOGLE_APPLICATION_CREDENTIALS` にサービスアカウント JSON のパス）が効いているとき、次を自動で行います。

1. 平文の図解 HTML を生成したうえで、**ランダムなパスワード**を発行する。
2. ブラウザでパスワード入力後に **Web Crypto（AES-GCM）** で復号する **単一 HTML** に包む（平文は GCS に置かない）。
3. GCS の指定プレフィックス（既定 `infographics/`）にアップロードし、`https://storage.googleapis.com/...` 形式の **公開 URL** を得る。
4. **`INFOGRAPHIC_SLACK_CHANNEL_ID`** があればそのチャンネル、なければ **`SLACK_CHANNEL_ID`** に、**公開 URL とパスワード**をテキスト投稿する（関係者へ両方を共有する運用向け）。

ローカルには **暗号化済み HTML** と、同じファイル名stemの **`.password.txt`**（パスワード1行）も `artifacts/` に保存されます。

- **公開を止めたいとき**: `INFOGRAPHIC_GCS_BUCKET` を空にするか、`--local-only` を付けて実行（従来どおり平文 HTML のみ保存）。
- **バケット側**: アップロードしたオブジェクトが **匿名で `GET` できる**ようにする（または公開 CDN オリジン）。サービスアカウントには少なくとも `storage.objects.create` が必要。
- **セキュリティの限界**: これは本格的なログイン認証ではなく、**ブラウザ内の復号**による閲覧制限です。チャンネル権限の設計とセットで運用してください。詳細は `docs/infographic_password_gcs_flow_ja.html` を参照。

**Claude なしで GCS だけ試す**: 手元の平文 `.html`（例: `artifacts/meeting_*_infographic_raw_prompt.html`）から暗号化してアップロードするには:

```bash
cd meeting-automation
.venv/bin/python scripts/publish_infographic_html_from_file.py artifacts/meeting_xxx_infographic_raw_prompt.html
```

`--no-gcs` で暗号化＋`.password.txt` のみ。`--post-slack` でアップロード後に Slack に URL とパスワードを投稿。

### Webhook の二重受信と失敗通知（任意）

Vercel ではサーバーが都度別インスタンスになるため、**同じ tl;dv 通知の再送**を防ぐには共有ストアが必要です。[Upstash](https://upstash.com/) などで Redis を作成し、コンソールに表示される **REST URL** と **Token** を環境変数 `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` に設定してください（`.env.example` 参照）。未設定の場合は従来どおり重複防止はオフです。

設定済みのときは Webhook JSON の `id` が必須になり、再送は `{"status":"duplicate"}` で応答します。パイプラインがどこかで失敗した場合は、**要約 PNG と同じ Slack チャンネル**に短文のエラー通知が送られます。

