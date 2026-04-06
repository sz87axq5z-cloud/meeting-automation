#!/usr/bin/env python3
"""
会議 ID の文字起こしを入力に、指定の system プロンプト（そのまま）で Claude に
縦スクロール図解の単一 HTML を生成し、artifacts に保存する。

  cd meeting-automation
  .venv/bin/python scripts/generate_meeting_infographic_html.py <会議ID>

- 既定: `.env` に `INFOGRAPHIC_GCS_BUCKET` と GCS 認証（例: `GOOGLE_APPLICATION_CREDENTIALS`）が
  ある場合、**パスワード保護付き単一HTML** にし、GCS へアップロードして **公開URL＋パスワードを Slack** に投稿する。
- `--local-only`: 平文HTMLのみ従来どおりローカル保存（暗号化・GCS・Slack なし）。

前提: .env に TLDV_API_KEY / ANTHROPIC_API_KEY（Slack 投稿には SLACK_* も）
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")

# ユーザー指定のプロンプトを一字一句変えずに system に渡す
INFOGRAPHIC_SYSTEM_PROMPT = r"""# やってほしいこと

指定した概念、言葉、文章について図解を作成してください。知識が全くない人でも**技術の実際の仕組みと利点**が**5分**で理解できる**縦スクロール型**の読み応えのあるインタラクティブな図解を作成してください。

# 役割

あなたは、複雑な技術的概念の**本質的な仕組みを保持したまま、専門用語だけを平易な言葉に置き換えて**解説するテクニカルストーリーライター兼インフォグラフィックデザイナーです。

# 詳細

これから指定する技術について、**実際にどのように動作し、なぜ価値があるのか**を**5分**で理解できる**縦スクロール型**のインタラクティブな図解を作成してください。**上から下へ自然に視線が流れ、スクロールしながら段階的に理解が深まる構成**にしてください。

# 図解を見る人

非エンジニアやその概念にリテラシーのない人を対象とします。**専門用語は平易な言葉に置き換えますが、技術の動作原理や仕組みは省略せずに説明**してください。例：「API」→「他のシステムと会話するための窓口」のように、機能を正確に表現する具体的な言い換えを使用してください。

# デザイン

デザインは信頼性と親しみやすさを両立させる現代的でフラットデザインを基調としてください。読みやすさとテーマに合ったデザインコンセプトを守ることを大事にします。絵文字よりもシンプルな線画アイコンを使用します。絵文字は使用せずフリーで使える洗練されたアイコンを使用します。**必ず縦長のシングルページレイアウトとし、スライド型やタブ切り替え型は採用しません。**白背景に白文字など文字が読みにくい状態にならないようにしてください。

# 処理のフロー

あなたはプロのテクニカルストーリーライターの役割をこなした後にプロのインフォグラフィックデザイナーに変貌します。

## 1. ライターフェーズ

まずは、プロのライター兼編集者として徹底したリサーチを行います。絶対にいきなり作業をしてはいけません。**技術の動作原理、アーキテクチャ、データフロー、利点、歴史的経緯、他の代表的な解決との比較、と制約を正確に理解**してください。その上で、**専門用語を噛み砕きながら、実際の仕組みをステップバイステップで説明する方法**を考えてください。リサーチを終えたら**縦スクロールで段階的に理解が深まる**構成案を３つ作って批判的に見比べた上で気づきを得て新たな構成案を作ってください。**技術の核心部分を簡略化せず、丁寧に説明**することを重視してください。

## 2. デザイナーフェーズ

完成したらあなたはプロのインフォグラフィックデザイナーに変わります。脳のスイッチを切り替えてください。まずはテーマに沿っていて尚且つ読みやすいわかりやすいデザインコンセプトを考えることからスタートします。次に、 **技術の動作フローや相互作用を視覚的に表現**し、**縦スクロール型の図解**として最も効果的な表現方法を検討してください。**各セクションは縦に連続して配置し、前のセクションの理解が次のセクションの理解を助ける構成**にします。**図表やフローチャートを活用して、言葉だけでは伝わりにくい仕組みを可視化**してください。必ずクリック可能な情報ソースを最後に載せてください。

## 3. 最終仕上げフェーズ

仕事の価値は最後の詰めで決まります。ライター兼デザイナーとして自分のアウトプットを2回批判的にみて最後の仕上げを行なってください。特に以下を確認してください：

