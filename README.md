# ブツリ単位ラボ

知らない単位や公式を、知っている公式とSI単位だけで理解するための次元解析サイト（静的サイト自動生成）。数値の換算は扱わない。

## 構成
- `data/si_db.json` … SI単位・物理量・公式のデータ（量を足すときはここを編集）
- `generate.py` … HTML生成スクリプト（Python標準ライブラリのみ）。生成時に全公式の両辺の次元と、全「言葉の式」の単位が一致するか自動検証する
- `dist/` … 生成物（公開されるHTML。データを変えたら再生成してコミット）
- `wrangler.jsonc` … Cloudflare Workers の公開設定

## ビルド
```
python generate.py
```

## 公開（Cloudflare Workers）
`main` にプッシュすると `dist/` が自動で公開される。
