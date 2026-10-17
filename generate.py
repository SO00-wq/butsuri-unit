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
from mathml import mathify
from fractions import Fraction as Fr
from pathlib import Path
from itertools import combinations

OUT = Path("dist")
SITE_NAME = "ブツリ単位ラボ"
SITE_URL = "https://tanitani.butsuri-lab.workers.dev"  # ★独自ドメイン取得後に変更
ASSET_VER = "8"  # CSS/JS を変えたら上げる（ブラウザのキャッシュ対策）
UPDATED = "2026-10-18"  # 最終更新日（内容を更新したら変える）
GOOGLE_VERIFICATION = "kVE91IWkP86K1E_JpBQDklXXu5gz86ZOA64xcgtDUwc"  # Search Console 所有権確認
SITE_DESC = "物理の計算で出した答えが正しいかを、答えの単位で確かめるためのサイト。検算の手順、よくあるミス、トレーニング、単位辞典。"

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


def split_half(items):
    """[(記号, 指数)] を、根号の外に出す部分と、√ の中に入れる部分に分ける。
    例：v₀¹ h^(1/2) g^(-1/2) → 外 [(v₀,1)]、中 [(h,1),(g,-1)]（= v₀√(h/g)）"""
    out_, in_ = [], []
    for s_, e in items:
        e = Fr(e)
        if e.denominator == 2:
            k = int(e)                 # 0 の方向に切り捨て
            if k:
                out_.append((s_, Fr(k)))
            in_.append((s_, (e - k) * 2))
        else:
            out_.append((s_, e))
    return out_, in_

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
    if any(Fr(e).denominator == 2 for _, e in items):
        out_, in_ = split_half(items)
        o = fmt_ud(dict(out_)) if out_ else ""
        r = f"√({fmt_ud(dict(in_))})"
        return f"{o}·{r}" if o and o != "1" else r
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
    if any(Fr(e).denominator == 2 for _, e in terms):
        out_, in_ = split_half(terms)
        r = f"√({factors_str(f, in_)})"
        return f"{factors_str(f, out_)} × {r}" if out_ else r
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
    if any(Fr(e).denominator == 2 for _, e in terms):
        out_, in_ = split_half(terms)
        r = f"√({expr_for(f, in_)})"
        return f"{expr_for(f, out_)} {r}" if out_ else r
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
.practice{display:grid;gap:1rem}
.pq{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:1rem}
.pq .qt{margin-bottom:.6rem}
.pq .qn{display:inline-block;background:var(--accent);color:#fff;font-size:.75rem;font-weight:700;border-radius:4px;padding:.05rem .45rem;margin-right:.45rem}
.pq .u{color:var(--accent);font-size:.9em;white-space:nowrap}
.pq .opts{list-style:none;margin:0 0 .7rem;padding:0;display:grid;gap:.45rem}
.pq .opts li{margin:0}
.ch{display:flex;align-items:center;gap:.6rem;width:100%;text-align:left;font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:.55rem .7rem;cursor:pointer;transition:border-color .15s,background .15s}
.ch:hover:not(:disabled){border-color:var(--accent)}
.ch:disabled{cursor:default}
.ch .opt{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--code);font-size:.78rem;font-weight:700;flex:none}
.ch.right{border-color:var(--ok);background:color-mix(in srgb,var(--ok) 12%,var(--bg))}
.ch.right .opt{background:var(--ok);color:#fff}
.ch.wrong{border-color:#c2410c;background:color-mix(in srgb,#c2410c 10%,var(--bg))}
.ch.wrong .opt{background:#c2410c;color:#fff}
.pq .res{font-weight:700;margin:.2rem 0 .4rem}.pq .res.ng{color:#c2410c}
.pq .exp summary{cursor:pointer;color:var(--accent);font-weight:700;font-size:.92rem}
.pq .exp p{margin:.5rem 0 0;font-size:.95rem}
.mission{margin:.6rem 0 1.4rem;padding:1.2rem 1.25rem;border-radius:var(--r);background:var(--card);border:1px solid var(--border)}
.mission .quote{font-size:1.15rem;font-weight:700;line-height:1.6;margin:0}
.mission .quote-src{color:var(--dim);font-size:.85rem;margin:.3rem 0 0}
.steps3{margin:0 0 1rem 1.4rem}.steps3 li{margin:.6rem 0}
.problem{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:.8rem 1rem;margin:1rem 0}
.problem b{font-size:.8rem;color:var(--dim)}.problem p{margin:.2rem 0 0}
.answer{display:flex;align-items:center;gap:.8rem;flex-wrap:wrap;padding:.7rem 1rem;border-radius:var(--r);margin:.8rem 0;font-size:1.1rem}
.answer .lbl{font-size:.75rem;font-weight:700;border-radius:4px;padding:.1rem .5rem;color:#fff}
.wrong-ans{background:color-mix(in srgb,#c2410c 8%,var(--card));border:1px solid #c2410c}.wrong-ans .lbl{background:#c2410c}
.right-ans{background:color-mix(in srgb,var(--ok) 10%,var(--card));border:1px solid var(--ok)}.right-ans .lbl{background:var(--ok)}
.ng{color:#c2410c;font-weight:700}
.verdict{padding:.6rem .8rem;border-radius:8px;margin:.4rem 0 0}
.verdict.ng{background:color-mix(in srgb,#c2410c 8%,var(--card));font-weight:400}
.verdict.warn{background:color-mix(in srgb,#b45309 10%,var(--card))}
.tag.warn{color:#b45309;background:color-mix(in srgb,#b45309 12%,var(--bg))}
.given{list-style:none;margin:.3rem 0 .2rem;padding:0;display:flex;flex-wrap:wrap;gap:.3rem 1rem;font-size:.92rem}
.given li{margin:0}
.mcards .u{font-size:.82rem}
.feat .d,.mcards .d{font-size:.85rem;color:var(--dim);line-height:1.6;margin-top:.2rem}
.feat .t{font-weight:700}
.checkbox{margin:1rem 0;padding:.8rem 1rem;border-radius:var(--r);border:2px solid var(--ok);background:color-mix(in srgb,var(--ok) 6%,var(--card))}
.checkbox b{font-size:.85rem;color:var(--ok)}
.pitfall{border:2px solid #c2410c;border-style:solid;background:color-mix(in srgb,#c2410c 6%,var(--card))}.pitfall b{color:#c2410c}.checkbox p{margin:.3rem 0 0}
.tnav{margin:.5rem 0 1.2rem}.tnav a[aria-current]{background:var(--accent);color:#fff;border-color:var(--accent)}
.pq .qt .given{margin-top:.5rem}
/* 数式（ノート風の表記） */
math{font-family:"Cambria Math","STIX Two Math","Latin Modern Math","Noto Sans Math",math;font-size:1.12em}
.calc{line-height:2.6;white-space:nowrap}
.calc math{font-size:1.18em}
.hero .big math{font-size:1.2em}
.pq .ch math{font-size:1.15em}
.u math,.grid .u math{font-size:1em}
.results .s math{font-size:1em}
td math{font-size:1.05em}

/* 重要な部分を目立たせる */
.ok{color:var(--ok);font-weight:700;font-size:1.08em}
.ng{color:#c2410c;font-weight:700;font-size:1.08em}
.key{color:#c2410c;font-weight:700;font-size:1.08em}
.steps3 b{color:var(--accent);font-size:1.08em}
.meaning b{color:var(--accent);font-size:1.1em}
.wordeq .eq{font-size:1.18rem}
.answer .mono{font-size:1.3rem;font-weight:700}
.verdict{font-size:1.05rem}.verdict.ng b{color:#c2410c;font-size:1.1em}.verdict.warn b{color:#b45309}
.checkbox .ok{font-size:1.2em}
.summary li{font-size:1.02rem}
main .lead b{color:var(--accent)}
h1{color:var(--fg)}
.mission .quote{color:var(--accent);font-size:1.25rem}



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
      a.href = e.u; k.className = 'k'; k.textContent = e.y; s.className = 's'; if (e.h) s.innerHTML = e.h; else s.textContent = e.s;
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

  // 練習問題：選んだらその場で答え合わせ
  d.querySelectorAll('.pq').forEach(pq => {
    pq.querySelectorAll('.ch').forEach(btn => btn.addEventListener('click', () => {
      if (pq.classList.contains('done')) return;
      pq.classList.add('done');
      const ok = btn.dataset.ok === '1';
      btn.classList.add(ok ? 'right' : 'wrong');
      pq.querySelectorAll('.ch').forEach(b => { b.disabled = true; if (b.dataset.ok === '1') b.classList.add('right'); });
      const r = d.createElement('p'); r.className = 'res ' + (ok ? 'ok' : 'ng');
      r.textContent = ok ? '正解！' : '惜しい！ 正しい組み立てを確認しましょう。';
      pq.insertBefore(r, pq.querySelector('.exp'));
      pq.querySelector('.exp').open = true;
    }));
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
POPULAR = ["velocity", "acceleration", "force", "energy", "power", "pressure", "voltage", "resistance", "capacitance", "spring_constant"]


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
    <div class="nav-sec"><h4>検算する</h4><ul>
      <li><a href="/"{cur("/")}>トップ</a></li>
      <li><a href="/method.html"{cur("/method.html")}>検算のやり方</a></li>
      <li><a href="/mistakes/"{cur("/mistakes/")}>よくあるミス集</a></li>
      <li><a href="/training/"{cur("/training/")}>検算トレーニング</a></li>
    </ul></div>
    <div class="nav-sec"><h4>単位を知る</h4><ul>
      <li><a href="/guide.html"{cur("/guide.html")}>単位の読み方</a></li>
      <li><a href="/about.html"{cur("/about.html")}>このサイトについて</a></li>
    </ul></div>
    <div class="nav-sec"><h4>単位辞典（分野別）</h4><ul>{cats}</ul></div>
    <div class="nav-sec"><h4>よく調べる単位</h4><div class="chips">{pop}</div></div>
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
        bc = mathify('<nav class="bc" aria-label="パンくずリスト">' + " › ".join(parts) + "</nav>")
    body = mathify(add_toc(body))
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
    <a class="txt" href="/method.html">検算のやり方</a>
    <a class="txt" href="/training/">トレーニング</a>
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
  <div class="links"><a href="/">トップ</a><a href="/method.html">検算のやり方</a><a href="/mistakes/">よくあるミス</a><a href="/training/">検算トレーニング</a><a href="/guide.html">単位の読み方</a><a href="/about.html">このサイトについて</a>{foot_links}</div>
  <p class="src">単位の定義は、国際度量衡局（BIPM）の SI パンフレット第9版と、その日本語版（産業技術総合研究所 計量標準総合センター）に基づいています。</p>
  {SITE_NAME} — 答えの単位で検算して、取れる問題を落とさない。最終更新日：{UPDATED}
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
    for m in MISTAKES:
        idx.append({"y": "ミス例", "t": m["title"].replace("【見抜けない例】", ""), "s": f'× {m["wrong"]["text"]} → ○ {m["right"]["text"]}',
                    "u": f"/mistakes/{m['id']}.html", "k": m["problem"]})
    idx.append({"y": "解説", "t": "検算のやり方", "s": "答えの単位で間違いを見つける3つの手順", "u": "/method.html", "k": "検算 次元解析 手順 確かめ"})
    idx.append({"y": "練習", "t": "検算トレーニング", "s": "単位が合う答えはどれ？", "u": "/training/", "k": "練習 問題 トレーニング"})
    for e_ in idx:
        h_ = mathify(E(e_["s"]))
        if h_ != E(e_["s"]):
            e_["h"] = h_
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


# ─────────────────────────── 練習問題（分子・分母の確認） ───────────────────────────

def _tok(u, e):
    """1つの単位を表示用に（m², (m/s) など）"""
    simple = re.fullmatch(r"[A-Za-zΩ⁰¹²³⁴⁵⁶⁷⁸⁹]+", u) is not None
    a = abs(Fr(e))
    t = u if simple else f"({u})"
    return t + (sup(a) if a != 1 else "")


def frac_str(tokens):
    """[(単位, 指数)] → 'J / C' や 'N·m / (m²·(m/s))' のような分数の形（約分しない）"""
    tokens = _merge(tokens)
    if len(tokens) == 1 and tokens[0][1] == 1:
        return tokens[0][0]
    num = [_tok(u, e) for u, e in tokens if e > 0]
    den = [_tok(u, e) for u, e in tokens if e < 0]
    n = "·".join(num) if num else "1"
    if not den:
        return n
    d = "·".join(den)
    return f"{n} / ({d})" if len(den) > 1 else f"{n} / {d}"


def is_one(u):
    """単位なし（無次元）の表示かどうか（'1/mol' は単位あり）"""
    return u == "1" or u.startswith("1（")


def _merge(tokens):
    """同じ単位が分子どうし・分母どうしにあればまとめる（分子と分母で打ち消しはしない）"""
    out = {}
    for u, e in tokens:
        e = Fr(e)
        if is_one(u) or e == 0:
            continue
        k = (u, e > 0)
        out[k] = out.get(k, 0) + e
    return [(u, e) for (u, _), e in out.items()]


def distractors(tokens):
    """分子と分母を取り違えた選択肢"""
    t = _merge(tokens)
    cands = [
        [(u, -e) for u, e in t],                         # 全部ひっくり返す
        [(u, abs(e)) for u, e in t],                     # 全部かけ算にする
        [(u, -abs(e)) for u, e in t],                    # 全部割り算にする
    ]
    for i in range(len(t)):                              # 1つだけひっくり返す
        cands.append([(u, -e if j == i else e) for j, (u, e) in enumerate(t)])
    for i in range(len(t)):                              # 1つだけ2乗にする
        cands.append([(u, 2 * e if j == i else e) for j, (u, e) in enumerate(t)])
    right = frac_str(t)
    seen, out = {right}, []
    for c in cands:
        f = frac_str(c)
        if f not in seen:
            seen.add(f)
            out.append(f)
    return right, out[:3]


def _choice_block(qid, n, question, tokens, explain):
    import hashlib
    right, wrong = distractors(tokens)
    if len(wrong) < 2:
        return ""
    opts = wrong[:]
    h = int(hashlib.md5(f"{qid}{n}".encode()).hexdigest(), 16)
    k = h % (len(opts) + 1)
    opts.insert(k, right)
    letters = "ABCD"
    lis = "".join(
        f'<li><button type="button" class="ch" data-ok="{1 if i == k else 0}">'
        f'<span class="opt">{letters[i]}</span><span class="mono">{E(o)}</span></button></li>'
        for i, o in enumerate(opts))
    return (f'<div class="pq"><p class="qt"><span class="qn">問{n}</span>{question}</p>'
            f'<ul class="opts">{lis}</ul>'
            f'<details class="exp"><summary>答えと解説</summary><p><b>正解：{letters[k]}</b>　<span class="mono ok">{E(right)}</span></p>'
            f'<p>{explain}</p></details></div>')


def _simplified(tokens, q=None):
    ud = {}
    for u, e in tokens:
        if is_one(u):
            continue
        ud = add_ud(ud, parse_display(u), Fr(e))
    if q is not None:
        ud, _ = tidy(ud, q)
    return fmt_ud(ud) if ud else "1"


def parse_display(u):
    """表示用の単位文字列（'kg·m/s²' など）を {記号: 指数} に戻す"""
    for qq in QS.values():
        if qq["unit_str"] == u:
            return dict(qq["ud"])
    raise ValueError(u)


def wq(w, u):
    if is_one(u):
        u = "単位なし"
    return f"「{E(w)}」<span class=\"mono u\">[{E(u)}]</span>"


def chain_eq(*parts):
    """'A ＝ B ＝ C' の重複を除いてつなぐ"""
    out, keys = [], []
    for p_ in parts:
        if p_ and is_one(p_):
            p_ = "1"
        k_ = re.sub(r"\s+", "", p_ or "")
        if k_ and k_ not in keys:
            keys.append(k_)
            out.append(p_)
    return " ＝ ".join(f'<span class="mono">{E(x)}</span>' for x in out)


def practice(q):
    """その量の単位を、分子・分母を意識して組み立てる3問"""
    if not q.get("words"):
        return []
    name, unit = q["name"], q["unit_str"]
    ws = [(w, wq_, Fr(e)) for w, wq_, e in q["words"]]
    probs = []

    # 問1：言葉の式をそのまま単位に
    tokens = [(QS[x]["unit_str"], e) for _, x, e in ws]
    given = "、".join(wq(w, QS[x]["unit_str"]) for w, x, _ in dict((w, (w, x, e)) for w, x, e in ws).values())
    eq, _ = word_equation(q)
    ques = f"{E(name)}は「{E(eq)}」で求められます。{given} のとき、{E(name)}の単位はどれ？"
    num = [w for w, _, e in ws if e > 0 and not is_one(QS[_]["unit_str"])]
    den = [w for w, _, e in ws if e < 0 and not is_one(QS[_]["unit_str"])]
    exp = ((f"かける量（{'・'.join(num)}）の単位が分子、" if num else "分子に来る単位はなく（1）、")
           + (f"割る量（{'・'.join(den)}）の単位が分母に来ます。" if den else "分母に来る単位はありません。")
           +
           f"まとめると {chain_eq(frac_str(tokens), _simplified(tokens, q), unit)}。")
    probs.append((ques, tokens, exp))

    # 問2：別の公式から
    alt = None
    for fid in Q_FORMS[q["id"]]:
        f = FS[fid]
        if fid == q["defined_by"]:
            continue
        for x in solvable_vars(f):
            if f["qof"][x] != q["id"]:
                continue
            terms = solve(f, x)
            if any(t[1].denominator != 1 for t in terms) or len(terms) < 2:
                continue
            alt = (f, x, terms)
            break
        if alt:
            break
    if alt:
        f, x, terms = alt
        tk = [(QS[f["qof"][v]]["unit_str"], e) for v, e in terms]
        given = "、".join(f'{E(f["sym"][v])} {wq(QS[f["qof"][v]]["name"], QS[f["qof"][v]]["unit_str"])}'
                          for v in dict.fromkeys(v for v, _ in terms))
        ques = f"{E(f['name'])} <span class=\"mono\">{E(f['expr'])}</span> を使います。{given} のとき、{E(name)} {E(f['sym'][x])} の単位はどれ？"
        exp = (f"式を {E(f['sym'][x])} について解くと <span class=\"mono\">{E(f['sym'][x])} = {E(expr_for(f, terms))}</span>。"
               f"分子・分母にそれぞれの単位を入れると {chain_eq(frac_str(tk), _simplified(tk, q), unit)}。")
        probs.append((ques, tk, exp))

    # 問3（と、問2がなければその代わり）：言葉の式を逆に使って、材料の単位を求める
    done_words = set()
    for strict in (True, False):
      for w, x, e in ws:
        if len(probs) >= 3:
            break
        if w in done_words or abs(e) != 1 or sum(1 for w2, _, _ in ws if w2 == w) > 1:
            continue
        if strict and (is_one(QS[x]["unit_str"]) or sum(1 for _, x2, _ in ws if x2 == x) > 1):
            continue
        done_words.add(w)
        others = [(w2, x2, e2) for w2, x2, e2 in ws if w2 != w]
        tk = [(unit, Fr(1) / e)] + [(QS[x2]["unit_str"], -e2 / e) for _, x2, e2 in others]
        if any(Fr(t[1]).denominator != 1 for t in tk):
            continue
        given = "、".join([wq(name, unit)] + [wq(w2, QS[x2]["unit_str"]) for w2, x2, _ in others if not is_one(QS[x2]["unit_str"])])
        ques = f"{E(name)} ＝ {E(eq)} です。{given} のとき、「{E(w)}」の単位はどれ？"
        solved = [(name, Fr(1) / e)] + [(w2, -e2 / e) for w2, _, e2 in others]
        sw = " ".join(
            (word_label(a_, b_) if i == 0 and b_ > 0 else ("1 ÷ " + word_label(a_, b_) if i == 0 else ("× " if b_ > 0 else "÷ ") + word_label(a_, b_)))
            for i, (a_, b_) in enumerate(sorted(solved, key=lambda t: t[1] < 0)))
        exp = (f"言葉の式を「{E(w)}」について解き直すと「{E(w)} ＝ {E(sw)}」。"
               f"単位を入れると {chain_eq(frac_str(tk), _simplified(tk), QS[x]['unit_str'])}。")
        probs.append((ques, tk, exp))

    if len(probs) < 3 and q["dims"] != ZERO:
        btk = [(sym, e) for sym, e in base_ud(q["dims"]).items()]
        btk = sorted(btk, key=lambda t: DISPLAY_ORDER.index(t[0]))
        route = " → ".join(QS[sid]["name"] for sid, _, _ in chain(q["id"]))
        ques = (f"{E(name)}の単位 <span class=\"mono\">[{E(unit)}]</span> を、基本単位"
                f"（<span class=\"mono\">{'・'.join(sym for sym, _ in btk)}</span>）だけで表したものはどれ？")
        exp = (f"{E(route)} の順に言葉の式をたどると、{chain_eq(unit, fmt_base(q['dims']))}。"
               "指数が正の基本単位が分子、負の基本単位が分母に来ます。")
        probs.append((ques, btk, exp))
    blocks = [_choice_block(q["id"], i + 1, qu, tk, ex) for i, (qu, tk, ex) in enumerate(probs[:3])]
    blocks = [b_ for b_ in blocks if b_]
    if not blocks:
        return []
    for i in range(len(blocks)):
        blocks[i] = re.sub(r'<span class="qn">問\d+</span>', f'<span class="qn">問{i + 1}</span>', blocks[i], count=1)
    return ["<h2>練習問題：分子と分母を見きわめる</h2>",
            "<p>問題文には単位が書いてあります。計算はしなくてかまいません。<b>どの単位が分子（上）に、どの単位が分母（下）に来るか</b>だけを考えて選んでください。</p>",
            '<div class="practice">' + "".join(blocks) + "</div>"]


# ─────────────────────────── 答えの検算（ミス例・トレーニング） ───────────────────────────

MISTAKES = json.load(open("data/mistakes.json", encoding="utf-8"))["mistakes"]
FIELD_NAMES = {"mech": "力学", "thermo": "熱・気体", "em": "電磁気", "wave": "波・光・量子"}


def _prod(prod):
    return [(sym, Fr(e)) for sym, e in prod]


def prod_dims(prod, given):
    d = ZERO
    for sym, e in _prod(prod):
        d = dimadd(d, dimscale(QS[given[sym]]["dims"], e))
    return d


def prod_units_str(prod, given):
    """[2gh] → '(m/s²)·m' のように、記号に単位を当てはめた形。√ を含む場合は √(...)"""
    pr = _prod(prod)
    half = any(e.denominator == 2 for _, e in pr)
    if half:
        inner = [(QS[given[s_]]["unit_str"], e * 2) for s_, e in pr if not is_one(QS[given[s_]]["unit_str"])]
        return f"√({frac_str(inner)})", True
    toks = [(QS[given[s_]]["unit_str"], e) for s_, e in pr if not is_one(QS[given[s_]]["unit_str"])]
    return frac_str(toks) if toks else "1", False


def prod_text(prod):
    """記号の積の表示（係数なし）: g h, m v² / r"""
    pr = _prod(prod)
    half = any(e.denominator == 2 for _, e in pr)
    def part(items):
        num = [f"{s_}{sup(e)}" for s_, e in items if e > 0]
        den = [f"{s_}{sup(-e)}" for s_, e in items if e < 0]
        n = " ".join(num) if num else "1"
        if not den:
            return n
        return f"{n}/{den[0]}" if len(den) == 1 else f"{n}/({' '.join(den)})"
    if half:
        return f"√({part([(s_, e * 2) for s_, e in pr])})"
    return part(pr)


def check_lines(expr, given, target_dims):
    """各項について [項] = 単位 = 基本単位 → ○/× を並べる"""
    lines, ok_all = [], True
    for prod in expr:
        us, half = prod_units_str(prod, given)
        d = prod_dims(prod, given)
        base = fmt_base(d) if d != ZERO else "1"
        chain_ = [us]
        if half:
            chain_.append(f"√({fmt_base(dimscale(d, 2))})")
        chain_.append(base)
        ok = d == target_dims
        ok_all &= ok
        mark = '<span class="ok">○ 一致</span>' if ok else '<span class="ng">× 不一致</span>'
        lines.append(f"[{E(prod_text(prod))}] ＝ " + " ＝ ".join(E(c) for c in dict.fromkeys(chain_)) + f"　{mark}")
    return lines, ok_all


for _m in MISTAKES:
    tq = QS[_m["target"][1]]
    for side in ("wrong", "right"):
        for prod in _m[side]["expr"]:
            for sym, _ in prod:
                if sym not in _m["given"]:
                    raise SystemExit(f"✗ ミス例 {_m['id']}: 記号 {sym} が given にない")
    _, okr = check_lines(_m["right"]["expr"], _m["given"], tq["dims"])
    _, okw = check_lines(_m["wrong"]["expr"], _m["given"], tq["dims"])
    if not okr:
        raise SystemExit(f"✗ ミス例 {_m['id']}: 正しい答えの単位が合わない")
    if okw == _m["detectable"]:
        raise SystemExit(f"✗ ミス例 {_m['id']}: 誤答が{'単位で見抜けない' if okw else '単位で見抜ける'}のに detectable={_m['detectable']}")


def given_list(given, used=None):
    items = []
    for sym, qid in given.items():
        if used is not None and sym not in used:
            continue
        u = QS[qid]["unit_str"]
        if is_one(u):
            items.append(f'<li><span class="mono">{E(sym)}</span>：単位のない数</li>')
            continue
        items.append(f'<li><span class="mono">{E(sym)}</span>：{qlink(qid)} <span class="mono u">[{E(u)}]</span></li>')
    return '<ul class="given">' + "".join(items) + "</ul>"


def mistake_card(m):
    tq = QS[m["target"][1]]
    flag = "" if m["detectable"] else '<span class="tag warn">単位では見抜けない</span>'
    return (f'<a href="/mistakes/{m["id"]}.html"><div class="t">{flag}{E(m["title"].replace("【見抜けない例】", ""))}</div>'
            f'<div class="u">× {E(m["wrong"]["text"])}　→　○ {E(m["right"]["text"])}</div></a>')


def build_mistake(m):
    tq = QS[m["target"][1]]
    tsym = m["target"][0]
    tbase = fmt_base(tq["dims"])
    wl, okw = check_lines(m["wrong"]["expr"], m["given"], tq["dims"])
    rl, _ = check_lines(m["right"]["expr"], m["given"], tq["dims"])
    title = m["title"].replace("【見抜けない例】", "")
    b = [f'<span class="tag">{E(FIELD_NAMES[m["field"]])}</span>' + ("" if m["detectable"] else '<span class="tag warn">単位では見抜けない例</span>'),
         f"<h1>{E(title)}</h1>",
         f'<div class="problem"><b>問題</b><p>{E(m["problem"])}</p></div>',
         f'<div class="answer wrong-ans"><span class="lbl">ありがちな答え</span><span class="mono">{E(m["wrong"]["text"])}</span></div>',
         "<h2>答えの単位で検算する</h2>",
         '<div class="step"><div class="st"><b>手順1</b>　求めたい量の単位を確かめる</div>'
         f'<p>求めたいのは{qlink(tq["id"])} <span class="mono">{E(tsym)}</span>。単位は <span class="mono">{E(tq["unit_str"])}</span>'
         + (f"（＝ <span class=\"mono\">{E(tbase)}</span>）" if tbase != tq["unit_str"] else "") + "。</p>"
         f'<p class="lead">使える量の単位：</p>{given_list(m["given"])}</div>',
         '<div class="step"><div class="st"><b>手順2</b>　答えの右辺に単位を当てはめる</div>'
         + ("<p>足し算の式は、<b>1つ1つの項</b>が求めたい量と同じ単位でなければいけません。</p>" if len(m["wrong"]["expr"]) > 1 else "")
         + "<p>数字の係数（2、½、π など）は単位をもたないので無視します。</p>"
         f'<div class="calc">' + "<br>".join(wl) + "</div></div>",
         '<div class="step"><div class="st"><b>手順3</b>　比べる</div>']
    if m["detectable"]:
        b.append(f'<p class="verdict ng">求めたい量は <span class="mono">{E(tbase)}</span> なのに、答えの単位が合いません。<b>この答えはどこかが間違っています。</b></p></div>')
    else:
        b.append(f'<p class="verdict warn">単位は <span class="mono">{E(tbase)}</span> で合っています。<b>でも、この答えは間違いです。</b>次元解析では見つけられない種類のミスです。</p></div>')
    b.append("<h2>どこで間違えやすいか</h2>")
    b.append(f'<p>{E(m["cause"])}</p>')
    b.append("<h2>正しい答え</h2>")
    b.append(f'<div class="answer right-ans"><span class="lbl">正しい答え</span><span class="mono">{E(m["right"]["text"])}</span></div>')
    b.append('<div class="calc">' + "<br>".join(rl) + "</div>")
    if m["detectable"]:
        b.append(f'<p>単位が <span class="mono">{E(tbase)}</span> になり、求めたい量と一致しました。</p>')
        b.append('<div class="note">単位が合っても、答えが正しいとは限りません（係数や sin・cos の間違いは見つけられません）。'
                 'ただ、<span class="key">単位が合わなければ必ず間違い</span>なので、見直す場所を絞り込めます。</div>')
    else:
        b.append(f'<div class="note"><b>どうやって見つけるか</b><br>{E(m.get("tip", ""))}<br>単位の検算は、こうした確かめ方とあわせて使いましょう。</div>')
    others = [x for x in MISTAKES if x["id"] != m["id"]][:6]
    b.append("<h2>ほかのミス例</h2><div class=\"grid mcards\">" + "".join(mistake_card(x) for x in others) + "</div>")
    b.append(f'<p><a href="/q/{tq["id"]}.html">→ {E(tq["name"])}の単位の意味を調べる</a>　<a href="/method.html">→ 検算のやり方</a></p>')
    page(f"/mistakes/{m['id']}.html", f"{title}｜答えの単位で検算",
         f"{m['problem'][:40]}… ありがちな答え {m['wrong']['text']} を、答えの単位で検算して間違いを見つける方法。",
         "\n".join(b), [("よくあるミス", "/mistakes/"), (title, None)])


def build_mistakes_index():
    det = [m for m in MISTAKES if m["detectable"]]
    und = [m for m in MISTAKES if not m["detectable"]]
    b = ["<h1>よくあるミスと、答えの単位での見つけ方</h1>",
         '<p class="lead">試験でよく見る間違いを集めました。どれも、答えが出たあとに単位を確かめるだけで見つけられます。</p>']
    for fid, fname in FIELD_NAMES.items():
        ms = [m for m in det if m["field"] == fid]
        if ms:
            b.append(f"<h2>{E(fname)}</h2><div class=\"grid mcards\">" + "".join(mistake_card(m) for m in ms) + "</div>")
    b.append("<h2>単位では見抜けないミス</h2>")
    b.append("<p>単位の検算は万能ではありません。見抜けない種類のミスも知っておきましょう。</p>")
    b.append('<div class="grid mcards">' + "".join(mistake_card(m) for m in und) + "</div>")
    page("/mistakes/", "よくあるミスと答えの単位での見つけ方",
         "物理の計算で多い間違い（√ の付け忘れ、分子と分母の取り違え、2乗の落とし）を、答えの単位で見つける例を集めました。",
         "\n".join(b), [("よくあるミス", None)])


def build_method():
    m = next(x for x in MISTAKES if x["id"] == "free_fall_speed")
    tq = QS[m["target"][1]]
    wl, _ = check_lines(m["wrong"]["expr"], m["given"], tq["dims"])
    body = f"""
<h1>答えの単位で検算する：3つの手順</h1>
<p class="lead">答えが出たら、提出する前に単位を確かめる。それだけで、取れるはずの問題を落とすミスの多くを防げます。</p>

<h2>3つの手順</h2>
<ol class="steps3">
<li><b>求めたい量の単位を確かめる</b><br>速さなら m/s、エネルギーなら J ＝ kg·m²/s²。わからなければ<a href="/#dict">単位辞典</a>で調べます。</li>
<li><b>答えの右辺に、それぞれの記号の単位を当てはめる</b><br>数字の係数（2、½、π など）は単位をもたないので無視します。</li>
<li><b>比べる</b><br>一致しなければ、<span class="key">その答えは必ず間違い</span>です。式のどこかを見直します。</li>
</ol>

<h2>例：落下の速さ</h2>
<div class="problem"><b>問題</b><p>{E(m["problem"])}</p></div>
<div class="answer wrong-ans"><span class="lbl">答え</span><span class="mono">{E(m["wrong"]["text"])}</span></div>
<p>求めたい速さ v の単位は m/s。右辺に単位を当てはめると、</p>
<div class="calc">{"<br>".join(wl)}</div>
<p>m²/s² は m/s と一致しません。v² を求めたところで止まり、√ を付け忘れていたことに気づけます。</p>

<h2>気をつけるポイント</h2>
<ul>
<li><b>足し算・引き算は、項ごとに単位がそろう</b>：x = v₀t + ½at² なら、v₀t も ½at² もどちらも m。単位の違うものは足せません。</li>
<li><b>sin・cos・指数関数・log の中身は単位をもたない</b>：sin(ωt) なら ωt に単位が残っていてはいけません。</li>
<li><b>単位が合っても、正しいとは限らない</b>：½ の付け忘れや sin と cos の取り違えは見つけられません。
<a href="/mistakes/">よくあるミス</a>の「見抜けない例」も見ておきましょう。</li>
</ul>

<h2>次にやること</h2>
<div class="grid">
<a href="/mistakes/"><div class="t"><b>よくあるミス集</b></div><div class="u">単位で見つけられる間違いの実例</div></a>
<a href="/training/"><div class="t"><b>検算トレーニング</b></div><div class="u">単位が合う答えを選ぶ練習</div></a>
<a href="/guide.html"><div class="t"><b>単位の読み方</b></div><div class="u">単位の意味を言葉から理解する</div></a>
</div>
"""
    page("/method.html", "答えの単位で検算する3つの手順", "物理の計算で出た答えが正しいかを、単位（次元解析）で確かめる3つの手順。足し算の項、sin・cos の中身、見抜けないミスまで解説。",
         body, [("検算のやり方", None)])


# 検算トレーニング：公式から「単位が合う答えはどれ？」を作る
def training_items(cat):
    import hashlib
    items = []
    for f in FS.values():
        if f["category"] != cat:
            continue
        made = 0
        for x in solvable_vars(f):
            if made >= 2:
                break
            q = QS[f["qof"][x]]
            terms = solve(f, x)
            if q["dims"] == ZERO or len(terms) < 2 or any(e.denominator != 1 for _, e in terms):
                continue
            if any(QS[f["qof"][v]]["dims"] == ZERO for v, _ in terms):
                continue
            def dims_of_terms(ts):
                d = ZERO
                for v, e in ts:
                    d = dimadd(d, dimscale(QS[f["qof"][v]]["dims"], e))
                return d
            right = expr_for(f, terms)
            cands = [[(v, -e if j == i else e) for j, (v, e) in enumerate(terms)] for i in range(len(terms))]
            if any(e > 0 for _, e in terms) and any(e < 0 for _, e in terms):
                cands.append([(v, -e) for v, e in terms])   # 分子と分母をまるごと入れかえる
            cands += [[(v, 2 * e if j == i else e) for j, (v, e) in enumerate(terms)] for i in range(len(terms))]
            wrong = []
            for c in cands:
                if dims_of_terms(c) == q["dims"]:
                    continue
                t_ = expr_for(f, c)
                if t_ != right and t_ not in wrong:
                    wrong.append(t_)
            if len(wrong) < 2:
                continue
            h = int(hashlib.md5(f"{f['id']}{x}".encode()).hexdigest(), 16)
            wrong = wrong[:3]
            k = h % (len(wrong) + 1)
            opts = wrong[:]
            opts.insert(k, right)
            used = list(dict.fromkeys(v for v, _ in terms))
            given = {f["sym"][v]: f["qof"][v] for v in used}
            tok = [(QS[f["qof"][v]]["unit_str"], e) for v, e in terms]
            exp_ = (f"求めたい{E(q['name'])}の単位は <span class=\"mono\">{E(q['unit_str'])}</span>"
                    + (f"（＝ <span class=\"mono\">{E(fmt_base(q['dims']))}</span>）" if fmt_base(q["dims"]) != q["unit_str"] else "")
                    + f"。{E(f['sym'][x])} = {E(right)} に単位を当てはめると {chain_eq(frac_str(tok), _simplified(tok, q), q['unit_str'])} で一致します。"
                    + "ほかの選択肢は単位が合いません。"
                    + f'（元の公式：{flink(f["id"])} <span class="mono">{E(f["expr"])}</span>）')
            ques = (f"求めたい量は{qlink(q['id'])} <span class=\"mono\">{E(f['sym'][x])}</span> "
                    f"<span class=\"mono u\">[{E(q['unit_str'])}]</span>。次の量を使って求めた答えのうち、<b>単位が合っているもの</b>はどれ？"
                    f"{given_list(given)}")
            items.append((ques, opts, k, exp_))
            made += 1
    return items


def choice_html(key, n, question, opts, k, explain):
    letters = "ABCD"
    lis = "".join(
        f'<li><button type="button" class="ch" data-ok="{1 if i == k else 0}">'
        f'<span class="opt">{letters[i]}</span><span class="mono">{E(o)}</span></button></li>' for i, o in enumerate(opts))
    return (f'<div class="pq"><div class="qt"><span class="qn">問{n}</span>{question}</div>'
            f'<ul class="opts">{lis}</ul>'
            f'<details class="exp"><summary>答えと解説</summary><p><b>正解：{letters[k]}</b>　<span class="mono ok">{E(opts[k])}</span></p>'
            f'<p>{explain}</p></details></div>')


TRAIN_CATS = [c for c in ["mech", "thermo", "em", "wave"] if c in CATS]


def build_training():
    counts = {}
    for cat in TRAIN_CATS:
        items = training_items(cat)
        counts[cat] = len(items)
        blocks = [choice_html(cat, i + 1, *it) for i, it in enumerate(items)]
        nav = "".join(f'<a href="/training/{c}.html"{" aria-current=\"page\"" if c == cat else ""}>{E(CATS[c]["name"])}</a>' for c in TRAIN_CATS)
        b = [f"<h1>検算トレーニング：{E(CATS[cat]['name'])}</h1>",
             '<p class="lead">計算はしなくてかまいません。答えの右辺に単位を当てはめて、<b>求めたい量と単位が合う答え</b>を選んでください。数字の係数は省いてあります。</p>',
             f'<div class="chips tnav">{nav}</div>',
             '<div class="practice">' + "".join(blocks) + "</div>"]
        page(f"/training/{cat}.html", f"検算トレーニング（{CATS[cat]['name']}）｜単位が合う答えはどれ？",
             f"{CATS[cat]['name']}の公式をもとに、答えの単位で正しい式を見分ける練習問題 {len(items)} 問。",
             "\n".join(b), [("検算トレーニング", "/training/"), (CATS[cat]["name"], None)])
    cards = "".join(f'<a href="/training/{c}.html"><div class="t">{E(CATS[c]["name"])}</div><div class="u">{counts[c]} 問</div></a>' for c in TRAIN_CATS)
    b = ["<h1>検算トレーニング</h1>",
         '<p class="lead">「単位が合う答えはどれ？」を繰り返し解いて、答えが出たら単位を確かめる習慣をつけましょう。</p>',
         '<div class="grid">' + cards + "</div>",
         '<p><a href="/method.html">→ まず検算のやり方を読む</a></p>']
    page("/training/", "検算トレーニング｜単位が合う答えはどれ？", "物理の公式をもとに、答えの単位で正しい式を見分ける練習問題。力学・熱・電磁気・波の分野別。",
         "\n".join(b), [("検算トレーニング", None)])


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

    if d != ZERO:
        rel_m = [m for m in MISTAKES if m["target"][1] == qid]
        chk = (f'<div class="checkbox"><b>検算のポイント</b><p>答えが{E(q["name"])}なら、右辺の単位は '
               f'<span class="mono ok">{E(u)}</span>' + (f"（＝ <span class=\"mono\">{E(base)}</span>）" if base != u else "")
               + ' になっているはず。ならなければ、どこかが間違っています。</p>')
        if rel_m:
            chk += "<p>関連するミス例：" + "、".join(f'<a href="/mistakes/{m["id"]}.html">{E(m["title"].replace("【見抜けない例】", ""))}</a>' for m in rel_m) + "</p>"
        chk += "</div>"
        b.append(chk)
    goals = [f"{q['name']}を言葉でどう言い表すか"]
    if q.get("words"):
        goals.append(f"その言葉を単位に置き換えると、なぜ {u} になるのか" if d != ZERO else "その言葉を単位に置き換えると、なぜ単位が消えるのか")
    elif d != ZERO:
        goals.append(f"基本単位 {u} がどのように決められているか")
    if alt_expressions(qid):
        goals.append(f"{u} のいろいろな書き方と、その根拠になる公式")
    b.append('<div class="goals"><b>このページでわかること</b><ul>' + "".join(f"<li>{E(g)}</li>" for g in goals) + "</ul></div>")

    b += words_section(q) if q["defined_by"] or d == ZERO and q.get("words") else (base_section(q) if q["ud"] else words_section(q))

    if q.get("pitfall"):
        b.append(f'<div class="note pitfall"><b>よくある誤解：{E(q["name"])}に単位はない？</b><br>{E(q["pitfall"])}</div>')
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

    b += practice(q)

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
    ff = next(x for x in MISTAKES if x["id"] == "spring_period")
    tq = QS[ff["target"][1]]
    wl, _ = check_lines(ff["wrong"]["expr"], ff["given"], tq["dims"])
    cats = []
    for c in CATS.values():
        n = sum(1 for q in QS.values() if q["category"] == c["id"])
        cats.append(f'<a href="/c/{c["id"]}.html"><div class="t">{E(c["name"])}</div>'
                    f'<div class="d">{E(c["description"])}</div><div class="n">{n} 個の量</div></a>')
    det = [m for m in MISTAKES if m["detectable"]][:6]
    ntrain = sum(len(training_items(c)) for c in TRAIN_CATS)
    b = [
        '<section class="mission">',
        '<p class="quote">「取れる問題を間違えることが、一番ダメージが大きい」</p>',
        '<p class="quote-src">— 予備校時代の数学の先生の教え</p>',
        "</section>",
        "<h1>答えが出たら、単位で検算。</h1>",
        '<p class="lead">物理の計算で出した答えが正しいかどうかを、<b>答えの単位</b>で確かめるためのサイトです。'
        "単位が合わない答えは、必ずどこかが間違っています。そのためには、求めた量の単位と、その単位の意味がわかっていることが必要です。"
        "このサイトは、その両方を身につける手助けをします。</p>",
        f'<button class="home-search" data-open-search>{ICON_SEARCH}答えの単位を調べる（例：電圧、J/K、ばね定数）</button>',
        "<h2>検算の3つの手順</h2>",
        '<ol class="steps3">'
        "<li><b>求めたい量の単位を確かめる</b><br>速さなら m/s、エネルギーなら J ＝ kg·m²/s²</li>"
        "<li><b>答えの右辺に、記号の単位を当てはめる</b><br>2、½、π などの数は単位をもたないので無視</li>"
        "<li><b>比べる</b><br><span class=\"key\">合わなければ、その答えは必ず間違い</span></li></ol>",
        '<p><a href="/method.html">→ 検算のやり方をくわしく読む</a></p>',
        "<h2>たとえば、こんなミスが見つかる</h2>",
        f'<div class="problem"><b>問題</b><p>{E(ff["problem"])}</p></div>',
        f'<div class="answer wrong-ans"><span class="lbl">ありがちな答え</span><span class="mono">{E(ff["wrong"]["text"])}</span></div>',
        f'<p>求めたい周期 T の単位は s。右辺に単位を当てはめると、</p><div class="calc">{"<br>".join(wl)}</div>',
        f'<p>s にならないので間違いだとわかります。正しくは <span class="mono ok">{E(ff["right"]["text"])}</span>。</p>',
        '<div class="grid mcards">' + "".join(mistake_card(m) for m in det) + "</div>",
        '<p><a href="/mistakes/">→ よくあるミスをすべて見る</a></p>',
        "<h2>このサイトでできること</h2>",
        '<div class="grid feat">'
        '<a href="/method.html"><div class="t">① 検算のやり方</div><div class="d">答えの単位で間違いを見つける3つの手順と、見抜けないミスの見分け方。</div></a>'
        f'<a href="/mistakes/"><div class="t">② よくあるミス集</div><div class="d">√ の付け忘れ、分子と分母の取り違えなど、{len(MISTAKES)} 個の実例。</div></a>'
        f'<a href="/training/"><div class="t">③ 検算トレーニング</div><div class="d">「単位が合う答えはどれ？」を {ntrain} 問。分野別に練習できます。</div></a>'
        f'<a href="#dict"><div class="t">④ 単位辞典</div><div class="d">{len(QS)} 個の量の単位を、意味を表す言葉から組み立てて理解します。</div></a>'
        "</div>",
        '<h2 id="dict">単位辞典：答えの単位とその意味を調べる</h2>',
        "<p>検算するには、求めた量の単位と、その単位が何を意味するかを知っている必要があります。"
        "それぞれの量のページでは、量の意味を言葉で表し、その言葉を単位に置き換えて、単位の正体を説明しています。</p>",
        '<p><a href="/guide.html">→ はじめに：単位の読み方</a></p>',
        '<div class="grid cat-cards">' + "".join(cats) + "</div>",
    ]
    page("/", "答えの単位で検算する物理サイト", "物理の計算で出した答えが正しいかを、答えの単位（次元解析）で確かめるためのサイト。検算の手順、よくあるミス集、検算トレーニング、単位辞典。", "\n".join(b))


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
<tr><td>「〜あたり」「1〜につき」</td><td class="mono">÷（分数の横線）</td><td>1秒あたりに進む距離 → m/s</td></tr>
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
<p class="lead">{E(SITE_NAME)}は、物理の計算で出した答えが正しいかどうかを、<b>答えの単位</b>で確かめられるようになるための学習サイトです。</p>

<h2>このサイトを作ったきっかけ</h2>
<p>予備校時代、数学の先生から「取れる問題を間違えることが、一番ダメージが大きい」と教わりました。
難しい問題を解けないことより、解けるはずの問題を計算ミスや式の取り違えで落とすほうが、ずっともったいない、という教えです。</p>
<p>物理では、答えが正しいかを確かめる方法のひとつに<b>次元解析</b>（答えの単位を確かめること）があります。
単位が合わない答えは、必ずどこかが間違っています。ところが、そのためには求めた量の単位と、その単位の意味がわかっていなければいけません。
このサイトは、その両方を身につける手助けをするために作りました。</p>

<h2>このサイトでできること</h2>
<ul>
<li><a href="/method.html">検算のやり方</a>：答えの単位で間違いを見つける手順</li>
<li><a href="/mistakes/">よくあるミス集</a>：単位で見つけられるミス・見つけられないミスの実例</li>
<li><a href="/training/">検算トレーニング</a>：単位が合う答えを選ぶ練習問題</li>
<li>単位辞典：{nq} 個の量について、意味を表す言葉から単位を組み立てる解説（単位はすべてSI）</li>
</ul>

<h2>内容の正しさの確かめ方</h2>
<p>ページはプログラムで作っており、公開する前に次の点を自動で検算しています。1つでも合わなければページは作られません。</p>
<ul>
<li>{nf} 個のすべての公式で、左辺と右辺の次元が一致すること</li>
<li>{len(MISTAKES)} 個のミス例で、正しい答えは単位が合い、誤った答えは単位が合わないこと（「見抜けない例」は単位が合うこと）</li>
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
    page("/about.html", "このサイトについて", f"{SITE_NAME}を作ったきっかけ、できること、内容の正しさの確かめ方、出典について。", body, [("このサイトについて", None)])

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
    build_method()
    build_mistakes_index()
    for m in MISTAKES:
        build_mistake(m)
    build_training()
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