- **【重要】ハルシネーションや表記崩れがないか**
- **技術の本質的な仕組みが省略されていないか**
- **専門用語の言い換えが機能を正確に表現しているか**
- **縦スクロールの流れで段階的に理解が深まるか**

# 共通方針

- 全ての作業は品質第一で時間を最大限つかって内省的かつ本質的な仕事に取り組んでください
- 処理の途中経過で今の考えを出力してください
- 概念について迎合的にならず批判的な目線も忘れずに説明をしてください
- **なぜその技術が必要で、どのような問題を解決するのか**を明確にしてください
- **必ず縦スクロール型のシングルページデザインで作成してください**
- **技術の複雑さを尊重し、安易な単純化は避けてください**

# 日本語スタイル（クライアント向け・必須）

HTML に表示する**見出し・本文・キャプション・リスト**の日本語は、次を満たしてください。

- **文体**: 常体（だ・である）と敬体（です・ます）を混ぜない。**です・ますで最後まで統一**する。
- **AI 定型の回避**: 次の語尾・表現に頼りすぎない。「〜することが重要です」「〜という仕組みとなっています」「〜を実現します」「まさに」「まとめると」「多岐にわたる」「不可欠」「最適な」「抜本的に」「本質的に」。代わりに**誰が・何を・いつまでに**に落ちる短文にする。
- **抽象語の連打を避ける**: 「本質」「相乗効果」「最適化」「シナジー」「包括的」などを**連続して使わない**。使う段落では、その近くに**文字起こしに根拠がある具体**（固有名・日付・数値・手順の一歩）を**少なくとも 1 つ**入れる。
- **リズム**: 1 文は**60〜70 文字を目安**に区切る。同じ接続詞（「また」「さらに」「その結果」）を**隣り合う段落で 3 回以上**繰り返さない。
- **事実**: 文字起こしにない評価・成果・決定は書かない。未確定は「文字起こし上は未確定です」などと明記する。
- **トーン**: 読者はクライアント想定。**上から目線の教科書調**より、丁寧で具体的なビジネス文書調にする。

## 数値のカンマ区切り（必須）

HTML に表示する数値は**正しい 3 桁区切り**にすること。
- 例: `23000000` → `23,000,000`（正）、`23000,000` は**誤り**。
- 桁数を数え直して**右から 3 桁ごと**にカンマを打つ。迷ったら桁数を声に出して確認する。

## 日本語の折り返し・レスポンシブ（CSS・必須）

`<html lang="ja">` の単一ページにおいて、**スマホ（幅 320px〜）でもテキストやカードがはみ出さない**ようにするため、次を **必ず** `<style>` に含める。

### グローバル設定
```css
*, *::before, *::after { box-sizing: border-box; }
body {
  line-break: strict;
  word-break: normal;
  overflow-wrap: break-word;
  margin: 0; padding: 0;
}
```
※ `word-break: keep-all` は日本語では文字間の折り返しを全て禁止してしまい、テキストがコンテナからはみ出すため **使用禁止**。`overflow-wrap: normal` も同様に禁止。

### HTML での折り位置の補助（`<wbr>`・任意だが推奨）
- **長い見出し・本文・リスト**では、**読点 `、` の直後**（必要なら句点 `。`・感嘆疑問 `！` `？` の直後）に `<wbr>` を入れてよい。モバイル幅で文の区切りに寄せて折れやすくなる。
- **数値（3 桁カンマ含む）・URL・英単語の途中**には入れない。属性値の中にタグを書かない（HTML エスケープに注意）。
- パイプラインの後処理でも句読点直後に `<wbr>` を機械的に挿入するため**必須ではない**が、意図した位置なら追記してよい。

### はみ出し防止（必須）
- **全てのコンテナ・カード・セクション**に `max-width: 100%;` を付与する。固定の `width`（px）を使う場合は必ず `max-width: 100%` も併記する。
- **見出し（h1〜h3）** にも `overflow-wrap: break-word;` を付けて、長いタイトルがはみ出さないようにする。
- **画像・SVG・iframe** には `max-width: 100%; height: auto;` を付ける。

### カード型グリッド
- 列の **最小幅を 280px 以上**（例: `minmax(min(100%, 280px), 1fr)`）。
- **640px 以下では必ず 1 列**にする `@media` を書く。

