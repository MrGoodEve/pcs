# -*- coding: utf-8 -*-
"""① 规格版 —— 完全按用户口述/定稿编写，结构刻意贴近 RTL。

定稿算法（8 步）
    初值：B=[1], b=1, L=0, H=0, C=[1], N=0
    ①  N = N + 1
    ②  δ = ⊕_{i=0..L} S[N−i] ⊗ C[i]        （C[0]=1；S 下标 ≤ 0 记 0）
    ③  δ = 0 → ⑧
    ④  s = N − H
    ⑤  C_tmp = [0]*s ⊕ (δ/b)⊗B              （块长 = len(B)，不是 L）
        C_len = s + len(B) − 1
    ⑥  if 2L < N:  B = C, L = max((N+1)//2, C_len), b = δ, H = N
    ⑦  C = C ⊕ C_tmp                        （0 占位：从不裁剪高位 0）
    ⑧  N < 2t → ①；否则结束

Chien（位置）
    根形式 Λ̃_j = Λ_{L−j}，遍历 x = α^d（d = 0..n−1）⇒ 命中的 d 对应位置 p = n−1−d
    失败判据①：BM 的递推长度 L > t ⇒ fail（数组越界护栏 + 提前中止，不跑 Chien/Forney）
    失败判据②：根数 < deg Λ ⇒ fail

Forney（幅值，FCR=1 ⇒ 尺度因子为 1）
    Ω[j] = Σ_{i≤j} S_{j+1−i} ⊗ λ_i        （S_k = 0 当 k ≤ 0；j = 0..2t−1）
    λ′(x) = Σ_{j 奇} λ_j x^{j−1}          （char 2 的形式导数：奇数下标右移一位）
    E_i   = Ω(X_i^{−1}) / λ′(X_i^{−1})
    失败判据③：∃ j ≥ deg Λ 使 Ω[j] ≠ 0 ⇒ fail

判据④（纠正后重算 S）**已删**：与 ③ 数学等价（0/14500 反例），却要重扫整块 n 拍（见 reference/算法规格.md §4）。
① 用**递推长度 L**（数组深度/越界 + 提前中止）；②③ 用 **deg Λ**（判多项式性质）。
两者不可互替：C 从不裁剪高位 0，实测会出现 deg Λ < L（如 rev ν=3 seed 424：L=2、deg Λ=1）。

RTL 对应
    · B / C 是定长寄存器数组（B: t 级，C: t+1 级）；此实现不裁剪，保持位置
    · ② 的 L+1 项用一个常数乘加树；⑤ 的块按偏移 s 就地异或进 C
    · Chien 用「每拍每系数乘一次常数」的递推；这里为可读性直接算 α^{dj}
"""

from common import rx_syndrome, pos_of


def deg(P):
    for j in range(len(P) - 1, -1, -1):
        if P[j]:
            return j
    return 0


def peval(gf, P, x):
    """Horner 求值（RTL 里是一串乘加）。"""
    acc = 0
    for c in reversed(P):
        acc = gf.mul(acc, x) ^ c
    return acc


