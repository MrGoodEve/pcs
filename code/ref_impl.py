# -*- coding: utf-8 -*-
"""② 参考实现 —— 独立路线，专门用来和规格版对拍。

刻意与规格版走不同的路，任何一处「只有一种写法才成立」的错都藏不住：

    | 步骤   | 规格版（spec_impl）              | 参考版（本文件）                    |
    |--------|----------------------------------|-------------------------------------|
    | BM     | 用户的 8 步（B/b/L/H/C，C_len）  | 教科书 BM（C/B + 年龄 age，L←N−L）  |
    | Chien  | 根形式 Λ̃_j=Λ_{L−j}，x=α^d       | 直接代入 Λ(α^{−e})，用折返指数      |
    | 幅值   | Forney（Ω/λ′）                   | 解线性方程组（Vandermonde + 高斯消元）|

    | 失败判据 | 规格版 | 参考版 |
    |----------|--------|--------|
    | ② 根数 < deg Λ | ✓ | ✓ |
    | ③ ∃j≥L, Ω[j]≠0 | ✓ | —（Ω 属规格版口径，不引入以保持独立）|
    | ④ 纠正后 S 全 0 | ✓ | ✓ |

经典 BM（教科书形式）
    C = 1, B = 1, L = 0, age = 1, b = 1
    for N = 1..2t:
        d = Σ_{i=0..L} S[N−i]·C[i]
        if d == 0:  age += 1; continue
        T = C
        C = C ⊕ (d/b)·x^age·B
        if 2L ≤ N−1:  L = N − L; B = T; b = d; age = 1
        else:         age += 1
"""

from common import rx_syndrome, pos_of


def deg(P):
    for j in range(len(P) - 1, -1, -1):
        if P[j]:
            return j
    return 0


def peval(gf, P, x):
    acc = 0
    for c in reversed(P):
        acc = gf.mul(acc, x) ^ c
    return acc


# -----------------------------------------------------------------------------
# BM：教科书形式
# -----------------------------------------------------------------------------
def bm(gf, cfg, S):
    two_t = cfg["two_t"]
    C, B, L, age, b = [1], [1], 0, 1, 1
    for N in range(1, two_t + 1):
        d = 0
        for i in range(0, L + 1):
            k = N - i
            if 1 <= k <= two_t and i < len(C):
                d ^= gf.mul(C[i], S[k - 1])
        if d == 0:
            age += 1
            continue
        T = list(C)
        coef = gf.div(d, b)
        need = age + len(B)
        if len(C) < need:
            C = C + [0] * (need - len(C))
        for j, v in enumerate(B):
            C[age + j] ^= gf.mul(coef, v)
        if 2 * L <= N - 1:
            L = N - L
            B, b, age = T, d, 1
        else:
            age += 1
    return C


# -----------------------------------------------------------------------------
# Chien：直接代入 Λ(α^{−e})（折返指数 α^{2^μ−e}）
# -----------------------------------------------------------------------------
def chien(gf, cfg, Lam):
    n = cfg["k"] + cfg["two_t"]
    es = []
    for e in range(n):
        if peval(gf, Lam, gf.pw((-e) % gf.size)) == 0:
            es.append(e)
    return es


# -----------------------------------------------------------------------------
# 幅值：解 Σ_i E_i·X_i^j = S_j（j = 1..ν），X_i = α^{d_i}
# 高斯消元，与 Forney 完全无关的一条路
# -----------------------------------------------------------------------------
def mags_gauss(gf, S, ds):
    nu = len(ds)
    M = []
    for j in range(nu):                                   # 第 j 行对应 S_{j+1}
        row = [gf.pw((d * (j + 1)) % gf.size) for d in ds]  # 系数 X_i^{j+1}
        row.append(S[j])
        M.append(row)
    for col in range(nu):
        piv = None
        for r in range(col, nu):
            if M[r][col]:
                piv = r
                break
        if piv is None:
            return None                                   # 奇异（根重复时才可能）
        M[col], M[piv] = M[piv], M[col]
        inv = gf.div(1, M[col][col])
        M[col] = [gf.mul(inv, v) for v in M[col]]
        for r in range(nu):
            if r != col and M[r][col]:
                f = M[r][col]
                M[r] = [a ^ gf.mul(f, b) for a, b in zip(M[r], M[col])]
    return [M[i][nu] for i in range(nu)]


# -----------------------------------------------------------------------------
# 串联 + 判据②④
# -----------------------------------------------------------------------------
def decode(gf, cfg, rw):
    S = rx_syndrome(gf, cfg, rw)
    Lam = bm(gf, cfg, S)
    L = deg(Lam)
    es = chien(gf, cfg, Lam)
    out = dict(S=S, Lam=Lam, L=L, ds=es)

    if len(es) != L:                                      # 判据②（参考版同样用 < 的等价形式）
        out["status"] = "FAIL②"
        return out

    Es = mags_gauss(gf, S, es)
    if Es is None:
        out["status"] = "FAIL②"
        return out
    pos = [pos_of(cfg, d) for d in es]
    fixed = list(rw)
    for p, e in zip(pos, Es):
        fixed[p] ^= e

    S2 = rx_syndrome(gf, cfg, fixed)
    out.update(Es=Es, pos=pos, fixed=fixed, S2=S2)
    out["status"] = "OK" if all(v == 0 for v in S2) else "FAIL④"
    return out
