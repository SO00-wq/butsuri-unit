#!/usr/bin/env python3
"""
ブツリ単位ラボ ページ生成スクリプト

data/si_db.json（物理量・公式・SI単位のデータ）から、
次元解析で単位を理解するための静的HTMLページを dist/ に生成する。

ページの種類
- /q/<量>.html   … 物理量ページ（単位を基本単位まで分解、別の書き方、同じ次元の量）
- /f/<公式>.html … 公式ページ（両辺の単位が一致することを確かめる）
- /r/<量>--<量>.html … 関係ページ（2つの量をつなぐ公式）
- /c/<分野>.html … 分野ページ
- /guide.html, /index.html, sitemap.xml, robots.txt

数値の換算は一切扱わず、SI単位と次元だけで表す。
すべての公式は生成時に両辺の次元が一致するか自動で検証される。
"""

import json, re, shutil, html
from fractions import Fraction as Fr
from pathlib import Path
from itertools import combinations

OUT = Path("dist")
SITE_NAME = "ブツリ単位ラボ"
SITE_URL = "https://tanitani.amft00571.workers.dev"  # ★独自ドメイン取得後に変更
SITE_DESC = "知らない単位や公式を、知っている公式と単位だけで理解する。SI単位と次元解析で物理量を基本単位まで分解するサイト。"

DB = json.load(open("data/si_db.json", encoding="utf-8"))

BASE_SYMS = ["kg", "m", "s", "A", "K", "mol", "cd"]
DISPLAY_ORDER = ["kg", "m", "A", "s", "K", "mol", "cd"]  # 表示の並び（A·s のように書く）
DIM_LABELS = DB["dimension_labels"]
UNITS = {u["symbol"]: u for u in DB["units"]}
UDIMS = {s: tuple(Fr(x) for x in u["dims"]) for s, u in UNITS.items()}
CATS = {c["id"]: c for c in DB["categories"]}
QS = {q["id"]: q for q in DB["quantities"]}
FS = {f["id"]: f for f in DB["formulas"]}
ZERO = tuple(Fr(0) for _ in range(7))

# ─────────────────────────── 単位の計算 ───────────────────────────

def parse_unit(s):
    """'N m2 kg-2' → {'N':1,'m':2,'kg':-2}"""
    out = {}
    for tok in s.split():
        m = re.fullmatch(r"([^\d\-/]+)(-?\d+(?:/\d+)?)?", tok)
        if not m or m.group(1) not in UNITS:
            raise ValueError(f"unknown unit token: {tok!r} in {s!r}")
        out[m.group(1)] = out.get(m.group(1), 0) + Fr(m.group(2) or 1)
    return out

def dims_of(ud):
    d = list(ZERO)
    for sym, e in ud.items():
        for i in range(7):
            d[i] += UDIMS[sym][i] * e
    return tuple(d)

def add_ud(a, b, k=Fr(1)):
    out = dict(a)
    for s, e in b.items():
        out[s] = out.get(s, 0) + e * k
    return {s: e for s, e in out.items() if e != 0}

def scale_ud(a, k):
    return {s: e * k for s, e in a.items() if e * k != 0}

def base_ud(d):
    return {BASE_SYMS[i]: d[i] for i in range(7) if d[i] != 0}

def dimscale(d, k):
    return tuple(x * k for x in d)

def dimadd(a, b):
    return tuple(x + y for x, y in zip(a, b))

