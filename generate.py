#!/usr/bin/env python3
"""
物理単位サイト ページ生成スクリプト
単位データベースからすべてのHTMLページを自動生成する
"""

import json, os, math, itertools
from pathlib import Path

OUT = Path("dist")
SITE_NAME = "ブツリ単位ラボ"
SITE_URL  = "https://butsuri-unit.pages.dev"  # ★独自ドメイン取得後に変更
SITE_DESC = "物理単位の変換＆次元解析。なぜその変換式が成り立つのかを、SI基本単位への分解で理解する。"

# ─── Load DB ───
with open("units_db.json", encoding="utf-8") as f:
    DB = json.load(f)

CATEGORIES = DB["categories"]

# Flat unit lookup
ALL_UNITS = {}
UNIT_TO_CAT = {}
for cat in CATEGORIES:
    for u in cat["units"]:
        ALL_UNITS[u["id"]] = u
        UNIT_TO_CAT[u["id"]] = cat

# ─── HTML helpers ───

def head(title, description, canonical_path, extra_css=""):
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | {SITE_NAME}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{SITE_URL}{canonical_path}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #f7f7f5;
  --fg: #1a1a1a;
  --accent: #2563eb;
  --accent-light: #dbeafe;
  --dim: #6b7280;
  --border: #d1d5db;
  --card-bg: #ffffff;
  --code-bg: #f3f4f6;
  --radius: 6px;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #111113;
    --fg: #e4e4e7;
    --accent: #60a5fa;
    --accent-light: #1e293b;
    --dim: #9ca3af;
    --border: #374151;
    --card-bg: #1c1c1f;
    --code-bg: #1e1e22;
  }}
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; }}
body {{
  font-family: 'Noto Sans JP', sans-serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.75;
  max-width: 720px;
  margin: 0 auto;
  padding: 2rem 1.25rem 4rem;
}}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: .5rem; line-height: 1.35; }}
h2 {{ font-size: 1.15rem; font-weight: 700; margin: 2rem 0 .75rem; padding-bottom: .35rem; border-bottom: 2px solid var(--accent); }}
h3 {{ font-size: 1rem; font-weight: 700; margin: 1.5rem 0 .5rem; }}
p {{ margin-bottom: 1rem; }}
code, .mono {{ font-family: 'IBM Plex Mono', monospace; }}
.dim {{ color: var(--dim); font-size: .85rem; }}
.card {{
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
  margin-bottom: 1.25rem;
}}
.converter {{
  background: var(--accent-light);
  border: 2px solid var(--accent);
  border-radius: var(--radius);
  padding: 1.5rem;
  margin: 1.5rem 0;
  text-align: center;
}}
.converter input {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 1.3rem;
  width: 140px;
  padding: .4rem .6rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card-bg);
  color: var(--fg);
  text-align: right;
}}
.converter .symbol {{
  font-family: 'IBM Plex Mono', monospace;
  font-weight: 600;
  margin: 0 .35rem;
}}
.converter .arrow {{ font-size: 1.4rem; margin: 0 .75rem; }}
.dim-box {{
  background: var(--code-bg);
  border-left: 3px solid var(--accent);
  padding: 1rem 1.25rem;
  margin: 1rem 0;
  border-radius: 0 var(--radius) var(--radius) 0;
  font-family: 'IBM Plex Mono', monospace;
  font-size: .95rem;
  line-height: 1.9;
}}
nav.breadcrumb {{
  font-size: .82rem;
  color: var(--dim);
  margin-bottom: 1rem;
}}
nav.breadcrumb a {{ color: var(--dim); }}
.tag {{
  display: inline-block;
  background: var(--accent-light);
  color: var(--accent);
  font-size: .75rem;
  font-weight: 700;
  padding: .15rem .5rem;
  border-radius: 3px;
  margin-right: .35rem;
}}
footer {{
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border);
  font-size: .8rem;
  color: var(--dim);
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: .75rem;
}}
.grid a {{
  display: block;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: .75rem 1rem;
  transition: border-color .15s;
}}
.grid a:hover {{
  border-color: var(--accent);
  text-decoration: none;
}}
{extra_css}
</style>
</head>
<body>
"""

def footer_html():
    return f"""
