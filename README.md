# タンブツ〜単位で物理を考える〜

物理の計算で出した答えが正しいかを、答えの単位（次元解析）で確かめるための学習サイト（静的サイト自動生成）。
きっかけは予備校の先生の教え「取れる問題を間違えることが、一番ダメージが大きい」。

## 構成
- `data/si_db.json` … SI単位・物理量・公式のデータ（量を足すときはここを編集）
- `data/mistakes.json` … よくあるミスの例（誤答と正答。生成時に単位で見抜けるかを自動検証）
- `generate.py` … HTML生成スクリプト（Python標準ライブラリのみ）。生成時に全公式の両辺の次元と、全「言葉の式」の単位が一致するか自動検証する
- `dist/` … 生成物（公開されるHTML。データを変えたら再生成してコミット）
- `wrangler.jsonc` … Cloudflare Workers の公開設定

## ビルド
```
python generate.py
```

## 公開（Cloudflare Workers）
`main` にプッシュすると `dist/` が自動で公開される。

## アイコン・共有画像・お問い合わせ

- `make_images.py` で `static/`（favicon、ホーム画面用アイコン、SNS共有画像 ogp.png）を作る。`generate.py` が `static/` を `dist/` にそのままコピーする
- お問い合わせページは、`generate.py` の `CONTACT_FORM_URL` に Google フォームの URL を入れると自動で作られ、メニュー・フッター・プライバシーポリシーからリンクされる
- `src/index.js`：tanbutsu.com 以外のホストからの 301 転送、安全のためのヘッダー、キャッシュ設定。存在しないページは `dist/404.html` を返す

## 代入で検算（/checks/）

- `data/make_checks.py` に定番問題を書き、`python data/make_checks.py` で `data/checks.json` を作る
- ビルド時に自動で確かめること：答えと誤答の単位が求めたい量と一致する、(m₁+m₂) などの和の中の項の単位がそろう、指数の肩が無次元、
  各代入ケースで答えが期待どおりの値になる（0 や ∞ は数値で近似）、誤答が指定したケースで見抜ける