SUP = str.maketrans("0123456789-/", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻ᐟ")

def sup(e):
    if e == 1:
        return ""
    s = str(e.numerator) if e.denominator == 1 else f"{e.numerator}/{e.denominator}"
    return s.translate(SUP)

def fmt_ud(ud, mode="frac"):
    """単位の辞書を表示用文字列へ。mode='frac' は分数形、'pow' は指数形"""
    items = [(s, e) for s, e in ud.items() if e != 0 and s not in ("rad", "sr") or (s in ("rad", "sr") and e != 0)]
    items = [(s, e) for s, e in items if e != 0]
    if not items:
        return "1"
    if all(s in BASE_SYMS for s, _ in items):
        items.sort(key=lambda t: DISPLAY_ORDER.index(t[0]))
    if mode == "pow":
        return "·".join(f"{s}{sup(Fr(e))}" for s, e in items)
    num = [f"{s}{sup(Fr(e))}" for s, e in items if e > 0]
    den = [f"{s}{sup(Fr(-e))}" for s, e in items if e < 0]
    n = "·".join(num) if num else "1"
    if not den:
        return n
    d = "·".join(den)
    return f"{n}/({d})" if len(den) > 1 else f"{n}/{d}"

def fmt_dim(d):
    parts = [f"{DIM_LABELS[i]}{sup(d[i])}" for i in range(7) if d[i] != 0]
    return "[" + " ".join(parts) + "]" if parts else "[無次元]"

def fmt_base(d):
    return fmt_ud(base_ud(d))

# 量ごとの単位と次元
for q in QS.values():
    q["ud"] = parse_unit(q["unit"])
    q["dims"] = dims_of(q["ud"])
    q["unit_str"] = fmt_ud(q["ud"]) if q["ud"] else "1（無次元）"

def qunit(qid):
    return QS[qid]["unit_str"]

def is_dimless(qid):
    return QS[qid]["dims"] == ZERO

# ─────────────────────────── 公式の解析と検証 ───────────────────────────

def parse_side(s):
    out = []
    for tok in s.split():
        if "^" in tok:
            v, e = tok.split("^")
            out.append((v, Fr(e)))
        else:
            out.append((tok, Fr(1)))
    return out

for f in FS.values():
    lhs, rhs = f["equation"].split("=")
    f["lhs"], f["rhs"] = parse_side(lhs), parse_side(rhs)
    f["qof"] = {}
    f["sym"] = {}
    for tok, v in f["vars"].items():
        qid, disp = (v, tok) if isinstance(v, str) else (v[0], v[1])
        if qid not in QS:
            raise ValueError(f"{f['id']}: unknown quantity {qid}")
        f["qof"][tok], f["sym"][tok] = qid, disp
    # D: ∏ var^D[var] が無次元になる（左辺は＋、右辺は−）
    D = {}
    for v, e in f["lhs"]:
        D[v] = D.get(v, 0) + e
    for v, e in f["rhs"]:
        D[v] = D.get(v, 0) - e
    f["D"] = D
    for v in D:
        if v not in f["qof"]:
            raise ValueError(f"{f['id']}: variable {v} not declared")

    def side_dims(side):
        d = ZERO
        for v, e in side:
            d = dimadd(d, dimscale(QS[f["qof"][v]]["dims"], e))
        return d
    f["lhs_dims"], f["rhs_dims"] = side_dims(f["lhs"]), side_dims(f["rhs"])
    if f["lhs_dims"] != f["rhs_dims"]:
        raise SystemExit(f"✗ 次元が一致しない公式: {f['id']} {f['expr']}  "
                         f"左辺 {fmt_dim(f['lhs_dims'])} / 右辺 {fmt_dim(f['rhs_dims'])}")
    f["quantities"] = list(dict.fromkeys(f["qof"].values()))

def solvable_vars(f):
    """1回だけ登場する量の変数（その量について解ける）"""
    cnt = {}
    for v, q in f["qof"].items():
        cnt[q] = cnt.get(q, 0) + 1
    return [v for v, q in f["qof"].items() if cnt[q] == 1 and f["D"].get(v, 0) != 0]

def solve(f, x):
    """変数 x について解いたときの、他の変数とその指数のリスト"""
    k = f["D"][x]
    return [(v, -e / k) for v, e in f["D"].items() if v != x and e != 0]

def factors_str(f, terms):
    """[(var, exp)] → 'N·m²/C² × C × C ÷ m²' のような、手で計算するときの書き方"""
    terms = sorted(terms, key=lambda t: t[1] < 0)
    out = []
    for i, (v, e) in enumerate(terms):
        u = qunit(f["qof"][v])
        if u.startswith("1"):
            u = "1"
        a = abs(e)
        simple = re.fullmatch(r"[A-Za-zΩ]+", u) is not None
        if a == 1:
            disp = u if (e > 0 or simple) else f"({u})"
        else:
            disp = f"{u}{sup(a)}" if simple else f"({u}){sup(a)}"
        if e > 0:
            out.append(disp if i == 0 else f"× {disp}")
        else:
            out.append(f"1 ÷ {disp}" if i == 0 else f"÷ {disp}")
    return " ".join(out) if out else "1"

def combine(f, terms):
    ud = {}
    for v, e in terms:
        ud = add_ud(ud, QS[f["qof"][v]]["ud"], e)
    return ud

def expr_for(f, terms):
    """式としての右辺 '(F)·(x)' のような記号表示"""
    num, den = [], []
    for v, e in terms:
        s = f["sym"][v]
        if e > 0:
            num.append(f"{s}{sup(e)}")
        else:
            den.append(f"{s}{sup(-e)}")
    n = " ".join(num) if num else "1"
    if not den:
        return n
    return f"{n} / {' '.join(den)}" if len(den) == 1 else f"{n} / ({' '.join(den)})"

# 量の定義式チェック
for q in QS.values():
    if q["defined_by"]:
        f = FS[q["defined_by"]]
        xs = [v for v in solvable_vars(f) if f["qof"][v] == q["id"]]
        if not xs:
            raise SystemExit(f"✗ {q['id']} の定義式 {f['id']} で解けない")
        q["def_var"] = xs[0]
        # 定義式から求めた単位が登録単位と一致するか
        d = dims_of(combine(f, solve(f, xs[0])))
        if d != q["dims"]:
            raise SystemExit(f"✗ {q['id']} の単位が定義式と一致しない")

# 量 → 登場する公式
Q_FORMS = {qid: [] for qid in QS}
for f in FS.values():
    for qid in f["quantities"]:
        Q_FORMS[qid].append(f["id"])

# 同じ次元の量
SAME_DIM = {}
for q in QS.values():
    SAME_DIM.setdefault(q["dims"], []).append(q["id"])

# 関係ページの組（同じ公式に登場する、次元をもつ2つの量）
PAIRS = {}
for f in FS.values():
    qs = [q for q in f["quantities"] if not is_dimless(q)]
    for a, b in combinations(sorted(set(qs)), 2):
        PAIRS.setdefault((a, b), []).append(f["id"])

def pair_slug(a, b):
    a, b = sorted((a, b))
    return f"{a}--{b}"

# ─────────────────────────── 導出の連鎖 ───────────────────────────

def chain(qid, seen=None):
    """量 qid の単位を、定義式をたどって基本単位まで組み立てる手順"""
    if seen is None:
        seen = set()
    q = QS[qid]
    if qid in seen or not q["defined_by"]:
        return []
    seen.add(qid)
    f = FS[q["defined_by"]]
    terms = solve(f, q["def_var"])
    steps = []
    for v, _ in terms:
        steps += chain(f["qof"][v], seen)
    steps.append((qid, f["id"], terms))
    return steps

# ─────────────────────────── HTML ───────────────────────────

E = html.escape

CSS = """
:root{--bg:#f7f7f4;--fg:#1b1b1b;--accent:#1d5fd1;--accent-soft:#e3ecfb;--dim:#666b73;--border:#d7d9dc;--card:#fff;--code:#f1f2f3;--ok:#18794e;--r:6px}
@media (prefers-color-scheme:dark){:root{--bg:#111214;--fg:#e6e6e8;--accent:#7aa7f5;--accent-soft:#1b2537;--dim:#9aa0a8;--border:#33363b;--card:#1a1b1e;--code:#1f2124;--ok:#4fc38a}}
*,*::before,*::after{box-sizing:border-box;margin:0}
body{font-family:'Noto Sans JP',system-ui,sans-serif;background:var(--bg);color:var(--fg);line-height:1.8;max-width:760px;margin:0 auto;padding:1.5rem 16px 4rem}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header.site{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;flex-wrap:wrap;margin-bottom:1.25rem;font-size:.9rem}
header.site .logo{font-weight:700;color:var(--fg);font-size:1rem}
header.site nav a{margin-left:.9rem;color:var(--dim)}
nav.bc{font-size:.8rem;color:var(--dim);margin-bottom:.75rem}nav.bc a{color:var(--dim)}
h1{font-size:1.5rem;line-height:1.4;margin-bottom:.6rem}
h2{font-size:1.12rem;margin:2.2rem 0 .8rem;padding-bottom:.3rem;border-bottom:2px solid var(--accent)}
h3{font-size:1rem;margin:1.4rem 0 .5rem}
p{margin-bottom:1rem}ul,ol{margin:0 0 1rem 1.3rem}li{margin-bottom:.35rem}
.lead{color:var(--dim)}
.mono,code{font-family:'IBM Plex Mono',ui-monospace,monospace}
.hero{background:var(--accent-soft);border:2px solid var(--accent);border-radius:var(--r);padding:1.2rem 1.25rem;margin:1.2rem 0;text-align:center}
.hero .big{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:1.45rem;font-weight:600;overflow-wrap:anywhere}
.hero .sub{color:var(--dim);font-size:.85rem;margin-top:.3rem}
.step{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:.9rem 1rem;margin-bottom:.8rem}
.step .st{margin-bottom:.35rem;font-size:.95rem}.step p{margin:.2rem 0 .3rem}.step .lead{font-size:.85rem}
details.pre{margin-bottom:.9rem}details.pre summary{cursor:pointer;color:var(--dim);font-size:.9rem;margin-bottom:.6rem}
.calc{font-family:'IBM Plex Mono',ui-monospace,monospace;background:var(--code);border-left:3px solid var(--accent);padding:.6rem .9rem;margin:.5rem 0 .2rem;border-radius:0 var(--r) var(--r) 0;overflow-x:auto;white-space:nowrap;font-size:.92rem;line-height:2}
.ok{color:var(--ok);font-weight:700}
table{width:100%;border-collapse:collapse;margin-bottom:1rem;font-size:.92rem}
th,td{text-align:left;padding:.45rem .5rem;border-bottom:1px solid var(--border);vertical-align:top}
th{font-size:.8rem;color:var(--dim);font-weight:700}
td.mono{white-space:nowrap}
.tbl{overflow-x:auto}
.note{background:var(--card);border:1px dashed var(--border);border-radius:var(--r);padding:.8rem 1rem;margin:1rem 0;font-size:.92rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:.6rem;margin-bottom:1rem}
.grid a{display:block;background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:.6rem .8rem;color:var(--fg)}
.grid a:hover{border-color:var(--accent);text-decoration:none}
.grid .u{font-family:'IBM Plex Mono',ui-monospace,monospace;color:var(--accent);font-size:.9rem}
.tag{display:inline-block;font-size:.72rem;font-weight:700;color:var(--accent);background:var(--accent-soft);border-radius:3px;padding:.05rem .45rem;margin-right:.3rem}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--border);font-size:.8rem;color:var(--dim)}
"""

def page(path, title, desc, body, crumbs=()):
    bc = ""
    if crumbs:
        parts = ['<a href="/">トップ</a>'] + [f'<a href="{u}">{E(t)}</a>' if u else E(t) for t, u in crumbs]
        bc = '<nav class="bc">' + " › ".join(parts) + "</nav>"
    doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)} | {SITE_NAME}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{SITE_URL}{path}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<header class="site"><a class="logo" href="/">{SITE_NAME}</a><nav><a href="/guide.html">使い方</a><a href="/#cats">分野一覧</a></nav></header>
{bc}
{body}
<footer>{SITE_NAME} — SI単位と次元解析で物理を理解する。<br>単位はすべてSI（国際単位系）で表記しています。</footer>
</body>
</html>"""
    out = OUT / path.lstrip("/")
    if path.endswith("/"):
        out = out / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    PATHS.append(path)

PATHS = []

def qlink(qid):
    return f'<a href="/q/{qid}.html">{E(QS[qid]["name"])}</a>'

def flink(fid):
    return f'<a href="/f/{fid}.html">{E(FS[fid]["name"])}</a>'

def cat_crumb(cid):
    return (CATS[cid]["name"], f"/c/{cid}.html")

def unit_line(ud):
    """named-unit 表示 = 基本単位表示（同じなら片方だけ）"""
    a = fmt_ud(ud)
    b = fmt_base(dims_of(ud))
    return a if a == b else f"{a} = {b}"

def norm(t):
    return re.sub(r"\s+", "", t)

def has_coef(f):
    return bool(re.search(r"[0-9½π]", f["expr"]))

ANGLE_SYMS = ("rad", "sr")

def tidy(combined, q):
    """表示用に整える：対象の単位に rad/sr がなければ省き、対象と同じ組なら対象の並びで返す"""
    dropped = [a for a in ANGLE_SYMS if a in combined and a not in q["ud"]]
    out = {k: v for k, v in combined.items() if k not in dropped}
    if out == q["ud"]:
        out = dict(q["ud"])
    elif set(out) <= set(BASE_SYMS):
        out = {k: out[k] for k in BASE_SYMS if k in out}
    return out, dropped

def calc_block(f, x):
    """公式 f を x について解き、単位を計算する過程"""
    terms = solve(f, x)
    q = QS[f["qof"][x]]
    combined, dropped = tidy(combine(f, terms), q)
    solved = f"{f['sym'][x]} = {expr_for(f, terms)}"
    lines = []
    if norm(solved) != norm(f["expr"]):
        lines.append(E(solved) + ("　<span class=\"lead\">（係数は単位に影響しないので省略）</span>" if has_coef(f) else ""))
    lines.append(f"[{E(f['sym'][x])}] = {E(factors_str(f, terms))}")
    c = fmt_ud(combined)
    if c != factors_str(f, terms) or dropped:
        note = f"　<span class=\"lead\">（{'・'.join(dropped)} は無次元なので省く）</span>" if dropped else ""
        lines.append(f"　　= {E(c)}{note}")
    b = fmt_base(q["dims"])
    if b != c and not set(combined) <= set(BASE_SYMS):
        lines.append(f"　　= {E(b)}")
    if q["ud"] and fmt_ud(q["ud"]) not in (c, b):
        lines.append(f"　　= {E(q['unit_str'])}")
    return '<div class="calc">' + "<br>".join(lines) + "</div>"

# ─────────────────────────── 物理量ページ ───────────────────────────

def alt_expressions(qid):
    """この量の単位の別の書き方（公式ごと）"""
    q = QS[qid]
    seen = {q["unit_str"], fmt_base(q["dims"])}
    out = []
    for fid in Q_FORMS[qid]:
        f = FS[fid]
        for x in solvable_vars(f):
            if f["qof"][x] != qid:
                continue
            ud, dropped = tidy(combine(f, solve(f, x)), q)
            if dropped or ud == q["ud"] or any(e.denominator != 1 for e in ud.values()):
                continue
            s = fmt_ud(ud)
            if s in seen or s == "1":
                continue
            seen.add(s)
            out.append((s, fid, x))
    return out

BASICS = {"velocity", "acceleration", "force", "energy", "power", "area", "volume", "charge", "momentum"}

def one_line(f, x):
    """'[F] = kg × m/s² = kg·m/s² = N' のような1行の計算"""
    q = QS[f["qof"][x]]
    terms = solve(f, x)
    combined, dropped = tidy(combine(f, terms), q)
    parts = [factors_str(f, terms)]
    c = fmt_ud(combined)
    if c not in parts:
        parts.append(c)
    b = fmt_base(q["dims"])
    if b not in parts:
        parts.append(b)
    if q["ud"] and q["unit_str"] not in parts:
        parts.append(q["unit_str"])
    return f"[{f['sym'][x]}] = " + " = ".join(parts)

def step_html(st):
    sid, fid, _ = st
    sq, f = QS[sid], FS[fid]
    return ('<div class="step">'
            f'<div class="st"><b>{qlink(sid)}</b> <span class="lead">— {flink(fid)}　<span class="mono">{E(f["expr"])}</span></span></div>'
            f'<p>{E(sq.get("how", ""))}</p>'
            f'<div class="calc">{E(one_line(f, sq["def_var"]))}</div></div>')

def build_quantity(q):
    qid = q["id"]
    cat = CATS[q["category"]]
    d = q["dims"]
    u = q["unit_str"]
    base = fmt_base(d)
    named = [s for s in q["ud"] if s not in BASE_SYMS]
    uname = "・".join(UNITS[s]["name"] for s in q["ud"]) if len(q["ud"]) == 1 else ""
    utitle = f"{uname}（{u}）" if uname and u != base else u
    if d == ZERO:
        title = f"{q['name']}の単位はなぜ無次元？"
    elif u == base:
        title = f"{q['name']}の単位 {u} の意味"
    else:
        title = f"{q['name']}の単位 {utitle} を基本単位で表すと {base}"
    desc = f"{q['name']}の単位{u}を、知っている公式からSI基本単位{base}まで分解して理解する。同じ単位の別の書き方と、同じ次元をもつ量も紹介。"
    b = [f'<span class="tag">{E(cat["name"])}</span>',
         f"<h1>{E(title)}</h1>",
         f'<p class="lead">{E(q["description"])}</p>',
         '<div class="hero">',
         f'<div class="big">{E(u)}{(" = " + E(base)) if base != u and d != ZERO else ""}</div>',
         f'<div class="sub">次元 {E(fmt_dim(d))}</div></div>']

    steps = chain(qid)
    if steps:
        b.append(f"<h2>{E(q['name'])}の単位を、知っている公式から組み立てる</h2>")
        if len(steps) > 1:
            route = " → ".join(E(QS[sid]["name"]) for sid, _, _ in steps)
            b.append(f"<p>{E(u)} を基本単位までほどくには、{route} の順に単位をつないでいきます。</p>")
        basics = [st for st in steps[:-1] if st[0] in BASICS] if len(steps) >= 4 else []
        rest = [st for st in steps if st not in basics]
        if basics:
            names = "・".join(QS[sid]["name"] for sid, _, _ in basics)
            b.append(f'<details class="pre"><summary>前提：{E(names)}の単位（知っていれば飛ばしてOK）</summary>')
            b += [step_html(st) for st in basics]
            b.append("</details>")
        b += [step_html(st) for st in rest]
        if base != u:
            b.append(f'<p>まとめると、<span class="mono ok">{E(u)} = {E(base)}</span> です。</p>')
    elif d != ZERO:
        b.append("<h2>基本単位として</h2>")
        b.append(f"<p>{E(q['name'])}はSIの基本量で、その単位 <span class=\"mono\">{E(u)}</span> はこれ以上分解できません。"
                 "ほかのすべての単位は、基本単位のかけ算・わり算で表されます。</p>")

    alts = alt_expressions(qid)
    if alts:
        b.append(f"<h2>{E(u)} の別の書き方</h2>")
        b.append("<p>同じ量でも、使う公式によって単位の見え方が変わります。どれも基本単位にすると一致します。</p>")
        b.append('<div class="tbl"><table><tr><th>書き方</th><th>根拠になる公式</th></tr>')
        for s, fid, x in alts:
            b.append(f'<tr><td class="mono">{E(u)} = {E(s)}</td><td>{flink(fid)}<br><span class="mono">{E(FS[fid]["expr"])}</span></td></tr>')
        b.append("</table></div>")

    same = [x for x in SAME_DIM[d] if x != qid]
    if same:
        b.append("<h2>同じ次元をもつ量</h2>")
        b.append(f"<p>次の量は {E(q['name'])} と次元 {E(fmt_dim(d))} が同じです。単位が同じでも意味が違う量があるので、"
                 "式の検算では区別に注意しましょう。</p><ul>")
        for x in same:
            b.append(f'<li>{qlink(x)}（<span class="mono">{E(QS[x]["unit_str"])}</span>）</li>')
        b.append("</ul>")

    forms = Q_FORMS[qid]
    if forms:
        b.append(f"<h2>{E(q['name'])}が出てくる公式</h2><ul>")
        for fid in forms:
            b.append(f'<li>{flink(fid)}：<span class="mono">{E(FS[fid]["expr"])}</span></li>')
        b.append("</ul>")

    rel = sorted({(a if a != qid else bb) for (a, bb) in PAIRS if qid in (a, bb)}, key=lambda x: QS[x]["name"])
    if rel:
        b.append(f"<h2>{E(q['name'])}とほかの量の関係</h2><div class=\"grid\">")
        for o in rel:
            b.append(f'<a href="/r/{pair_slug(qid, o)}.html">{E(q["name"])}と{E(QS[o]["name"])}'
                     f'<div class="u">{E(u)} と {E(QS[o]["unit_str"])}</div></a>')
        b.append("</div>")

    page(f"/q/{qid}.html", title, desc, "\n".join(b), [cat_crumb(q["category"]), (q["name"], None)])

# ─────────────────────────── 公式ページ ───────────────────────────

def build_formula(f):
    cat = CATS[f["category"]]
    title = f"{f['name']} {f['expr']} を次元解析で確かめる"
    desc = f"{f['name']}（{f['expr']}）の両辺の単位がSI基本単位で一致することを確かめ、式に出てくる量の単位どうしの関係を読み取る。"
    b = [f'<span class="tag">{E(cat["name"])}</span>', f"<h1>{E(f['name'])}</h1>",
         f'<div class="hero"><div class="big">{E(f["expr"])}</div></div>']

    b.append("<h2>出てくる記号と単位</h2>")
    b.append('<div class="tbl"><table><tr><th>記号</th><th>量</th><th>SI単位</th><th>基本単位</th></tr>')
    for v in dict.fromkeys(f["qof"]):
        qid = f["qof"][v]
        b.append(f'<tr><td class="mono">{E(f["sym"][v])}</td><td>{qlink(qid)}</td>'
                 f'<td class="mono">{E(qunit(qid))}</td><td class="mono">{E(fmt_base(QS[qid]["dims"]))}</td></tr>')
    b.append("</table></div>")

    b.append("<h2>両辺の単位が一致するか確かめる</h2>")
    for label, side, dd in (("左辺", f["lhs"], f["lhs_dims"]), ("右辺", f["rhs"], f["rhs_dims"])):
        cs = fmt_ud(combine(f, side))
        fs = factors_str(f, side)
        lines = [f"{label}： {E(expr_for(f, side))}", f"　→ {E(fs)}"]
        if cs != fs:
            lines.append(f"　= {E(cs)}")
        if fmt_base(dd) != cs:
            lines.append(f"　= {E(fmt_base(dd))}")
        b.append('<div class="calc">' + "<br>".join(lines) + "</div>")
    if f["lhs_dims"] == ZERO:
        b.append('<p class="ok">両辺とも単位がすべて打ち消しあい、無次元で一致します。</p>')
    else:
        b.append(f'<p><span class="ok">両辺とも {E(fmt_base(f["lhs_dims"]))} で一致</span>します。'
                 "単位が合わない式は、どこかが間違っているサインです。</p>")
    if f.get("note"):
        b.append(f'<div class="note">💡 {E(f["note"])}</div>')

    sv = solvable_vars(f)
    if sv:
        b.append("<h2>この公式から読み取れる単位の関係</h2>")
        b.append("<p>公式をある量について解くと、その量の単位をほかの量の単位で表せます。"
                 "知らない量が出てきたときは、知っている量について解き直して単位を組み立てるのが近道です。</p>")
        for x in sv:
            qid = f["qof"][x]
            b.append(f'<h3>{qlink(qid)}について解く</h3>')
            b.append(calc_block(f, x))

    same_cat = [x for x in FS if FS[x]["category"] == f["category"] and x != f["id"]][:12]
    b.append(f"<h2>{E(cat['name'])}のほかの公式</h2><ul>")
    for x in same_cat:
        b.append(f'<li>{flink(x)}：<span class="mono">{E(FS[x]["expr"])}</span></li>')
    b.append("</ul>")
    page(f"/f/{f['id']}.html", title, desc, "\n".join(b), [cat_crumb(f["category"]), (f["name"], None)])

# ─────────────────────────── 関係ページ ───────────────────────────

def build_pair(a, bq, fids):
    A, B = QS[a], QS[bq]
    title = f"{A['name']}と{B['name']}の関係｜{A['unit_str']} と {B['unit_str']} をつなぐ公式"
    desc = f"{A['name']}（{A['unit_str']}）と{B['name']}（{B['unit_str']}）を結ぶ公式と、単位どうしの関係を次元解析で整理。"
    b = [f"<h1>{E(A['name'])}と{E(B['name'])}の関係</h1>",
         f'<div class="hero"><div class="big">{E(A["unit_str"])}　と　{E(B["unit_str"])}</div>'
         f'<div class="sub">{E(fmt_dim(A["dims"]))}　と　{E(fmt_dim(B["dims"]))}</div></div>']

    ratio = dimadd(A["dims"], dimscale(B["dims"], -1))
    b.append("<h2>単位の比から見る</h2>")
    r = fmt_base(ratio) if ratio != ZERO else "1（無次元）"
    b.append(f'<div class="calc">[{E(A["name"])}] ÷ [{E(B["name"])}] = ({E(fmt_base(A["dims"]))}) ÷ ({E(fmt_base(B["dims"]))}) = {E(r)}</div>')
    match = [x for x in SAME_DIM.get(ratio, []) if x not in (a, bq)]
    inv = [x for x in SAME_DIM.get(dimscale(ratio, -1), []) if x not in (a, bq)]
    if ratio == ZERO:
        b.append(f"<p>{E(A['name'])}と{E(B['name'])}は同じ次元をもちます。</p>")
    elif match:
        b.append(f"<p>つまり {E(A['name'])} は「{E(B['name'])} × " + "・".join(qlink(x) for x in match[:3])
                 + "」と同じ単位をもちます。</p>")
    elif inv:
        b.append(f"<p>つまり {E(A['name'])} は「{E(B['name'])} ÷ " + "・".join(qlink(x) for x in inv[:3])
                 + "」と同じ単位をもちます。</p>")

    b.append("<h2>2つの量を結ぶ公式</h2>")
    for fid in fids:
        f = FS[fid]
        b.append(f'<div class="step"><b>{flink(fid)}</b>：<span class="mono">{E(f["expr"])}</span>')
        for qid in (a, bq):
            xs = [v for v in solvable_vars(f) if f["qof"][v] == qid]
            if xs:
                b.append(calc_block(f, xs[0]))
        b.append("</div>")

    b.append("<h2>それぞれの量のページ</h2><ul>")
    for qid in (a, bq):
        b.append(f'<li>{qlink(qid)}（<span class="mono">{E(QS[qid]["unit_str"])} = {E(fmt_base(QS[qid]["dims"]))}</span>）</li>')
    b.append("</ul>")
    page(f"/r/{pair_slug(a, bq)}.html", title, desc, "\n".join(b),
         [(A["name"], f"/q/{a}.html"), (f"{B['name']}との関係", None)])

# ─────────────────────────── 分野・トップ・使い方 ───────────────────────────

def qcard(qid):
    q = QS[qid]
    return f'<a href="/q/{qid}.html">{E(q["name"])}<div class="u">{E(q["unit_str"])}</div></a>'

def build_category(c):
    qs = [q for q in QS if QS[q]["category"] == c["id"]]
    fs = [f for f in FS if FS[f]["category"] == c["id"]]
    b = [f"<h1>{E(c['name'])}の単位と公式</h1>", f'<p class="lead">{E(c["description"])}</p>']
    if qs:
        b.append("<h2>物理量</h2><div class=\"grid\">" + "".join(qcard(x) for x in qs) + "</div>")
    if fs:
        b.append("<h2>公式</h2><ul>" + "".join(
            f'<li>{flink(x)}：<span class="mono">{E(FS[x]["expr"])}</span></li>' for x in fs) + "</ul>")
    page(f"/c/{c['id']}.html", f"{c['name']}の単位と公式一覧",
         f"{c['name']}に出てくる物理量の単位と公式を、SI単位と次元解析で整理した一覧。", "\n".join(b),
         [(c["name"], None)])

def build_index():
    b = ["<h1>知らない単位も、知っている公式から組み立てればわかる</h1>",
         f'<p class="lead">{E(SITE_DESC)}</p>',
         '<div class="hero"><div class="big">J = N·m = kg·m²/s²</div>'
         '<div class="sub">F = ma と W = Fx を知っていれば、ジュールの中身は自分で導ける</div></div>',
         "<h2>このサイトの考え方</h2>",
         "<p>物理の単位は、たった7つの基本単位のかけ算・わり算でできています。"
         "初めて見る単位や公式も、知っている公式を使って基本単位まで分解すれば、その正体がわかります。"
         "このサイトでは数値の換算は扱わず、<b>SI単位と次元だけ</b>で説明します。</p>",
         '<p><a href="/guide.html">→ 次元解析の使い方を読む</a></p>',
         "<h2>7つの基本単位</h2><div class=\"grid\">"
         + "".join(qcard(x) for x in ["length", "mass", "time", "current", "temperature", "amount", "luminous_intensity"])
         + "</div>",
         "<h2>まずはここから</h2><div class=\"grid\">"
         + "".join(qcard(x) for x in ["force", "energy", "power", "voltage", "resistance", "magnetic_flux_density", "planck", "gas_constant"])
         + "</div>",
         '<h2 id="cats">分野から探す</h2>']
    for c in CATS.values():
        n = sum(1 for q in QS.values() if q["category"] == c["id"])
        m = sum(1 for f in FS.values() if f["category"] == c["id"])
        b.append(f'<h3><a href="/c/{c["id"]}.html">{E(c["name"])}</a> <span class="lead" style="font-size:.85rem;font-weight:400">量 {n}・公式 {m}</span></h3>')
        b.append(f'<p class="lead">{E(c["description"])}</p>')
    page("/", "SI単位と次元解析で物理を理解する", SITE_DESC, "\n".join(b))

def build_guide():
    body = """
