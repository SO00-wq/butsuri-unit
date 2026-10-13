# ブツリ単位ラボ

物理単位の変換＋次元解析による解説サイト（静的サイト自動生成）。

## 構成
- `units_db.json` … 単位データベース
- `generate.py` … HTML生成スクリプト（Python標準ライブラリのみ）
- `dist/` … 生成物（公開されるHTML。データを変えたら再生成してコミット）
- `wrangler.jsonc` … Cloudflare Workers の公開設定

## ビルド
```
python generate.py
```

## 公開（Cloudflare Workers）
`main` にプッシュすると `dist/` が自動で公開される。
