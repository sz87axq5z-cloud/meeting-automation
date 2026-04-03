このフォルダに NotoSansCJKjp-Regular.otf（または旧名 NotoSansJP-Regular.otf）を置くと、
Vercel 等でもネットワーク取得なしで日本語 PNG を描画できます。

取得例（ファイルサイズ大・約16MB）:
  curl -fsSL -o fonts/NotoSansCJKjp-Regular.otf \
    https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf

図解の見出しを太字にしたい場合は、同じく OTF の Bold を fonts/ に置くか、環境変数 SUMMARY_FONT_BOLD_PATH で指定してください。
（未設定でも macOS ではヒラギノ W6 を自動で試します。）

ライセンス: SIL Open Font License（noto-cjk リポジトリの OFL.txt を参照）