<h1>次元解析の使い方：知らない単位を基本単位に分解する</h1>
<p class="lead">次元解析は、式に出てくる量の「単位」だけに注目して、式の意味を読み取ったり、間違いを見つけたりする方法です。</p>

<h2>1. すべての単位は7つの基本単位からできている</h2>
<p>SI（国際単位系）では、長さ m・質量 kg・時間 s・電流 A・温度 K・物質量 mol・光度 cd の7つが基本単位です。
N（ニュートン）や V（ボルト）のような単位は、基本単位の組み合わせに名前をつけたものにすぎません。</p>
<div class="calc">N = kg·m/s²　　J = kg·m²/s²　　V = kg·m²/(s³·A)</div>

<h2>2. 知っている公式を使って分解する</h2>
<p>知らない単位が出てきたら、その量が出てくる「知っている公式」を探し、その量について解きます。
たとえば電圧 V を知らなくても、電力の式 P = IV を知っていれば、</p>
<div class="calc">V = P / I　→　[V] = W / A = (kg·m²/s³) / A = kg·m²/(s³·A)</div>
<p>と分解できます。W（ワット）がわからなければ、さらに P = W/t、W = Fx、F = ma とたどればよいのです。</p>

<h2>3. 両辺の単位が一致するか確かめる</h2>
<p>正しい公式では、左辺と右辺の単位が必ず一致します。たとえば運動エネルギー K = ½mv² では、</p>
<div class="calc">左辺 [K] = J = kg·m²/s²<br>右辺 [m v²] = kg × (m/s)² = kg·m²/s²　<span class="ok">一致</span></div>
<p>½ のような係数は単なる数で単位をもたないので、次元解析では無視してかまいません。
単位が合わなければ、式のどこかが間違っています。</p>

