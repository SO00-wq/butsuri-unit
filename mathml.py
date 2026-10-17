"""
本文中の式・単位を、ノートに書くような数式表記（MathML）に変換する

  ・a/b      → 分数（横線で上下に書く）
  ・√(…)     → 根号が中身全体にかかる
  ・k_B, v₀  → 下付き文字
  ・½        → 分数の 1/2
  ・m², s⁻¹  → 上付き文字

HTML のテキスト部分だけを見て、「/ √ _ ½」のどれかを含む式のかたまりを変換する。
うまく読めないかたまりは、元の文字のまま残す（ページが壊れないように）。
"""

import html
import re

LETTERS = "A-Za-zΩΔΣΦΨΛΘΓΠαβγδεζηθικλμνξπρστυφχψωℏ′'"
SUPS = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "−", "ᐟ": "/"}
SUBS = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4"}
RUN = re.compile(r"[" + LETTERS + r"0-9½·×÷=＝+\-−/()√_⁰¹²³⁴⁵⁶⁷⁸⁹⁻ᐟ₀₁₂₃₄ ]+")
TRIGGER = re.compile(r"[/√_½ᐟ]")


class ParseError(Exception):
    pass


def tokenize(s):
    toks, i = [], 0
    while i < len(s):
        c = s[i]
        if c == " ":
            i += 1
        elif c in "0123456789":
            j = i
            while j < len(s) and s[j] in "0123456789":
                j += 1
            toks.append(("num", s[i:j])); i = j
        elif re.match(f"[{LETTERS}]", c):
            j = i
            while j < len(s) and re.match(f"[{LETTERS}]", s[j]):
                j += 1
            toks.append(("id", s[i:j])); i = j
        elif c == "_":
            j = i + 1
            while j < len(s) and re.match(f"[{LETTERS}0-9]", s[j]):
                j += 1
            if j == i + 1:
                raise ParseError("empty subscript")
            toks.append(("sub", s[i + 1:j])); i = j
        elif c in SUBS:
            j = i
            while j < len(s) and s[j] in SUBS:
                j += 1
            toks.append(("sub", "".join(SUBS[x] for x in s[i:j]))); i = j
        elif c in SUPS:
            j = i
            while j < len(s) and s[j] in SUPS:
                j += 1
            toks.append(("sup", "".join(SUPS[x] for x in s[i:j]))); i = j
        elif c in "=＝+-−":
            toks.append(("rel", {"＝": "=", "-": "−"}.get(c, c))); i += 1
        elif c in "·×÷":
            toks.append(("mul", c)); i += 1
        elif c in "/()√½":
            toks.append((c, c)); i += 1
        else:
            raise ParseError(c)
    return toks


class Node:
    def __init__(self, ml, paren=False, group=False):
        self.ml = ml          # 括弧を除いた中身
        self.paren = paren    # 括弧を表示するか
        self.group = group    # もともと括弧でくくられていたか（指数がつくときは括弧を戻す）

    def render(self):
        return f"<mo>(</mo>{self.ml}<mo>)</mo>" if self.paren else self.ml

    def bare(self):
        return self.ml

    def with_paren(self):
        """指数をつけるときの表示：もとが括弧つきなら必ず括弧を付ける"""
        return f"<mo>(</mo>{self.ml}<mo>)</mo>" if (self.paren or self.group) else self.ml


def esc(t):
    return html.escape(t, quote=False)


class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek(); self.i += 1
        return tok

    def expr(self, closing=None):
        out = []
        while True:
            k, v = self.peek()
            if k is None or (closing and k == ")"):
                break
            if k == "rel":
                self.take(); out.append(f"<mo>{esc(v)}</mo>")
                continue
            out.append(self.product())
        if not out:
            raise ParseError("empty")
        return "".join(out)

    def product(self):
        parts = []        # 分子になりうる部分（直前の / までの積）
        while True:
            k, v = self.peek()
            if k in (None, "rel", ")"):
                break
            if k == "mul":
                self.take(); parts.append(f"<mo>{esc(v)}</mo>")
                continue
            if k == "/":
                self.take()
                if not parts:
                    raise ParseError("no numerator")
                num = parts_node(parts)
                den = self.factor()
                parts = [f"<mfrac><mrow>{num}</mrow><mrow>{den.bare()}</mrow></mfrac>"]
                continue
            parts.append(self.factor().render())
        if not parts:
            raise ParseError("empty product")
        return "".join(parts)

    def factor(self):
        node = self.atom()
        while True:
            k, v = self.peek()
            if k == "sup" and "/" in v:
                # 分数の指数は根号で書く： x^(1/2) → √x、x^(3/2) → √(x³)、x^(-1/2) → 1/√x、x^(1/4) → 4乗根
                self.take()
                p_, q_ = v.split("/")
                neg = p_.startswith("−")
                p_ = p_.lstrip("−")
                inner = node.bare() if p_ == "1" else f"<msup><mrow>{node.with_paren()}</mrow><mn>{esc(p_)}</mn></msup>"
                rt = f"<msqrt>{inner}</msqrt>" if q_ == "2" else f"<mroot><mrow>{inner}</mrow><mn>{esc(q_)}</mn></mroot>"
                node = Node(f"<mfrac><mn>1</mn><mrow>{rt}</mrow></mfrac>" if neg else rt)
            elif k == "sup":
                self.take()
                node = Node(f"<msup><mrow>{node.with_paren()}</mrow><mn>{esc(v)}</mn></msup>")
            elif k == "sub":
                self.take()
                node = Node(f"<msub><mrow>{node.render()}</mrow><mi mathvariant=\"normal\">{esc(v)}</mi></msub>")
            else:
                return node

    def atom(self):
        k, v = self.take()
        if k == "num":
            return Node(f"<mn>{esc(v)}</mn>")
        if k == "id":
            return Node(f"<mi mathvariant=\"normal\">{esc(v)}</mi>")
        if k == "½":
            return Node("<mfrac><mn>1</mn><mn>2</mn></mfrac>")
        if k == "(":
            inner = self.expr(closing=")")
            if self.take()[0] != ")":
                raise ParseError("no )")
            return Node(inner, paren=not is_single(inner, "mfrac"), group=True)
        if k == "√":
            n = self.factor()
            return Node(f"<msqrt>{n.bare()}</msqrt>")
        raise ParseError(f"unexpected {k}")