### フォントサイズ
- **カード内の見出し・本文**は `font-size: clamp(...)` で、狭い幅でもフォントを下げて行あたりの文字数を確保する。
- **数値を大きく表示する場合**も `font-size: clamp(1.5rem, 5vw, 2.5rem)` 等で可変にし、はみ出しを防ぐ。

### パディング・マージン
- セクションやカードの左右パディングは `padding: 0 clamp(12px, 4vw, 32px);` のように**スマホで狭くなる**設計にする。
- コンテンツ領域の `max-width` は `min(100%, 800px)` 等にし、`margin: 0 auto` で中央寄せする。

## 最終仕上げに加える確認（日本語）

上記「最終仕上げフェーズ」のチェックに加え、次も確認する。

- **です・ます**が HTML 内の表示テキスト全体で統一されているか
- 禁止に近い定型句や抽象語の**連打**がないか
- **主要セクションごと**に、文字起こし由来の具体が 1 つ以上あるか
- **数値のカンマ区切り**が正しい 3 桁区切りになっているか（右から数えて確認）
- **スマホ幅（320px）でテキスト・カード・見出しがはみ出していないか**（`box-sizing: border-box` と `max-width: 100%` を確認）
"""


def _extract_html(raw: str) -> str:
    """応答から単一 HTML を取り出す（フェンス付きにも対応）。"""
    text = (raw or "").strip()
    if not text:
        return ""

    m = re.search(
        r"```(?:html|HTML)?\s*\n([\s\S]*?)```",
        text,
    )
    if m:
        return m.group(1).strip()

    low = text.lower()
    if "<!doctype" in low or text.lstrip().lower().startswith("<html"):
        return text

    # 前置きの説明の後に HTML がある場合
    idx = text.lower().find("<!doctype")
    if idx == -1:
        idx = text.lower().find("<html")
    if idx >= 0:
        return text[idx:].strip()

    return text


def main() -> int:
    p = argparse.ArgumentParser(description="会議IDで図解HTMLを生成（指定systemプロンプトそのまま）")
    p.add_argument("meeting_id", help="tl;dv 会議 ID")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="出力パス（省略時 artifacts/meeting_<id>_infographic_raw_prompt.html）",
    )
    p.add_argument(
        "--local-only",
        action="store_true",
        help="暗号化・GCS・Slack を行わず、平文HTMLのみ保存する",
    )
    args = p.parse_args()
    mid = (args.meeting_id or "").strip()
    if not mid:
        print("meeting_id が空です。", file=sys.stderr)
        return 2

    from anthropic import Anthropic

    from app.config import settings
    from app.services.tldv_client import fetch_meeting_context

    print("tl;dv 取得中…", flush=True)
    try:
        meeting_info, transcript = fetch_meeting_context(mid)
    except Exception as e:
        print(f"tl;dv 失敗: {e}", file=sys.stderr)
        return 1

    if not (transcript or "").strip():
        print("文字起こしが空です。", file=sys.stderr)
        return 1

    parts = meeting_info.get("participants") or []
    parts_line = ", ".join(str(x) for x in parts if x) if isinstance(parts, list) else ""

    user_body = f"""以下が「指定する概念・言葉・文章」の一次情報です。会議で扱われた論点・仕組み・決定・課題を、プロンプトの指示どおりに図解してください。
（会議の「技術」とは、ビジネス上の施策・制作フロー・市場戦略など、文字起こしに現れる仕組みや判断を指します。文字起こしにない事実は書かないでください。）

## 会議情報
- 会議名: {meeting_info.get("name")}
- 日時: {meeting_info.get("happened_at")}
- 参加者: {parts_line or "不明"}

## 文字起こし
{transcript}

---

【出力形式（このメッセージのみの追加指示）】
- 最終回答は **<!DOCTYPE html> で始まり </html> で終わる単一の HTML ソースのみ** にしてください。
- マークダウンのコードフェンスで囲んでも構いませんが、それ以外の前置き・後書き・思考の説明は出力しないでください。
- インタラクション（スクロール連動・ホバー等）はインライン CSS / 必要なら同一ファイル内の <script> で完結させてください。外部画像は使わず、SVG や CSS で表現してください（CDN のフォント・Mermaid 等の読み込みは可）。
- **情報ソース**は会議名のテキスト1行のみ（**tl;dv や録画の URL・リンクは書かない**）。プロンプト原文にリンク必須とあっても、この指示を優先する。フッタは `<div class="sources">` で包むと後処理と相性がよい（`info-source` でも可）。
- **タスク一覧は HTML に含めない**（後処理で別途差し込む）。会議の ToDo 列挙セクションは作らないでよい。