<footer>
  <p><a href="/">トップ</a>に戻る</p>
  <p>{SITE_NAME} — 物理単位の変換と次元解析による理解</p>
</footer>
</body>
</html>"""


# ─── Conversion pages ───

def conversion_factor(u_from, u_to):
    """Get conversion factor: 1 u_from = ? u_to"""
    f = u_from["to_si"]
    t = u_to["to_si"]
    if isinstance(f, str) or isinstance(t, str):
        return None  # temperature special
    return f / t

def format_number(n):
    if n == 0:
        return "0"
    if abs(n) >= 1e6 or abs(n) < 1e-3:
        return f"{n:.6e}"
    if n == int(n):
        return str(int(n))
    # trim trailing zeros
    s = f"{n:.10f}".rstrip('0').rstrip('.')
    return s

def make_conversion_page(u_from, u_to, cat):
    slug = f"{u_from['id']}-to-{u_to['id']}"
    path = f"/convert/{slug}.html"
    
    factor = conversion_factor(u_from, u_to)
    
    title = f"{u_from['symbol']}から{u_to['symbol']}への変換"
    desc = f"{u_from['name']}（{u_from['symbol']}）を{u_to['name']}（{u_to['symbol']}）に変換。次元解析による物理的意味の解説付き。"
    
    # Temperature special handling
    is_temp = (cat["id"] == "temperature")
    
    factor_str = ""
    if factor is not None:
        factor_str = format_number(factor)
    
    # Build dimensional analysis explanation
    dim_explanation = build_dim_explanation(u_from, u_to, cat, factor)
    
    html = head(title, desc, path)
    
    html += f"""
<nav class="breadcrumb">
  <a href="/">トップ</a> &gt; <a href="/category/{cat['id']}.html">{cat['name']}</a> &gt; {u_from['symbol']} → {u_to['symbol']}
</nav>

<h1>{u_from['name']}（{u_from['symbol']}）から<br>{u_to['name']}（{u_to['symbol']}）への変換</h1>
<p class="dim">{cat['name']}の単位変換 — 次元: {cat['dimension_formula']}</p>
"""

    # Converter widget
    if not is_temp and factor is not None:
        html += f"""
<div class="converter" id="conv">
  <input type="number" id="valA" value="1" oninput="calc()">
  <span class="symbol">{u_from['symbol']}</span>
  <span class="arrow">＝</span>
  <input type="number" id="valB" value="{factor_str}" readonly>
  <span class="symbol">{u_to['symbol']}</span>
</div>
<script>
function calc() {{
  var v = parseFloat(document.getElementById('valA').value);
  if (isNaN(v)) {{ document.getElementById('valB').value = ''; return; }}
  var result = v * {factor};
  if (Math.abs(result) >= 1e6 || (Math.abs(result) < 1e-3 && result !== 0))
    document.getElementById('valB').value = result.toExponential(6);
  else
    document.getElementById('valB').value = parseFloat(result.toPrecision(10));
}}
</script>
"""
    elif is_temp:
        html += build_temp_converter(u_from, u_to)
    
    # Core result box
    if factor is not None:
        html += f"""
<div class="card">
  <h3>変換結果</h3>
  <p class="mono" style="font-size:1.15rem;">1 {u_from['symbol']} = {factor_str} {u_to['symbol']}</p>
</div>
"""
    
    # Dimensional analysis section
    html += f"""
<h2>なぜこの変換が成り立つのか — 次元解析</h2>
{dim_explanation}
"""
    
    # Physical meaning section
    html += f"""
<h2>{u_from['name']}とは</h2>
<div class="card">
  <p><strong>SI分解:</strong> <code>{u_from['si_decomposition']}</code></p>
  <p>{u_from['physical_meaning']}</p>
</div>

<h2>{u_to['name']}とは</h2>
<div class="card">
  <p><strong>SI分解:</strong> <code>{u_to['si_decomposition']}</code></p>
  <p>{u_to['physical_meaning']}</p>
</div>
"""
    
    # Reverse link
    html += f"""
<h2>逆変換</h2>
<p><a href="/convert/{u_to['id']}-to-{u_from['id']}.html">{u_to['symbol']}から{u_from['symbol']}への変換はこちら</a></p>
"""
    
    # Related conversions
    html += f"""