def is_single(ml, tag):
    """ml 全体が1つの <tag>…</tag> だけでできているか"""
    if not (ml.startswith(f"<{tag}>") and ml.endswith(f"</{tag}>")):
        return False
    depth, i = 0, 0
    for m in re.finditer(rf"<(/?){tag}>", ml):
        depth += -1 if m.group(1) else 1
        if depth == 0 and m.end() != len(ml):
            return False
    return True


def parts_node(parts):
    """分子が括弧つきの1つのグループだけなら、括弧を外す"""
    s = "".join(parts)
    m = re.fullmatch(r"<mo>\(</mo>(.*)<mo>\)</mo>", s)
    if m and m.group(1).count("<mo>(</mo>") == m.group(1).count("<mo>)</mo>"):
        return m.group(1)
    return s


def to_mathml(text):
    toks = tokenize(text)
    p = Parser(toks)
    body = p.expr()
    if p.i != len(toks):
        raise ParseError("trailing")
    return f'<math><mstyle displaystyle="true">{body}</mstyle></math>'


def convert_text(text, in_math=False):
    """テキスト1かたまりの中の式の部分を MathML に置き換える（text は HTML エスケープ済み）。
    in_math=True（式・単位の欄の中）なら、/ などがなくても英字・数字のかたまりはすべて数式にする"""
    raw = html.unescape(text)
    out, pos = [], 0
    for m in RUN.finditer(raw):
        seg = m.group(0)
        core = seg.strip()
        if not core:
            continue
        if not TRIGGER.search(core) and not (in_math and re.search(f"[{LETTERS}0-9]", core)):
            continue
        lead = seg[:len(seg) - len(seg.lstrip())]
        trail = seg[len(seg.rstrip()):]
        while core.count("(") < core.count(")") and core.endswith(")"):
            core = core[:-1]; trail = ")" + trail
        while core.count("(") > core.count(")") and core.startswith("("):
            core = core[1:]; lead = lead + "("
        try:
            ml = to_mathml(core)
        except (ParseError, IndexError):
            continue
        out.append(esc(raw[pos:m.start()]) + esc(lead) + ml + esc(trail))
        pos = m.end()
    if pos == 0:
        return text
    out.append(esc(raw[pos:]))
    return "".join(out)


TAG = re.compile(r"(<[^>]+>)")


MATH_CLASSES = re.compile(r'class="[^"]*\b(mono|calc|big|u)\b')
VOID = {"br", "img", "input", "meta", "link", "hr", "source", "wbr"}


def mathify(html_text):
    """HTML のテキスト部分だけを変換する（タグの属性・script・style などは触らない）。
    class に mono / calc / big / u を含む要素の中は「式の欄」として、すべての英字・数字を数式にする"""
    parts = TAG.split(html_text)
    stack = []          # (タグ名, 式の欄か)
    skip = 0
    for i, p_ in enumerate(parts):
        if p_.startswith("<"):
            m = re.match(r"<(/?)([a-zA-Z0-9]+)", p_)
            if not m:
                continue
            closing, name = m.group(1) == "/", m.group(2).lower()
            if name in ("script", "style", "textarea", "title", "math"):
                skip += -1 if closing else 1
                skip = max(skip, 0)
                continue
            if name in VOID or p_.endswith("/>"):
                continue
            if closing:
                while stack:
                    n_, _ = stack.pop()
                    if n_ == name:
                        break
            else:
                inherited = bool(stack and stack[-1][1])
                stack.append((name, inherited or bool(MATH_CLASSES.search(p_))))
            continue
        if skip or not p_.strip():
            continue
        parts[i] = convert_text(p_, in_math=bool(stack and stack[-1][1]))
    return "".join(parts)


if __name__ == "__main__":
    for t in ["kg·m²/(A·s³)", "T = 2π√(m/k)", "v = √(2qV/m)", "R = N_A k_B", "(N·m²/kg²)·kg² / m²",
              "x = v₀t + ½at²", "√((N/m) / kg) ＝ √(1/s²) ＝ 1/s", "E = (3/2) k_B T", "1 / (J·C)", "(m/s) / s"]:
        print(t, "→", to_mathml(t)[:160])
