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
SITE_URL = "https://tanitani.butsuri-lab.workers.dev"  # ★独自ドメイン取得後に変更
ASSET_VER = "3"  # CSS/JS を変えたら上げる（ブラウザのキャッシュ対策）
UPDATED = "2026-10-17"  # 最終更新日（内容を更新したら変える）
GOOGLE_VERIFICATION = "kVE91IWkP86K1E_JpBQDklXXu5gz86ZOA64xcgtDUwc"  # Search Console 所有権確認
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
        simple = re.fullmatch(r"[A-Za-zΩ⁰¹²³⁴⁵⁶⁷⁸⁹]+", u) is not None
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

# 言葉の式のチェック：言葉を単位に置き換えた結果が、その量の単位と一致するか
for q in QS.values():
    if q.get("words"):
        d = ZERO
        for _, wq, e in q["words"]:
            if wq not in QS:
                raise SystemExit(f"✗ {q['id']} の言葉の式に未知の量 {wq}")
            d = dimadd(d, dimscale(QS[wq]["dims"], Fr(e)))
        if d != q["dims"]:
            raise SystemExit(f"✗ {q['id']} の言葉の式の単位が一致しない: {fmt_dim(d)} ≠ {fmt_dim(q['dims'])}")

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
:root{--bg:#f7f7f4;--fg:#1b1b1b;--accent:#1d5fd1;--accent-soft:#e3ecfb;--dim:#666b73;--border:#d7d9dc;--card:#fff;--code:#f1f2f3;--ok:#18794e;--r:8px;--hdr:56px;--shadow:0 6px 24px rgba(0,0,0,.12)}
@media (prefers-color-scheme:dark){:root{--bg:#111214;--fg:#e6e6e8;--accent:#7aa7f5;--accent-soft:#1b2537;--dim:#9aa0a8;--border:#33363b;--card:#1a1b1e;--code:#1f2124;--ok:#4fc38a;--shadow:0 6px 24px rgba(0,0,0,.5)}}
*,*::before,*::after{box-sizing:border-box;margin:0}
html{scroll-padding-top:calc(var(--hdr) + 12px);-webkit-text-size-adjust:100%}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
body{font-family:'Noto Sans JP',system-ui,sans-serif;background:var(--bg);color:var(--fg);line-height:1.8}
body.nav-open{overflow:hidden}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.skip{position:absolute;left:-999px;top:0;background:var(--accent);color:#fff;padding:.5rem 1rem;z-index:100}.skip:focus{left:8px;top:8px}
.wrap{max-width:780px;margin:0 auto;padding:0 16px}

/* ヘッダー */
header.site{position:sticky;top:0;z-index:30;height:var(--hdr);background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--border)}
header.site .wrap{height:100%;display:flex;align-items:center;justify-content:space-between;gap:.5rem}
.logo{display:flex;align-items:center;gap:.5rem;font-weight:700;color:var(--fg);font-size:1.02rem}
.logo:hover{text-decoration:none}
.logo .mark{display:grid;place-items:center;width:30px;height:30px;border-radius:7px;background:var(--accent);color:#fff;font-family:'IBM Plex Mono',monospace;font-size:.78rem;font-weight:600}
.hdr-nav{display:flex;align-items:center;gap:.15rem}
.hdr-nav .txt{color:var(--dim);font-size:.88rem;padding:.4rem .6rem;border-radius:6px}
.hdr-nav .txt:hover{color:var(--fg);background:var(--code);text-decoration:none}
.icon-btn{display:grid;place-items:center;width:42px;height:42px;border:0;border-radius:8px;background:transparent;color:var(--fg);cursor:pointer}
.icon-btn:hover{background:var(--code)}
.icon-btn svg{width:22px;height:22px}
@media (max-width:560px){.hdr-nav .txt{display:none}}

/* ハンバーガーメニュー（右から出る引き出し） */
.overlay{position:fixed;inset:0;z-index:40;background:rgba(0,0,0,.4);opacity:0;visibility:hidden;transition:opacity .2s,visibility .2s}
.drawer{position:fixed;top:0;right:0;bottom:0;z-index:50;width:min(380px,88vw);background:var(--bg);box-shadow:var(--shadow);display:flex;flex-direction:column;transform:translateX(100%);visibility:hidden;transition:transform .25s ease,visibility .25s}
body.nav-open .overlay{opacity:1;visibility:visible}
body.nav-open .drawer{transform:none;visibility:visible}
.drawer-head{display:flex;align-items:center;justify-content:space-between;padding:0 8px 0 18px;height:var(--hdr);border-bottom:1px solid var(--border);font-weight:700}
.drawer-body{overflow-y:auto;padding:14px 18px 32px;flex:1}
.search{position:relative;margin-bottom:.5rem}
.search svg{position:absolute;left:12px;top:50%;transform:translateY(-50%);width:18px;height:18px;color:var(--dim)}
.search input{width:100%;font:inherit;font-size:16px;padding:.65rem .8rem .65rem 2.4rem;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--fg)}
.search input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.search-hint{font-size:.78rem;color:var(--dim);margin-bottom:1rem}
.results{list-style:none;margin:0 0 1rem;padding:0}
.results li{margin:0}
.results a{display:block;padding:.55rem .7rem;border-radius:8px;color:var(--fg)}
.results a:hover,.results a.sel{background:var(--accent-soft);text-decoration:none}
.results .k{display:inline-block;font-size:.68rem;font-weight:700;color:var(--accent);border:1px solid var(--accent);border-radius:3px;padding:0 .3rem;margin-right:.4rem;vertical-align:1px}
.results .s{display:block;font-family:'IBM Plex Mono',monospace;font-size:.82rem;color:var(--dim)}
.results .none{color:var(--dim);font-size:.9rem;padding:.5rem .2rem}
.nav-sec{margin-top:1.1rem}
.nav-sec h4{font-size:.75rem;color:var(--dim);letter-spacing:.06em;margin-bottom:.35rem}
.nav-sec ul{list-style:none;margin:0;padding:0}
.nav-sec li{margin:0}
.nav-sec a{display:flex;justify-content:space-between;align-items:center;padding:.5rem .6rem;border-radius:8px;color:var(--fg)}
.nav-sec a:hover{background:var(--code);text-decoration:none}
.nav-sec a[aria-current]{background:var(--accent-soft);color:var(--accent);font-weight:700}
.nav-sec .n{font-size:.75rem;color:var(--dim)}
.chips{display:flex;flex-wrap:wrap;gap:.4rem}
.chips a{display:inline-block;padding:.25rem .65rem;border:1px solid var(--border);border-radius:999px;font-size:.85rem;color:var(--fg)}
.chips a:hover{border-color:var(--accent);color:var(--accent);text-decoration:none}

/* 本文 */
main{padding:1.2rem 0 3rem}
nav.bc{font-size:.8rem;color:var(--dim);margin-bottom:.75rem;overflow-x:auto;white-space:nowrap}nav.bc a{color:var(--dim)}
h1{font-size:1.5rem;line-height:1.4;margin-bottom:.6rem}
h2{font-size:1.12rem;margin:2.2rem 0 .8rem;padding-bottom:.3rem;border-bottom:2px solid var(--accent)}
h3{font-size:1rem;margin:1.4rem 0 .5rem}
p{margin-bottom:1rem}ul,ol{margin:0 0 1rem 1.3rem}li{margin-bottom:.35rem}
.lead{color:var(--dim)}
.mono,code{font-family:'IBM Plex Mono',ui-monospace,monospace}
.toc{margin:1rem 0 .5rem;padding:.7rem .8rem;background:var(--card);border:1px solid var(--border);border-radius:var(--r)}
.toc b{display:block;font-size:.75rem;color:var(--dim);margin-bottom:.4rem}
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
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.6rem;margin-bottom:1rem}
.grid a{display:block;background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:.6rem .8rem;color:var(--fg);transition:border-color .15s,transform .15s}
.grid a:hover{border-color:var(--accent);text-decoration:none;transform:translateY(-1px)}
.grid .u{font-family:'IBM Plex Mono',ui-monospace,monospace;color:var(--accent);font-size:.9rem}
.cat-cards a{padding:.85rem 1rem}
.cat-cards .t{font-weight:700}
.cat-cards .d{font-size:.82rem;color:var(--dim);line-height:1.6;margin-top:.2rem}
.cat-cards .n{font-size:.75rem;color:var(--accent);margin-top:.35rem}
.tag{display:inline-block;font-size:.72rem;font-weight:700;color:var(--accent);background:var(--accent-soft);border-radius:3px;padding:.05rem .45rem;margin-right:.3rem}
.home-search{display:flex;align-items:center;gap:.6rem;width:100%;margin:1rem 0 .5rem;padding:.8rem 1rem;border:1px solid var(--border);border-radius:12px;background:var(--card);color:var(--dim);font:inherit;font-size:.95rem;cursor:pointer;text-align:left}
.home-search:hover{border-color:var(--accent)}
.home-search svg{width:18px;height:18px;flex:none}

/* フッター・トップへ戻る */
footer.site{border-top:1px solid var(--border);padding:1.6rem 0 2.5rem;font-size:.82rem;color:var(--dim)}
footer.site .links{display:flex;flex-wrap:wrap;gap:.4rem 1rem;margin-bottom:.8rem}
footer.site a{color:var(--dim)}
.to-top{position:fixed;right:16px;bottom:16px;z-index:20;width:44px;height:44px;border-radius:50%;border:1px solid var(--border);background:var(--card);color:var(--fg);box-shadow:var(--shadow);cursor:pointer;display:grid;place-items:center;opacity:0;visibility:hidden;transition:opacity .2s,visibility .2s}
.to-top.show{opacity:1;visibility:visible}
.to-top svg{width:20px;height:20px}
.tag.lv{color:var(--dim);background:var(--code)}
.goals{margin:1rem 0;padding:.8rem 1rem;border-left:4px solid var(--ok);background:var(--card);border-radius:0 var(--r) var(--r) 0}
.goals b{font-size:.85rem}.goals ul{margin:.3rem 0 0 1.2rem}.goals li{margin:.15rem 0;font-size:.92rem}
.meaning{font-size:1.05rem;padding:.2rem 0}
.wordeq{margin:1rem 0;padding:.9rem 1rem;border:2px dashed var(--accent);border-radius:var(--r);background:var(--card)}
.wordeq .lbl{font-size:.75rem;font-weight:700;color:var(--accent);margin-bottom:.2rem}
.wordeq .eq{font-size:1.08rem;font-weight:700;line-height:1.7}
table.swap td:first-child{font-weight:700}
table.swap th:last-child,table.swap td:last-child{white-space:nowrap}
.unitname{border-style:solid;border-color:var(--accent);background:var(--accent-soft)}
.summary{margin:2rem 0 1rem;padding:.9rem 1.1rem;background:var(--accent-soft);border-radius:var(--r)}
.summary ul{margin:.3rem 0 0 1.2rem}.summary li{margin:.2rem 0}
.quiz{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:1rem}
.quiz .opts{list-style:none;margin:.4rem 0 .8rem;padding:0;display:grid;gap:.4rem}
.quiz .opts li{display:flex;align-items:center;gap:.6rem;padding:.45rem .7rem;border:1px solid var(--border);border-radius:8px;margin:0}
.quiz .opt{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--code);font-size:.78rem;font-weight:700;flex:none}
.quiz details summary{cursor:pointer;color:var(--accent);font-weight:700}
.quiz details p{margin:.5rem 0 0}
footer.site .src{font-size:.78rem;margin:0 0 .5rem}
"""

JS = r"""
(() => {
  const d = document, body = d.body;
  const drawer = d.getElementById('drawer'), overlay = d.getElementById('overlay');
  const menuBtn = d.getElementById('menu-btn'), searchBtns = d.querySelectorAll('[data-open-search]');
  const closeBtn = d.getElementById('close-btn'), q = d.getElementById('q'), list = d.getElementById('results');
  let lastFocus = null, index = null, sel = -1;

  const isOpen = () => body.classList.contains('nav-open');
  function open(focusSearch) {
    lastFocus = d.activeElement;
    drawer.inert = false;
    body.classList.add('nav-open');
    menuBtn.setAttribute('aria-expanded', 'true');
    setTimeout(() => (focusSearch ? q : closeBtn).focus(), 60);
    loadIndex();
  }
  function close() {
    body.classList.remove('nav-open');
    menuBtn.setAttribute('aria-expanded', 'false');
    drawer.inert = true;
    if (lastFocus) lastFocus.focus();
  }
  menuBtn.addEventListener('click', () => (isOpen() ? close() : open(false)));
  searchBtns.forEach(b => b.addEventListener('click', () => open(true)));
  closeBtn.addEventListener('click', close);
  overlay.addEventListener('click', close);
  d.addEventListener('keydown', e => {
    if (e.key === 'Escape' && isOpen()) { close(); return; }
    if (e.key === '/' && !isOpen() && !/input|textarea/i.test(d.activeElement.tagName)) { e.preventDefault(); open(true); return; }
    if (e.key === 'Tab' && isOpen()) {           // 引き出しの中でフォーカスを回す
      const f = drawer.querySelectorAll('a[href],button,input');
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && d.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && d.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  // 検索
  const norm = s => s.normalize('NFKC').toLowerCase().replace(/[\s・·]/g, '');
  async function loadIndex() {
    if (index) return;
    try {
      index = await (await fetch('/search.json')).json();
      index.forEach(e => { e.n = norm(e.t); e.a = norm(e.t + e.s + e.k); });
    } catch (_) { index = []; }
  }
  function render(hits, raw) {
    list.innerHTML = ''; sel = -1;
    if (!raw) return;
    if (!hits.length) {
      const li = d.createElement('li'); li.className = 'none';
      li.textContent = '見つかりませんでした。量の名前（例：電圧）や単位（例：V、J/K）で探してみてください。';
      list.appendChild(li); return;
    }
    hits.slice(0, 30).forEach(e => {
      const li = d.createElement('li'), a = d.createElement('a'), k = d.createElement('span'), s = d.createElement('span');
      a.href = e.u; k.className = 'k'; k.textContent = e.y; s.className = 's'; s.textContent = e.s;
      a.append(k, d.createTextNode(e.t), s); li.appendChild(a); list.appendChild(li);
    });
  }
  q.addEventListener('input', async () => {
    await loadIndex();
    const raw = q.value.trim(), v = norm(raw);
    if (!v) { render([], ''); return; }
    const hits = [];
    for (const e of index) {
      let score = -1;
      if (e.units && e.units.includes(raw)) score = 0;          // 単位記号がぴったり一致（大文字小文字も区別）
      else if (e.n.startsWith(v)) score = 1;
      else if (e.n.includes(v)) score = 2;
      else if (e.a.includes(v)) score = 3;
      if (score >= 0) hits.push([score + (e.y === '量' ? 0 : 0.5), e]);
    }
    hits.sort((x, y) => x[0] - y[0]);
    render(hits.map(h => h[1]), raw);
  });
  q.addEventListener('keydown', e => {
    const items = list.querySelectorAll('a');
    if (!items.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items.forEach((a, i) => a.classList.toggle('sel', i === sel));
      items[sel].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      location.href = items[Math.max(sel, 0)].href;
    }
  });

  // トップへ戻る
  const top = d.getElementById('to-top');
  const onScroll = () => top.classList.toggle('show', scrollY > 600);
  addEventListener('scroll', onScroll, { passive: true }); onScroll();
  top.addEventListener('click', () => scrollTo({ top: 0 }));
})();
"""

ICON_MENU = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>'
ICON_CLOSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>'
ICON_SEARCH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>'
ICON_UP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>'
POPULAR = ["force", "energy", "power", "pressure", "voltage", "resistance", "capacitance", "magnetic_flux_density", "planck", "gas_constant"]


def drawer_html(path):
    def cur(u):
        return ' aria-current="page"' if u == path else ""
    cats = "".join(
        f'<li><a href="/c/{c["id"]}.html"{cur("/c/" + c["id"] + ".html")}>{E(c["name"])}'
        f'<span class="n">{sum(1 for q in QS.values() if q["category"] == c["id"])}量</span></a></li>'
        for c in CATS.values())
    pop = "".join(f'<a href="/q/{x}.html">{E(QS[x]["name"].split("・")[0].split("（")[0])}</a>' for x in POPULAR)
    return f"""<div class="overlay" id="overlay"></div>
<aside class="drawer" id="drawer" inert aria-label="メニュー">
  <div class="drawer-head">メニュー<button class="icon-btn" id="close-btn" aria-label="メニューを閉じる">{ICON_CLOSE}</button></div>
  <div class="drawer-body">
    <div class="search">{ICON_SEARCH}<input id="q" type="search" placeholder="量・単位・公式を検索（例：電圧、J/K）" autocomplete="off" aria-label="サイト内検索"></div>
    <div class="search-hint">名前でも単位記号でも探せます。</div>
    <ul class="results" id="results" aria-live="polite"></ul>
    <div class="nav-sec"><h4>ページ</h4><ul>
      <li><a href="/"{cur("/")}>トップ</a></li>
      <li><a href="/guide.html"{cur("/guide.html")}>単位の読み方と次元解析</a></li>
      <li><a href="/about.html"{cur("/about.html")}>このサイトについて</a></li>
    </ul></div>
    <div class="nav-sec"><h4>分野</h4><ul>{cats}</ul></div>
    <div class="nav-sec"><h4>よく使う量</h4><div class="chips">{pop}</div></div>
  </div>
</aside>"""


def add_toc(body):
    """h2 に id をつけ、3つ以上あれば「このページの内容」を先頭の h2 の前に置く"""
    heads = []
    def repl(m):
        heads.append(m.group(1))
        return f'<h2 id="s{len(heads)}">{m.group(1)}</h2>'
    body = re.sub(r"<h2>(.*?)</h2>", repl, body)
    if len(heads) < 3:
        return body
    chips = "".join(f'<a href="#s{i}">{re.sub(r"<[^>]+>", "", h)}</a>' for i, h in enumerate(heads, 1))
    toc = f'<nav class="toc" aria-label="このページの内容"><b>このページの内容</b><div class="chips">{chips}</div></nav>'
    i = body.index('<h2 id="s1">')
    return body[:i] + toc + body[i:]


def page(path, title, desc, body, crumbs=(), noindex=False):
    bc = ""
    if crumbs:
        parts = ['<a href="/">トップ</a>'] + [f'<a href="{u}">{E(t)}</a>' if u else E(t) for t, u in crumbs]
        bc = '<nav class="bc" aria-label="パンくずリスト">' + " › ".join(parts) + "</nav>"
    body = add_toc(body)
    foot_links = "".join(f'<a href="/c/{c["id"]}.html">{E(c["name"])}</a>' for c in CATS.values())
    doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)} | {SITE_NAME}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{SITE_URL}{path}">
{'<meta name="robots" content="noindex,follow">' if noindex else ''}
<meta name="google-site-verification" content="{GOOGLE_VERIFICATION}">
<meta name="theme-color" content="#1d5fd1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/site.css?v={ASSET_VER}">
<script src="/assets/site.js?v={ASSET_VER}" defer></script>
</head>
<body>
<a class="skip" href="#main">本文へ移動</a>
<header class="site"><div class="wrap">
  <a class="logo" href="/"><span class="mark">SI</span>{SITE_NAME}</a>
  <nav class="hdr-nav" aria-label="メインメニュー">
    <a class="txt" href="/guide.html">使い方</a>
    <button class="icon-btn" data-open-search aria-label="検索">{ICON_SEARCH}</button>
    <button class="icon-btn" id="menu-btn" aria-label="メニューを開く" aria-controls="drawer" aria-expanded="false">{ICON_MENU}</button>
  </nav>
</div></header>
{drawer_html(path)}
<main id="main"><div class="wrap">
{bc}
{body}
</div></main>
<footer class="site"><div class="wrap">
  <div class="links"><a href="/">トップ</a><a href="/guide.html">単位の読み方</a><a href="/about.html">このサイトについて</a>{foot_links}</div>
  <p class="src">単位の定義は、国際度量衡局（BIPM）の SI パンフレット第9版と、その日本語版（産業技術総合研究所 計量標準総合センター）に基づいています。</p>
  {SITE_NAME} — SI単位と次元解析で物理を理解する。最終更新日：{UPDATED}
</div></footer>
<button class="to-top" id="to-top" aria-label="ページの先頭へ戻る">{ICON_UP}</button>
</body>
</html>"""
    out = OUT / path.lstrip("/")
    if path.endswith("/"):
        out = out / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    ALL_PAGES.append(path)
    if not noindex:
        PATHS.append(path)


def build_assets():
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    (OUT / "assets" / "site.css").write_text(CSS.strip() + "\n", encoding="utf-8")
    (OUT / "assets" / "site.js").write_text(JS.strip() + "\n", encoding="utf-8")
    idx = []
    for q in QS.values():
        names = " ".join(UNITS[s]["name"] for s in q["ud"])
        idx.append({"y": "量", "t": q["name"], "s": q["unit_str"], "u": f"/q/{q['id']}.html",
                    "units": [q["unit_str"], fmt_base(q["dims"])] + list(q["ud"]) if len(q["ud"]) == 1 else [q["unit_str"], fmt_base(q["dims"])],
                    "k": f"{names} {fmt_base(q['dims'])} {CATS[q['category']]['name']}"})
    for f in FS.values():
        idx.append({"y": "公式", "t": f["name"], "s": f["expr"], "u": f"/f/{f['id']}.html",
                    "k": " ".join(QS[x]["name"] for x in f["quantities"]) + " " + CATS[f["category"]]["name"]})
    for c in CATS.values():
        idx.append({"y": "分野", "t": c["name"], "s": c["description"], "u": f"/c/{c['id']}.html", "k": ""})
    idx.append({"y": "解説", "t": "単位の読み方と次元解析", "s": "言葉から単位を組み立てる・基本単位・検算", "u": "/guide.html", "k": "次元解析 使い方 ガイド 読み方 基本単位"})
    idx.append({"y": "解説", "t": "このサイトについて", "s": "目的・内容の確かめ方・出典", "u": "/about.html", "k": "運営 出典 参考文献"})
    (OUT / "search.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


PATHS = []       # サイトマップに載せるページ
ALL_PAGES = []   # 生成したすべてのページ

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
    if not q["defined_by"]:
        return []
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
            if set(ud) & set(q["ud"]) or len(ud) > 3:      # 自分自身を含む書き方や、記号が多すぎる書き方は省く
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

LEVEL_NOTE = {"中学": "中学理科で出てくる", "高校": "高校物理・化学で出てくる", "大学": "大学の物理で出てくる"}


def word_label(w, e):
    """言葉の式での表示：『半径』² のように"""
    e = Fr(e)
    a = abs(e)
    return f"（{w}）{sup(a)}" if a != 1 else w


def word_equation(q):
    """'進んだ距離 ÷ かかった時間' のような言葉の式（かける物を先に）"""
    ws = sorted(q["words"], key=lambda t: t[2] < 0)
    out = []
    for i, (w, _, e) in enumerate(ws):
        lab = word_label(w, e)
        if e > 0:
            out.append(lab if i == 0 else f"× {lab}")
        else:
            out.append(f"1 ÷ {lab}" if i == 0 else f"÷ {lab}")
    return " ".join(out), ws


def unit_equation(ws):
    out = []
    for i, (_, wq, e) in enumerate(ws):
        u = QS[wq]["unit_str"]
        if u.startswith("1"):
            u = "1"
        a = abs(Fr(e))
        simple = re.fullmatch(r"[A-Za-zΩ⁰¹²³⁴⁵⁶⁷⁸⁹]+|1", u) is not None
        disp = (u if simple else f"({u})") + (sup(a) if a != 1 else "")
        if e > 0:
            out.append(disp if i == 0 else f"× {disp}")
        else:
            out.append(f"1 ÷ {disp}" if i == 0 else f"÷ {disp}")
    return " ".join(out)


def words_section(q):
    """言葉で意味をつかみ、言葉を単位に置き換える"""
    b = [f"<h2>{E(q['name'])}とは？ 言葉で意味をつかむ</h2>",
         f'<p class="meaning"><b>{E(q["name"])}とは</b>　{E(q["meaning"])}</p>']
    if not q.get("words"):
        return b
    eq, ws = word_equation(q)
    b.append('<div class="wordeq"><div class="lbl">言葉の式</div>'
             f'<div class="eq">{E(q["name"])} ＝ {E(eq)}</div></div>')
    b.append("<p>言葉の式に出てくるそれぞれの言葉は、すでに単位がわかっている量です。言葉を単位に置き換えてみましょう。</p>")
    b.append('<div class="tbl"><table class="swap"><tr><th>言葉</th><th>何の量か</th><th>単位</th></tr>')
    seen = set()
    for w, wq, e in ws:
        if w in seen:
            continue
        seen.add(w)
        u = QS[wq]["unit_str"]
        b.append(f'<tr><td>{E(w)}</td><td>{qlink(wq)}</td><td class="mono">{E(u)}</td></tr>')
    b.append("</table></div>")
    combined = {}
    for _, wq, e in ws:
        combined = add_ud(combined, QS[wq]["ud"], Fr(e))
    combined, dropped = tidy(combined, q)
    lines = [f"[{E(q['name'])}] ＝ {E(unit_equation(ws))}"]
    c = fmt_ud(combined) if combined else "1"
    if c != unit_equation(ws):
        lines.append(f"　　　＝ {E(c)}" + (f"　<span class=\"lead\">（{'・'.join(dropped)} は次元をもたないので省く）</span>" if dropped else ""))
    base = fmt_base(q["dims"]) if q["dims"] != ZERO else "1"
    if base not in (c,):
        lines.append(f"　　　＝ {E(base)}")
    if q["dims"] != ZERO and q["unit_str"] not in (c, base):
        lines.append(f"　　　＝ {E(q['unit_str'])}")
    b.append('<div class="calc">' + "<br>".join(lines) + "</div>")
    named = [s_ for s_ in q["ud"] if s_ not in BASE_SYMS and s_ not in ("rad", "sr")]
    if len(q["ud"]) == 1 and named:
        sym = named[0]
        b.append(f'<div class="note unitname"><b>{E(UNITS[sym]["name"])}（{E(sym)}）</b>は、この組み合わせ '
                 f'<span class="mono">{E(c)}</span> に付けられた名前です。<br>{E(UNITS[sym]["meaning"])}</div>')
    elif q["dims"] == ZERO:
        b.append('<div class="note">単位どうしが打ち消しあって何も残りません。だから「次元をもたない量」なのです。</div>')
    else:
        b.append(f'<p>言葉の通りに単位を並べるだけで、<span class="mono ok">{E(q["unit_str"])}</span> が出てきました。</p>')
    return b


def base_section(q):
    sym = next(iter(q["ud"]))
    return [f"<h2>{E(q['name'])}とは？ 言葉で意味をつかむ</h2>",
            f'<p class="meaning"><b>{E(q["name"])}とは</b>　{E(q["meaning"])}</p>',
            f'<div class="note unitname"><b>{E(UNITS[sym]["name"])}（{E(sym)}）</b>はSIの基本単位のひとつで、'
            f"ほかの単位に分解できません。<br>{E(UNITS[sym]['meaning'])}</div>",
            "<p>ほかのすべての単位は、7つの基本単位を「かける」「割る」で組み合わせて作られています。"
            f"{E(q['name'])}を含む単位の例は、下の「{E(q['name'])}が出てくる公式」から見られます。</p>"]


def quiz(q):
    """基本単位での表し方を選ぶ確認問題（答えは開くと見える）"""
    if q["dims"] == ZERO or not q["defined_by"]:
        return []
    right = fmt_base(q["dims"])
    import hashlib
    pool = sorted({fmt_base(o["dims"]) for o in QS.values() if o["dims"] not in (ZERO, q["dims"])})
    h = int(hashlib.md5(q["id"].encode()).hexdigest(), 16)
    # 次元の近いもの（基本単位の種類が似ているもの）を優先してまぎらわしくする
    def closeness(x):
        return (len(set(re.findall(r"[a-zA-Z]+", x)) ^ set(re.findall(r"[a-zA-Z]+", right))), x)
    cand = sorted(pool, key=closeness)[:8]
    picks = [cand[(h >> (4 * i)) % len(cand)] for i in range(12)]
    wrong = list(dict.fromkeys(p_ for p_ in picks if p_ != right))[:3]
    opts = wrong + [right]
    k = h % 4
    opts = opts[:3]
    opts.insert(k, right)
    letters = "ABCD"
    lis = "".join(f'<li><span class="opt">{letters[i]}</span><span class="mono">{E(o)}</span></li>' for i, o in enumerate(opts))
    why = ""
    if q.get("words"):
        eq, ws = word_equation(q)
        why = f"{E(q['name'])} ＝ {E(eq)} なので、[{E(q['name'])}] ＝ {E(unit_equation(ws))} ＝ {E(right)}。"
    return [f"<h2>確認問題</h2>",
            f'<div class="quiz"><p><b>Q.</b> {E(q["name"])}の単位 <span class="mono">{E(q["unit_str"])}</span> を基本単位で表したものはどれ？</p>'
            f'<ul class="opts">{lis}</ul>'
            f'<details><summary>答えを見る</summary><p><b>正解：{letters[k]}</b>　<span class="mono ok">{E(right)}</span></p>'
            f'<p>{why}</p></details></div>']


# 量 → その量を材料にして作られる量（次に読む）
DEPENDENTS = {qid: [] for qid in QS}
for _q in QS.values():
    for _w in _q.get("words") or []:
        if _w[1] != _q["id"] and _q["id"] not in DEPENDENTS[_w[1]] and QS[_w[1]]["dims"] != ZERO:
            DEPENDENTS[_w[1]].append(_q["id"])


def build_quantity(q):
    qid = q["id"]
    cat = CATS[q["category"]]
    d = q["dims"]
    u = q["unit_str"]
    base = fmt_base(d)
    uname = "・".join(UNITS[s_]["name"] for s_ in q["ud"]) if len(q["ud"]) == 1 else ""
    utitle = f"{uname}（{u}）" if uname and u != base else u
    if d == ZERO:
        title = f"{q['name']}の単位はなぜ無次元？意味と仕組み"
    elif not q["defined_by"]:
        title = f"{q['name']}の単位 {utitle} の意味｜SI基本単位"
    elif u == base:
        title = f"{q['name']}の単位 {u} の意味を言葉から理解する"
    else:
        title = f"{q['name']}の単位 {utitle} の意味｜基本単位で表すと {base}"
    desc = (f"{q['name']}とは{q['meaning']}その言葉をそのまま単位に置き換えると {u}"
            + (f"（= {base}）" if base != u and d != ZERO else "") + " になる理由を、図式と確認問題でやさしく解説。")
    lvl = q.get("level", "高校")
    b = [f'<span class="tag">{E(cat["name"])}</span><span class="tag lv">{E(LEVEL_NOTE[lvl])}</span>',
         f"<h1>{E(title)}</h1>",
         '<div class="hero">',
         f'<div class="big">{E(u if d != ZERO else "1（無次元）")}{(" = " + E(base)) if base != u and d != ZERO else ""}</div>',
         f'<div class="sub">次元 {E(fmt_dim(d))}</div></div>']

    goals = [f"{q['name']}を言葉でどう言い表すか"]
    if q.get("words"):
        goals.append(f"その言葉を単位に置き換えると、なぜ {u} になるのか" if d != ZERO else "その言葉を単位に置き換えると、なぜ単位が消えるのか")
    elif d != ZERO:
        goals.append(f"基本単位 {u} がどのように決められているか")
    if alt_expressions(qid):
        goals.append(f"{u} のいろいろな書き方と、その根拠になる公式")
    b.append('<div class="goals"><b>このページでわかること</b><ul>' + "".join(f"<li>{E(g)}</li>" for g in goals) + "</ul></div>")

    b += words_section(q) if q["defined_by"] or d == ZERO and q.get("words") else (base_section(q) if q["ud"] else words_section(q))

    steps = chain(qid)
    if len(steps) > 1:
        b.append(f"<h2>基本単位までたどる</h2>")
        route = " → ".join(E(QS[sid]["name"]) for sid, _, _ in steps)
        b.append(f"<p>言葉の式に出てきた量も、さらに言葉の式で分解できます。{route} の順にたどると、"
                 "すべて基本単位（m・kg・s・A・K・mol・cd）だけで表せます。</p>")
        basics = [st for st in steps[:-1] if st[0] in BASICS] if len(steps) >= 4 else []
        rest = [st for st in steps if st not in basics]
        if basics:
            names = "・".join(QS[sid]["name"] for sid, _, _ in basics)
            b.append(f'<details class="pre"><summary>前提：{E(names)}の単位（知っていれば飛ばしてOK）</summary>')
            b += [step_html(st) for st in basics]
            b.append("</details>")
        b += [step_html(st) for st in rest]

    alts = alt_expressions(qid)
    if alts:
        b.append(f"<h2>{E(u)} の別の書き方</h2>")
        b.append("<p>同じ量でも、使う公式によって単位の見え方が変わります。どれも基本単位にすると一致します。</p>")
        b.append('<div class="tbl"><table><tr><th>書き方</th><th>根拠になる公式</th></tr>')
        for s_, fid, x in alts:
            b.append(f'<tr><td class="mono">{E(u)} = {E(s_)}</td><td>{flink(fid)}<br><span class="mono">{E(FS[fid]["expr"])}</span></td></tr>')
        b.append("</table></div>")

    same = [x for x in SAME_DIM[d] if x != qid]
    if same and d != ZERO:
        b.append("<h2>よくある間違い：同じ単位でも別の量</h2>")
        b.append(f"<p>次の量は {E(q['name'])} と次元 {E(fmt_dim(d))} が同じです。単位が一致しても意味が違うことがあるので、"
                 "検算のときは「何を表す量か」も確かめましょう。</p><ul>")
        for x in same:
            b.append(f'<li>{qlink(x)}（<span class="mono">{E(QS[x]["unit_str"])}</span>）— {E(QS[x]["meaning"])}</li>')
        b.append("</ul>")

    forms = Q_FORMS[qid]
    if forms:
        b.append(f"<h2>{E(q['name'])}が出てくる公式</h2><ul>")
        for fid in forms:
            b.append(f'<li>{flink(fid)}：<span class="mono">{E(FS[fid]["expr"])}</span></li>')
        b.append("</ul>")

    summ = [f"{q['name']}とは、{q['meaning']}"]
    if q.get("words"):
        eq, ws = word_equation(q)
        summ.append(f"言葉の式 {q['name']} ＝ {eq} を単位に置き換えると {fmt_ud(tidy(combine_words(q), q)[0]) or '1'}。")
    if d != ZERO and base != u:
        summ.append(f"基本単位だけで書くと {base}。")
    b.append('<div class="summary"><b>まとめ</b><ul>' + "".join(f"<li>{E(x)}</li>" for x in summ) + "</ul></div>")

    b += quiz(q)

    nxt = DEPENDENTS.get(qid, [])
    if nxt:
        b.append(f"<h2>次に読む：{E(q['name'])}を使って表される量</h2><div class=\"grid\">"
                 + "".join(qcard(x) for x in nxt[:9]) + "</div>")

    page(f"/q/{qid}.html", title, desc, "\n".join(b), [cat_crumb(q["category"]), (q["name"], None)])


def combine_words(q):
    c = {}
    for _, wq, e in q["words"]:
        c = add_ud(c, QS[wq]["ud"], Fr(e))
    return c

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
    page(f"/r/{pair_slug(a, bq)}.html", title, desc, "\n".join(b), noindex=True, crumbs=
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
         f'<button class="home-search" data-open-search>{ICON_SEARCH}量・単位・公式を検索（例：電圧、J/K、オームの法則）</button>',
         '<div class="hero"><div class="big">J = N·m = kg·m²/s²</div>'
         '<div class="sub">F = ma と W = Fx を知っていれば、ジュールの中身は自分で導ける</div></div>',
         "<h2>このサイトの考え方</h2>",
         "<p>物理の単位は、たった7つの基本単位のかけ算・わり算でできています。"
         "初めて見る単位や公式も、知っている公式を使って基本単位まで分解すれば、その正体がわかります。"
         "このサイトでは数値の換算は扱わず、<b>SI単位と次元だけ</b>で説明します。</p>",
         '<p>たとえば速さは「1秒あたりに進む距離」＝「距離 ÷ 時間」。言葉をそのまま単位に置き換えると m ÷ s ＝ m/s になります。'
         'すべての量のページで、まず<b>言葉で意味をつかみ、その言葉を単位に置き換える</b>流れで説明しています。</p>',
         '<p><a href="/guide.html">→ はじめに：単位の読み方を読む</a></p>',
         "<h2>7つの基本単位</h2><div class=\"grid\">"
         + "".join(qcard(x) for x in ["length", "mass", "time", "current", "temperature", "amount", "luminous_intensity"])
         + "</div>",
         "<h2>まずはここから</h2><div class=\"grid\">"
         + "".join(qcard(x) for x in ["force", "energy", "power", "voltage", "resistance", "magnetic_flux_density", "planck", "gas_constant"])
         + "</div>",
         '<h2>分野から探す</h2>']
    cards = []
    for c in CATS.values():
        n = sum(1 for q in QS.values() if q["category"] == c["id"])
        m = sum(1 for f in FS.values() if f["category"] == c["id"])
        cards.append(f'<a href="/c/{c["id"]}.html"><div class="t">{E(c["name"])}</div>'
                     f'<div class="d">{E(c["description"])}</div><div class="n">量 {n}・公式 {m}</div></a>')
    b.append('<div class="grid cat-cards">' + "".join(cards) + "</div>")
    page("/", "SI単位と次元解析で物理を理解する", SITE_DESC, "\n".join(b))

def unit_home(sym):
    """その単位をそのまま単位にもつ量（なければ None）"""
    for q in QS.values():
        if list(q["ud"]) == [sym] and q["ud"][sym] == 1:
            return q
    return None


def build_guide():
    base_rows = "".join(
        f'<tr><td class="mono">{E(sym)}</td><td>{E(UNITS[sym]["name"])}</td>'
        f'<td>{qlink(unit_home(sym)["id"]) if unit_home(sym) else ""}</td><td>{E(UNITS[sym]["meaning"])}</td></tr>'
        for sym in ["m", "kg", "s", "A", "K", "mol", "cd"])
    named = [sym for sym in UNITS if sym not in BASE_SYMS]
    named_rows = []
    for sym in named:
        hq = unit_home(sym)
        bse = fmt_base(UDIMS[sym]) if UDIMS[sym] != ZERO else "1（無次元）"
        named_rows.append(f'<tr><td class="mono">{E(sym)}</td><td>{qlink(hq["id"]) if hq else E(UNITS[sym]["name"])}</td>'
                          f'<td>{E(UNITS[sym]["meaning"])}</td><td class="mono">{E(bse)}</td></tr>')
    body = f"""
<h1>単位の読み方：言葉の意味から単位を組み立てる</h1>
<p class="lead">物理の単位は、暗記するものではなく「その量を言葉で言い表したもの」を記号に置き換えたものです。このページでは、言葉から単位を組み立てる方法と、次元解析の使い方を説明します。</p>
<div class="goals"><b>このページでわかること</b><ul>
<li>量の意味を表す言葉が、どのように単位の記号に置き換わるか</li>
<li>7つの基本単位と、名前のついた単位の意味</li>
<li>次元解析で、式の検算や公式の推測をする方法</li></ul></div>

<h2>1. 単位は「言葉の式」から生まれる</h2>
<p>たとえば速さは「1秒あたりに進む距離」、つまり<b>「進んだ距離 ÷ かかった時間」</b>です。言葉をそれぞれの単位に置き換えると、</p>
<div class="wordeq"><div class="lbl">言葉の式</div><div class="eq">速さ ＝ 進んだ距離 ÷ かかった時間</div></div>
<div class="calc">[速さ] ＝ m ÷ s ＝ m/s</div>
<p>となり、速さの単位 m/s がそのまま出てきます。どんなに難しそうな単位も、同じやり方で組み立てられます。</p>
<h3>言葉と記号の対応</h3>
<div class="tbl"><table>
<tr><th>言葉</th><th>記号</th><th>例</th></tr>
<tr><td>「〜あたり」「1〜につき」</td><td class="mono">÷（/）</td><td>1秒あたりに進む距離 → m/s</td></tr>
<tr><td>「〜と〜の積」「〜をかけた」</td><td class="mono">×（·）</td><td>力 × 距離 → N·m</td></tr>
<tr><td>「〜の2乗」「〜の3乗」</td><td class="mono">² ³</td><td>長さ × 長さ → m²</td></tr>
<tr><td>「〜の逆数」「1回にかかる時間をひっくり返す」</td><td class="mono">⁻¹</td><td>周期の逆数 → s⁻¹ ＝ Hz</td></tr>
<tr><td>「〜は〜の何倍か」「〜の比」</td><td class="mono">÷（単位が消える）</td><td>弧の長さ ÷ 半径 → m/m ＝ 1</td></tr>
</table></div>

<h2>2. 7つの基本単位</h2>
<p>SI（国際単位系）では、次の7つが基本単位です。ほかのすべての単位は、この7つのかけ算・わり算で作られています。</p>
<div class="tbl"><table><tr><th>記号</th><th>名前</th><th>量</th><th>どう決められているか</th></tr>{base_rows}</table></div>

<h2>3. 名前のついた単位</h2>
<p>よく使う組み合わせには名前がついています。名前のついた単位も、言葉の意味を読めば中身がわかります。</p>
<div class="tbl"><table><tr><th>記号</th><th>量</th><th>言葉での意味</th><th>基本単位</th></tr>{"".join(named_rows)}</table></div>

<h2>4. 知っている公式を使って分解する</h2>
<p>知らない単位が出てきたら、その量が出てくる「知っている公式」を探し、その量について解きます。
たとえば電圧 V を知らなくても、電力の式 P = IV を知っていれば、</p>
<div class="calc">V = P / I　→　[V] = W / A = (kg·m²/s³) / A = kg·m²/(A·s³)</div>
<p>と分解できます。W（ワット）がわからなければ、さらに P = W/t、W = Fx、F = ma とたどればよいのです。</p>

<h2>5. 両辺の単位が一致するか確かめる</h2>
<p>正しい公式では、左辺と右辺の単位が必ず一致します。たとえば運動エネルギー K = ½mv² では、</p>
<div class="calc">左辺 [K] = J = kg·m²/s²<br>右辺 [m v²] = kg × (m/s)² = kg·m²/s²　<span class="ok">一致</span></div>
<p>½ のような係数は単なる数で単位をもたないので、次元解析では無視してかまいません。
単位が合わなければ、式のどこかが間違っています。</p>

<h2>6. 単位が同じでも、同じ量とは限らない</h2>
<p>トルク（N·m）とエネルギー（J）は基本単位にするとどちらも kg·m²/s² です。
ヘルツ（Hz）とベクレル（Bq）もどちらも s⁻¹ です。次元解析は式の検算に強力ですが、
次元が同じだからといって同じ意味の量とは限らない点には注意しましょう。</p>

<h2>7. 単位から公式を推測する</h2>
<p>単位の組み合わせから、式の形を推測することもできます。たとえば単振り子の周期 T が、ひもの長さ l [m] と
重力加速度 g [m/s²] だけで決まるとすると、秒 s をつくる組み合わせは</p>
<div class="calc">√(l / g)　→　√(m ÷ (m/s²)) = √(s²) = s</div>
<p>しかありません。実際の公式 T = 2π√(l/g) と、係数 2π を除いて一致します。</p>
<p><a href="/">→ トップに戻って物理量を探す</a></p>
"""
    page("/guide.html", "単位の読み方と次元解析の使い方", "物理の単位を、量の意味を表す言葉から組み立てる方法を解説。7つの基本単位と名前のついた単位の意味、次元解析での検算や公式の推測まで。",
         body, [("単位の読み方と次元解析", None)])


def build_about():
    nq = len(QS); nf = len(FS); nw = sum(1 for q in QS.values() if q.get("words"))
    body = f"""
<h1>このサイトについて</h1>
<p class="lead">{E(SITE_NAME)}は、物理の単位を「暗記」ではなく「意味から組み立てて理解する」ための学習サイトです。</p>

<h2>このサイトの考え方</h2>
<p>単位は、その量を言葉で言い表したものを、記号に置き換えたものです。速さが「1秒あたりに進む距離」だから m/s、圧力が「1 m² あたりの力」だから N/m²。
このサイトのすべての量のページでは、まず言葉で意味をつかみ、その言葉を一つずつ単位に置き換えることで、単位が自然に出てくる流れを示しています。</p>
<ul>
<li>単位はすべてSI（国際単位系）で表しています</li>
<li>数値の換算（km と m の換算など）は扱わず、単位と次元の関係だけに絞っています</li>
<li>中学理科から大学の物理までの量を扱い、各ページに目安のレベルを表示しています</li>
</ul>

<h2>内容の正しさの確かめ方</h2>
<p>ページはプログラムで作っており、公開する前に次の点を自動で検算しています。1つでも合わなければページは作られません。</p>
<ul>
<li>{nf} 個のすべての公式で、左辺と右辺の次元が一致すること</li>
<li>{nw} 個のすべての「言葉の式」で、言葉を単位に置き換えた結果が、その量の単位と一致すること</li>
<li>各量の単位が、その量を定義する公式から導いた単位と一致すること</li>
</ul>
<p>説明文の誤りに気づいた場合は、お知らせいただけると助かります。</p>

<h2>出典・参考資料</h2>
<ul>
<li>国際度量衡局（BIPM）「The International System of Units (SI)」第9版</li>
<li>産業技術総合研究所 計量標準総合センター「国際単位系（SI）第9版（2019）日本語版」</li>
</ul>

<h2>運営</h2>
<p>物理を学ぶ大学生が運営しています。最終更新日：{UPDATED}</p>
"""
    page("/about.html", "このサイトについて", f"{SITE_NAME}の目的、内容の正しさの確かめ方、出典について。", body, [("このサイトについて", None)])

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
    build_assets()
    build_index()
    build_guide()
    build_about()
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
    print(f"✓ 言葉の式 {sum(1 for q in QS.values() if q.get('words'))} 個の単位が一致することを確認")
    print(f"合計: {len(ALL_PAGES)} ページ生成完了（うち検索に載せる {len(PATHS)} ページ）→ {OUT}/")

if __name__ == "__main__":
    main()