<h2>同じカテゴリの変換</h2>
<div class="grid">
"""
    count = 0
    for other in cat["units"]:
        if other["id"] != u_from["id"] and other["id"] != u_to["id"] and count < 8:
            html += f'  <a href="/convert/{u_from["id"]}-to-{other["id"]}.html">{u_from["symbol"]} → {other["symbol"]}</a>\n'
            count += 1
    html += "</div>\n"
    
    html += footer_html()
    
    outpath = OUT / f"convert/{slug}.html"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(html, encoding="utf-8")
    return path


def build_dim_explanation(u_from, u_to, cat, factor):
    """Build the dimensional analysis explanation that makes this site unique"""
    html = ""
    
    html += f"""<div class="dim-box">
<strong>次元式:</strong> {cat['name']}の次元 = {cat['dimension_formula']}<br><br>
<strong>{u_from['name']}のSI分解:</strong><br>
　{u_from['symbol']} = {u_from['si_decomposition']}<br><br>
<strong>{u_to['name']}のSI分解:</strong><br>
　{u_to['symbol']} = {u_to['si_decomposition']}
</div>
"""
    
    html += """<p>両方の単位をSI基本単位（kg, m, s, A, K, mol, cd）まで分解すると、
同じ次元を持つことが確認できます。変換係数は、それぞれのSI基本単位への
換算値の比から機械的に導出されます。</p>
"""
    
    if factor is not None and factor != 1:
        html += f"""<p>具体的には、{u_from['name']}の定義値をSI単位で表したものと、
{u_to['name']}の定義値をSI単位で表したものの比をとると：</p>
<div class="dim-box">
1 {u_from['symbol']} = {format_number(factor)} {u_to['symbol']}
</div>
"""
    
    return html


def build_temp_converter(u_from, u_to):
    """Temperature needs special conversion formulas"""
    fid = u_from['id']
    tid = u_to['id']
    
    formulas = {
        ('K', 'degC'):    ('v - 273.15', 'v + 273.15'),
        ('degC', 'K'):    ('v + 273.15', 'v - 273.15'),
        ('K', 'degF'):    ('(v - 273.15) * 9/5 + 32', '(v - 32) * 5/9 + 273.15'),
        ('degF', 'K'):    ('(v - 32) * 5/9 + 273.15', '(v - 273.15) * 9/5 + 32'),
        ('degC', 'degF'): ('v * 9/5 + 32', '(v - 32) * 5/9'),
        ('degF', 'degC'): ('(v - 32) * 5/9', 'v * 9/5 + 32'),
    }
    
    key = (fid, tid)
    if key in formulas:
        fwd = formulas[key][0]
    else:
        fwd = 'v'
    
    default_result = eval(fwd.replace('v', '1'))
    
    return f"""
<div class="converter" id="conv">
  <input type="number" id="valA" value="0" oninput="calc()">
  <span class="symbol">{u_from['symbol']}</span>
  <span class="arrow">＝</span>
  <input type="number" id="valB" value="" readonly>
  <span class="symbol">{u_to['symbol']}</span>
</div>
<script>
function calc() {{
  var v = parseFloat(document.getElementById('valA').value);
  if (isNaN(v)) {{ document.getElementById('valB').value = ''; return; }}
  var result = {fwd};
  document.getElementById('valB').value = parseFloat(result.toPrecision(10));
}}
calc();
</script>
"""


# ─── Category pages ───

def make_category_page(cat):
    path = f"/category/{cat['id']}.html"
    title = f"{cat['name']}の単位変換一覧"
    desc = f"{cat['name']}に関する全単位の変換ページ一覧。次元式: {cat['dimension_formula']}。"
    
    html = head(title, desc, path)
    
    html += f"""
<nav class="breadcrumb">
  <a href="/">トップ</a> &gt; {cat['name']}
</nav>

<h1>{cat['name']}の単位変換</h1>
<p>{cat['description']}</p>
<div class="dim-box">
次元式: {cat['dimension_formula']}
</div>

<h2>単位一覧</h2>
"""
    for u in cat["units"]:
        si_tag = '<span class="tag">SI</span>' if u["is_si"] else ''
        html += f"""