<h2>4. 単位が同じでも、同じ量とは限らない</h2>
<p>トルク（N·m）とエネルギー（J）は基本単位にするとどちらも kg·m²/s² です。
ヘルツ（Hz）とベクレル（Bq）もどちらも s⁻¹ です。次元解析は式の検算に強力ですが、
次元が同じだからといって同じ意味の量とは限らない点には注意しましょう。</p>

<h2>5. 単位から公式を推測する</h2>
<p>単位の組み合わせから、式の形を推測することもできます。たとえば単振り子の周期 T が、ひもの長さ l [m] と
重力加速度 g [m/s²] だけで決まるとすると、秒 s をつくる組み合わせは</p>
<div class="calc">√(l / g)　→　√(m ÷ (m/s²)) = √(s²) = s</div>
<p>しかありません。実際の公式 T = 2π√(l/g) と、係数 2π を除いて一致します。</p>
<p><a href="/">→ トップに戻って物理量を探す</a></p>
"""
    page("/guide.html", "次元解析の使い方", "次元解析の基本：7つの基本単位、公式を使った単位の分解、両辺の単位の検算、単位から公式を推測する方法を解説。",
         body, [("次元解析の使い方", None)])

def build_sitemap():
    urls = "\n".join(f"  <url><loc>{SITE_URL}{p}</loc></url>" for p in PATHS)
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n',
        encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")

def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    print(f"✓ 全{len(FS)}公式の両辺の次元が一致することを確認")
    build_index()
    build_guide()
    for c in CATS.values():
        build_category(c)
    for q in QS.values():
        build_quantity(q)
    for f in FS.values():
        build_formula(f)
    for (a, bq), fids in PAIRS.items():
        build_pair(a, bq, fids)
    build_sitemap()
    print(f"✓ 物理量 {len(QS)}・公式 {len(FS)}・関係 {len(PAIRS)}・分野 {len(CATS)} ページ")
    print(f"合計: {len(PATHS)} ページ生成完了 → {OUT}/")

if __name__ == "__main__":
    main()
