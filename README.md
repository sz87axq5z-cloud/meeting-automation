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

tl;dv が登録 URL のクエリを POST に付けない場合は、`x-api-key` か上記ヘッダーで `WEBHOOK_SECRET` を渡してください。

### Webhook の二重受信と失敗通知（任意）

Vercel ではサーバーが都度別インスタンスになるため、**同じ tl;dv 通知の再送**を防ぐには共有ストアが必要です。[Upstash](https://upstash.com/) などで Redis を作成し、コンソールに表示される **REST URL** と **Token** を環境変数 `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` に設定してください（`.env.example` 参照）。未設定の場合は従来どおり重複防止はオフです。

設定済みのときは Webhook JSON の `id` が必須になり、再送は `{"status":"duplicate"}` で応答します。パイプラインがどこかで失敗した場合は、**要約 PNG と同じ Slack チャンネル**に短文のエラー通知が送られます。