<div class="card">
  <h3>{u['name']}（<code>{u['symbol']}</code>）{si_tag}</h3>
  <p class="dim">SI分解: {u['si_decomposition']}</p>
  <p>{u['physical_meaning']}</p>
</div>
"""
    
    html += "<h2>全変換ページ</h2>\n<div class='grid'>\n"
    for a, b in itertools.permutations(cat["units"], 2):
        html += f'  <a href="/convert/{a["id"]}-to-{b["id"]}.html">{a["symbol"]} → {b["symbol"]}</a>\n'
    html += "</div>\n"
    
    html += footer_html()
    
    outpath = OUT / f"category/{cat['id']}.html"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(html, encoding="utf-8")
    return path


# ─── Index page ───

def make_index():
    html = head(SITE_NAME, SITE_DESC, "/")
    
    html += f"""
<h1 style="font-size:2rem; margin-bottom:.25rem;">ブツリ単位ラボ</h1>
<p style="font-size:1.05rem; color:var(--dim); margin-bottom:2rem;">
  単位を変換するだけでなく、<strong>なぜその変換が成り立つのか</strong>を次元解析で理解する。
</p>

<div class="card" style="border-color:var(--accent);">
  <h3>このサイトの特徴</h3>
  <p>一般的な単位変換サイトは「1Pa = ○○atm」と結果だけを表示します。
  このサイトは、すべての単位をSI基本単位（kg, m, s, A, K, mol, cd）まで分解し、
  変換係数がどこから来るのかを導出します。</p>
  <p>公式を丸暗記するのではなく、次元から理解すれば、忘れても自分で導き出せます。</p>
</div>
"""
    
    total_pages = 0
    for cat in CATEGORIES:
        n = len(cat["units"])
        total_pages += n * (n - 1)
    
    html += f"<p class='dim'>全{total_pages}ページの変換解説を収録</p>\n"
    
    for cat in CATEGORIES:
        html += f"""
<h2><a href="/category/{cat['id']}.html">{cat['name']}</a></h2>
<p class="dim">次元: {cat['dimension_formula']} — {cat['description']}</p>
<div class="grid">
"""
        # Show top conversions
        shown = 0
        for a, b in itertools.permutations(cat["units"], 2):
            if shown >= 6:
                break
            html += f'  <a href="/convert/{a["id"]}-to-{b["id"]}.html">{a["symbol"]} → {b["symbol"]}</a>\n'
            shown += 1
        
        remaining = len(cat["units"]) * (len(cat["units"]) - 1) - shown
        html += f'</div>\n'
        if remaining > 0:
            html += f'<p class="dim"><a href="/category/{cat["""id"""]}.html">他{remaining}件の変換を見る →</a></p>\n'
    
    html += footer_html()
    
    outpath = OUT / "index.html"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(html, encoding="utf-8")


# ─── Sitemap ───

def make_sitemap(all_paths):
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for p in all_paths:
        xml += f"  <url><loc>{SITE_URL}{p}</loc></url>\n"
    xml += "</urlset>\n"
    (OUT / "sitemap.xml").write_text(xml, encoding="utf-8")


def make_robots():
    txt = f"""User-agent: *
Allow: /

Sitemap: {SITE_URL}/sitemap.xml
"""
    (OUT / "robots.txt").write_text(txt, encoding="utf-8")


# ─── Main ───

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    
    all_paths = ["/"]
    
    # Index
    make_index()
    print("✓ index.html")
    
    # Category pages
    for cat in CATEGORIES:
        p = make_category_page(cat)
        all_paths.append(p)
    print(f"✓ {len(CATEGORIES)} category pages")
    
    # Conversion pages
    page_count = 0
    for cat in CATEGORIES:
        for a, b in itertools.permutations(cat["units"], 2):
            p = make_conversion_page(a, b, cat)
            all_paths.append(p)
            page_count += 1
    print(f"✓ {page_count} conversion pages")
    
    # Sitemap & robots
    make_sitemap(all_paths)
    make_robots()
    print(f"✓ sitemap.xml ({len(all_paths)} URLs)")
    print(f"✓ robots.txt")
    print(f"\n合計: {len(all_paths)} ページ生成完了 → {OUT}/")


if __name__ == "__main__":
    main()
