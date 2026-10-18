"""
サイトのアイコンと SNS 共有用の画像を static/ に作る（一度作れば十分。作り直すときだけ実行）

  python make_images.py

作るもの
  static/favicon.ico                 ブラウザのタブのアイコン
  static/assets/icon.svg             同じアイコンの SVG 版
  static/assets/apple-touch-icon.png スマホのホーム画面に追加したときのアイコン
  static/assets/ogp.png              X や LINE でリンクを貼ったときに出る画像（1200×630）

generate.py は static/ の中身をそのまま dist/ にコピーする。
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent / "static"
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_R = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
ACCENT = (29, 95, 209)
BG = (247, 247, 244)
FG = (27, 27, 27)
DIM = (102, 107, 115)

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#1d5fd1"/>
<text x="32" y="45" text-anchor="middle" font-family="'Noto Sans JP','Hiragino Sans','Yu Gothic',sans-serif" font-weight="700" font-size="38" fill="#fff">単</text>
</svg>
"""


def font(size, bold=True):
    return ImageFont.truetype(FONT if bold else FONT_R, size, index=0)


def mark(size, radius_ratio=0.22):
    """青い角丸の四角に白い「単」"""
    s = size * 4  # 大きく描いて縮小（ふちをなめらかに）
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * radius_ratio), fill=ACCENT)
    f = font(int(s * 0.62))
    d.text((s / 2, s / 2), "単", font=f, fill="white", anchor="mm")
    return im.resize((size, size), Image.LANCZOS)


def center_text(d, x, y, text, f, fill):
    d.text((x, y), text, font=f, fill=fill, anchor="mm")


def ogp():
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 14), fill=ACCENT)
    m = mark(132)
    im.paste(m, (W // 2 - 66, 92), m)
    center_text(d, W / 2, 300, "タンブツ", font(104), FG)
    center_text(d, W / 2, 392, "〜単位で物理を考える〜", font(46), ACCENT)
    center_text(d, W / 2, 488, "答えの単位で検算して、取れる問題を落とさない。", font(34, bold=False), DIM)
    center_text(d, W / 2, 566, "tanbutsu.com", font(30), DIM)
    return im


def main():
    (ROOT / "assets").mkdir(parents=True, exist_ok=True)
    (ROOT / "assets" / "icon.svg").write_text(SVG, encoding="utf-8")
    mark(180, 0.0).convert("RGB").save(ROOT / "assets" / "apple-touch-icon.png")  # iPhone が角を丸めるので四角のまま
    mark(64).save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    ogp().save(ROOT / "assets" / "ogp.png", optimize=True)
    for p in sorted(ROOT.rglob("*")):
        if p.is_file():
            print("作成:", p.relative_to(ROOT.parent), p.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
