# ブツリ単位ラボ

物理単位の変換＋次元解析による解説サイト（静的サイト自動生成）。

## 構成
- `units_db.json` … 単位データベース
- `generate.py` … HTML生成スクリプト（Python標準ライブラリのみ）
- `dist/` … 生成物（Gitには含めない）

## ビルド
```
python generate.py
```

## 公開（Cloudflare Pages）
- ビルドコマンド: `python generate.py`
- 出力ディレクトリ: `dist`