# -----------------------------------------------------------------------------
# BM：八步
# -----------------------------------------------------------------------------
def bm(gf, cfg, S):
    """返回 (C, rows)。C 即 Λ（升幂，C[0]=1）。rows 供逐轮打印。"""
    two_t = cfg["two_t"]
    B, b, L, H, C = [1], 1, 0, 0, [1]
    rows = []
    for N in range(1, two_t + 1):
        # ②  δ = Σ_{i=0..L} S[N−i] ⊗ C[i]
        d = 0
        for i in range(0, L + 1):
            k = N - i                                  # 用第 k 个伴随式（1-based）
            if 1 <= k <= two_t and i < len(C):
                d ^= gf.mul(C[i], S[k - 1])
        row = dict(N=N, L_in=L, B_in=list(B), b_in=b, H=H, C_in=list(C), delta=d)
        # ③
        if d == 0:
            row.update(action="δ=0 → ⑧", L_out=L, C_out=list(C))
            rows.append(row)
            continue
        # ④
        s = N - H
        # ⑤
        coef = gf.div(d, b)
        blk = [gf.mul(coef, v) for v in B]             # 块长 = len(B)
        C_len = s + len(blk) - 1
        # ⑥
        if 2 * L < N:
            B = list(C)
            L = max((N + 1) // 2, C_len)
            b = d
            H = N
            row["grow"] = True
        # ⑦  就地异或（0 占位：需要多长补多长，从不裁剪）
        need = s + len(blk)
        if len(C) < need:
            C = C + [0] * (need - len(C))
        for j, v in enumerate(blk):
            C[s + j] ^= v
        row.update(action="修正", s=s, coef=coef, blk=blk, C_len=C_len,
                   L_out=L, B_out=list(B), b_out=b, H_out=H, C_out=list(C))
        rows.append(row)
    return C, rows


# -----------------------------------------------------------------------------
# Chien：根形式遍历
# -----------------------------------------------------------------------------
def chien(gf, cfg, Lam):
    """返回 (ds, L)：ds = 命中的次数列表；位置 p = n−1−d。"""
    n = cfg["k"] + cfg["two_t"]
    L = deg(Lam)
    Lt = [Lam[L - j] for j in range(L + 1)]            # 根形式 Λ̃_j = Λ_{L−j}
    ds = []
    for d in range(n):
        acc = 0
        for j, c in enumerate(Lt):
            acc ^= gf.mul(c, gf.pw((d * j) % gf.size))  # x^j = (α^d)^j
        if acc == 0:
            ds.append(d)
    return ds, L


# -----------------------------------------------------------------------------
# Forney：Ω / λ′ / 幅值
# -----------------------------------------------------------------------------
def omega(gf, cfg, Lam, S):
    """Ω[j] = Σ_{i≤j} S_{j+1−i} ⊗ λ_i（S_k = 0 当 k ≤ 0），j = 0..2t−1。"""
    two_t = cfg["two_t"]
    Om = []
    for j in range(two_t):
        acc = 0
        for i in range(0, min(j, len(Lam) - 1) + 1):
            k = j + 1 - i
            if 1 <= k <= two_t:
                acc ^= gf.mul(Lam[i], S[k - 1])
        Om.append(acc)
    return Om


def lam_deriv(Lam):
    """λ′(x) = Σ_{j 奇} λ_j x^{j−1}：挑奇数下标、整体右移一位（char 2 的形式导数）。"""
    return [Lam[j + 1] if (j + 1) % 2 == 1 else 0 for j in range(len(Lam) - 1)]


def forney(gf, Om, dv, ds):
    """返回 [(d, x, 分子, 分母, E_i)]。"""
    out = []
    for d in ds:
        x = gf.pw((-d) % gf.size)                       # X^{-1} = α^{−d}
        num, den = peval(gf, Om, x), peval(gf, dv, x)
        e = 0 if num == 0 else gf.div(num, den)
        out.append((d, x, num, den, e))
    return out


# -----------------------------------------------------------------------------
# 串联 + 失败判据
# -----------------------------------------------------------------------------
def decode(gf, cfg, rw):
    """返回 dict：status ∈ {OK, FAIL①, FAIL②, FAIL③} 及全部中间量。

    判据集合（定稿）：① L ≤ t ② 根数 < deg Λ ③ ∃ j ≥ deg Λ 使 Ω[j] ≠ 0。
    ④（纠正后重算 S）已删 —— 与 ③ 等价且要重扫整块；端到端自检留给参考版/系统级 CRC。
    """
    t = cfg["two_t"] // 2
    S = rx_syndrome(gf, cfg, rw)
    Lam, rows = bm(gf, cfg, S)

    # 判据①：BM 递推长度 L ≤ t（写高次系数前的越界护栏；这里当提前中止用，省掉 Chien/Forney）
    L_rec = rows[-1]["L_out"]
    if L_rec > t:
        return dict(S=S, Lam=Lam, rows=rows, ds=[], L=deg(Lam), L_rec=L_rec, status="FAIL①")

    ds, L = chien(gf, cfg, Lam)
    out = dict(S=S, Lam=Lam, rows=rows, ds=ds, L=L, L_rec=L_rec)

    # 判据②：根数 < deg Λ
    if len(ds) < L:
        out.update(pos=[pos_of(cfg, d) for d in ds], status="FAIL②")
        return out

    # Ω + 判据③：∃ j ≥ deg Λ 使 Ω[j] ≠ 0
    Om = omega(gf, cfg, Lam, S)
    out["Omega"] = Om
    over = [j for j in range(L, len(Om)) if Om[j] != 0]
    pos = [pos_of(cfg, d) for d in ds]
    if over:
        out.update(pos=pos, status="FAIL③", over=over)
        return out

    # Forney + 纠正（④ 已删：不再重算 S）
    dv = lam_deriv(Lam)
    fs = forney(gf, Om, dv, ds)
    Es = [f[4] for f in fs]
    fixed = list(rw)
    for p, e in zip(pos, Es):
        fixed[p] ^= e
    out.update(dv=dv, fs=fs, Es=Es, pos=pos, fixed=fixed, status="OK")
    return out
