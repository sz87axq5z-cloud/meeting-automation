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