【日本語（このメッセージの追加指示・system の「日本語スタイル」と併せて従うこと）】
- 見出し・本文・キャプション・箇条書きは**です・ますで統一**。クライアントにそのまま見せてよいトーンにする。
- 「〜することが重要です」「仕組みとなっています」「本質的に」「最適化」「相乗効果」などの**抽象語・AI っぽい定型**を連打しない。代わりに会議の**具体**（誰・何・いつ）を書く。
- **各主要セクション**（導入を含む）に、文字起こしに基づく**具体例を 1 つ以上**入れる（固有名・日付・数値・手順の一歩など）。
- 文字起こしにない決定や成果は書かない。未確定は未確定と明示する。
"""

    print("Claude 呼び出し中（長文 HTML のため max_tokens 大）…", flush=True)
    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16_384,
        system=INFOGRAPHIC_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_body}],
    )

    block = message.content[0]
    raw_text = block.text if hasattr(block, "text") else str(block)
    html_out = _extract_html(raw_text)

    if not html_out.strip() or "<html" not in html_out.lower():
        dump = _ROOT / "artifacts" / f"meeting_{mid}_infographic_claude_raw.txt"
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(raw_text, encoding="utf-8")
        print(f"HTML を検出できませんでした。生テキストを保存: {dump}", file=sys.stderr)
        return 1

    print("要約からタスク一覧を取得して HTML に差し込み中…", flush=True)
    from app.services.claude_processor import summarize_and_extract_tasks

    try:
        sum_result = summarize_and_extract_tasks(transcript, meeting_info)
        summary_raw = sum_result.get("raw_text") or ""
    except Exception as e:
        print(f"タスク差し込み用の要約取得に失敗（図解のみ保存）: {e}", file=sys.stderr)
        summary_raw = ""

    from app.services.infographic_html_postprocess import patch_infographic_html

    html_out = patch_infographic_html(html_out, meeting_info, summary_raw)

    safe_mid = re.sub(r"[^a-zA-Z0-9._-]+", "_", mid).strip("_")[:200] or "meeting"
    out_path = args.output
    if out_path is None:
        out_path = _ROOT / "artifacts" / f"meeting_{safe_mid}_infographic_raw_prompt.html"

    publish = (not args.local_only) and bool(
        (settings.infographic_gcs_bucket or "").strip()
    )
    password: str | None = None
    html_to_write = html_out

    if publish:
        password = secrets.token_urlsafe(24)
        from app.services.infographic_password_html import encrypt_plain_html_to_password_gate

        html_to_write = encrypt_plain_html_to_password_gate(html_out, password)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_to_write, encoding="utf-8")
    print(f"保存しました: {out_path.resolve()}", flush=True)

    if publish and password:
        pw_path = out_path.with_name(out_path.stem + ".password.txt")
        pw_path.write_text(password + "\n", encoding="utf-8")
        print(f"パスワードを保存: {pw_path.resolve()}", flush=True)

        from app.services.infographic_gcs import upload_html_public_read
        from app.services.slack_publisher import post_infographic_gcs_share_notice

        rand = secrets.token_hex(8)
        prefix = (settings.infographic_gcs_prefix or "").strip().strip("/")
        mid_part = safe_mid[:120]
        if prefix:
            object_name = f"{prefix}/{rand}_{mid_part}.html"
        else:
            object_name = f"{rand}_{mid_part}.html"

        try:
            public_url = upload_html_public_read(
                bucket_name=settings.infographic_gcs_bucket or "",
                object_name=object_name,
                html_bytes=html_to_write.encode("utf-8"),
            )
        except Exception as e:
            print(
                f"GCS アップロードに失敗しました（ローカルには暗号化HTMLとパスワードファイルを保存済み）: {e}",
                file=sys.stderr,
            )
            return 1

        channel = settings.infographic_slack_channel_id or settings.slack_channel_id
        ok = post_infographic_gcs_share_notice(
            meeting_id=mid,
            meeting_info=meeting_info,
            public_url=public_url,
            password=password,
            channel_id=channel,
        )
        print(f"公開URL: {public_url}", flush=True)
        if not ok:
            print(
                "Slack への投稿に失敗しました。URL とパスワードは上記ファイルと標準出力を確認してください。",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
