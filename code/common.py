# -*- coding: utf-8 -*-
"""共用基础设施 —— 两个实现都从这里取，不构成对拍的分歧点。

包含：
  · GF(2^μ) 域表：exp[] / log / mul / div         （μ = 域位宽）
  · CODES：反向 RS(73,69,8)、正向 RS(384,354,9)
  · build_g()    ：生成多项式 g(x) = ∏(x ⊕ α^i)，升幂系数
  · tx_encode()  ：步进法编码（发送序 D0..D(k-1), P0..P(2t-1)）
  · rx_syndrome()：S_j = S_j ⊗ α^j ⊕ r，j=1..2t（跑完 n 拍 ⇒ S_j = R(α^j)）
  · apply_errors() / random_case()：造用例

命名口径（与笔记一致，注意别再和本原多项式撞名）
  n  = 码字长度 = k + 2t                 k = 信息符号数
  h  = 2t = 校验符号数                    μ = 域位宽 GF(2^μ)
  位置 p（0..n-1，发送序）↔ 次数 d = n-1-p ↔ X = α^d ↔ Λ 的根 x = X^{-1} = α^{-d}
  传输序：整块降幂发送；p=0 的符号 = x^(n-1)（最先发），p=n-1 的符号 = x^0（最后发）
"""

import random

CODES = {
    "rev": dict(mu=8, poly=0x1D, fcr=1, two_t=4, k=69,
                title="反向 RS-FEC(73,69,8)   GF(2^8)  x^8+x^4+x^3+x^2+1"),
    "fwd": dict(mu=9, poly=0x11, fcr=1, two_t=30, k=354,
                title="正向 RS-FEC(384,354,9) GF(2^9)  x^9+x^4+1"),
}


def gf_table(mu, poly):
    """返回 [α^0, α^1, ..., α^(2^μ−2)]，共 2^μ−1 项。

    递推：tbl[i+1] = tbl[i] << 1；若溢出 2^μ，再异或 (1<<μ) ^ poly
    （poly 是本原多项式去掉 x^μ 后剩的低 μ 位，如 x^8+x^4+x^3+x^2+1 → 0x1D）
    """
    size = (1 << mu) - 1
    tbl = [0] * size
    tbl[0] = 1
    for i in range(size - 1):
        v = tbl[i] << 1
        if v >= (1 << mu):
            v ^= (1 << mu) ^ poly
        tbl[i + 1] = v
    return tbl


class GF:
    """GF(2^μ) 的乘/除/幂与打印。非零元素与 α^k 一一对应（α 的阶 = 2^μ−1）。"""

    def __init__(self, mu, poly):
        self.mu = mu
        self.size = (1 << mu) - 1                 # α 的阶 = 2^μ − 1
        self.exp = gf_table(mu, poly)
        self.log = {v: i for i, v in enumerate(self.exp)}

    # ---- 域运算 ----
    def mul(self, a, b):                          # α^u ⊗ α^v = α^(u+v mod 2^μ−1)
        return 0 if (a == 0 or b == 0) else self.exp[(self.log[a] + self.log[b]) % self.size]

    def div(self, a, b):                          # a / b（b ≠ 0）
        return 0 if a == 0 else self.exp[(self.log[a] - self.log[b]) % self.size]

    def pw(self, e):                              # α^e（指数自动绕回）
        return self.exp[e % self.size]

    # ---- 打印 ----
    def v(self, x, w=None):
        """单个符号：非零写 α^k(0xNN)，0 只写 0x00。"""
        w = w or (self.mu + 3) // 4
        return ("0x%0*X" % (w, 0)) if x == 0 else ("α^%d(0x%0*X)" % (self.log[x], w, x))

    def arr(self, P, tag=""):
        return "%s[%s]" % (tag, ", ".join(self.v(x) for x in P))


# -----------------------------------------------------------------------------
# 发端：g(x) 与步进法编码
# -----------------------------------------------------------------------------
def build_g(gf, two_t, fcr=1):
    """g(x) = ∏_(i=fcr..fcr+2t-1) (x ⊕ α^i)，返回升幂系数 g[j] = [x^j]g。"""
    g = [1]
    for i in range(fcr, fcr + two_t):
        r = gf.pw(i)
        ng = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            ng[j + 1] ^= c                        # 乘 x：升一次
            ng[j] ^= gf.mul(c, r)                 # 乘常数 α^i
        g = ng
    return g


def tx_encode(gf, cfg, data):
    """步进法编码，返回【发送序】码块：D0..D(k-1) 接 P0..P(2t-1)。

    与 self_code_rs_fec.py --enc 同一递推（反馈只取最高级 p[2t-1]，2t 个常量乘并行）。
    """
    two_t, k = cfg["two_t"], cfg["k"]
    g_asc = build_g(gf, two_t, cfg["fcr"])[:two_t]
    p = [0] * two_t
    dat = list(data) + [0] * two_t
    for i in range(k + two_t):
        fb = p[two_t - 1]
        w = [gf.mul(fb, gj) for gj in g_asc]
        old = p[:]
        for j in range(two_t - 1, 0, -1):
            p[j] = old[j - 1] ^ w[j]
        p[0] = dat[i] ^ w[0]
    return list(data) + p[::-1]                   # p[2t-1]..p[0] 依次是 P0..P(2t-1)


# -----------------------------------------------------------------------------
# 收端：伴随式
# -----------------------------------------------------------------------------
def rx_syndrome(gf, cfg, cw):
    """S_j = S_j ⊗ α^j ⊕ r（j = 1..2t，域运算）。跑完 n 拍 ⇒ S_j = R(α^j)。"""
    two_t = cfg["two_t"]
    S = [0] * two_t
    for r in cw:
        for j in range(1, two_t + 1):
            S[j - 1] = gf.mul(S[j - 1], gf.pw(j)) ^ r
    return S


# -----------------------------------------------------------------------------
# 位置 ↔ 次数
# -----------------------------------------------------------------------------
def n_of(cfg):
    return cfg["k"] + cfg["two_t"]


def pos_of(cfg, d):
    """次数 d → 位置 p（发送序）。"""
    return n_of(cfg) - 1 - d


def d_of(cfg, p):
    return n_of(cfg) - 1 - p


# -----------------------------------------------------------------------------
# 造用例
# -----------------------------------------------------------------------------
def apply_errors(cw, errs):
    rw = list(cw)
    for p, e in errs:
        rw[p] ^= e
    return rw


def random_case(gf, cfg, nu, seed):
    """返回 (data, errs)：随机数据 + nu 个随机位置/幅值（幅值非 0）。"""
    rng = random.Random(seed)
    n = n_of(cfg)
    data = [rng.randrange(0, 1 << gf.mu) for _ in range(cfg["k"])]
    pos = rng.sample(range(n), min(nu, n))
    evs = [rng.randrange(1, 1 << gf.mu) for _ in pos]
    return data, list(zip(pos, evs))


def make_case(gf, cfg, nu, seed, errs=None):
    """返回 (cw, rw, errs)：原始码字、接收字、错误表。errs 给定则覆盖随机。"""
    data, e_rand = random_case(gf, cfg, nu, seed)
    cw = tx_encode(gf, cfg, data)
    errs = errs if errs else e_rand
    return cw, apply_errors(cw, errs), errs


def parse_errs(s):
    """'10:0x5A,370:0xA5' → [(10,0x5A), (370,0xA5)]"""
    out = []
    for item in s.replace("，", ",").split(","):
        item = item.strip()
        if not item:
            continue
        p, v = item.split(":")
        out.append((int(p, 0), int(v, 0)))
    return out
