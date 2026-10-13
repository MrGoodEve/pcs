#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrambler_parallel.py —— 并行加扰的常数掩码生成（一拍处理 P 个比特）

背景（为什么要并行）
------------------
数据是**并行**进出的（例如一拍 40 bit）；顺序逐比特加扰时序不够，必须在一拍内同时得到
P 个扰码比特，并把寄存器一次推进 P 拍。加扰器是 GF(2) 线性系统，所以这两件事都能写成
**常数掩码 + 异或树**：

    S_{n+P} = T^P · S_n                              （状态一次跳 P 拍）
    scr_i   = Scr_{n+i}[0] = (T^i · S_n) 的第 0 位     （本拍第 i 个扰码比特，i = 0..P-1）
    A_i     = scr_i ^ D_i                            （公式 A.5：A_n = Scr_n[0] ^ D_n）

本脚本把 T^P 与 T^i 的每一行算成 33 bit 常数掩码，并**用逐拍实现交叉验证**（同一份 `step()`），
可直接照抄进 RTL（见 --verilog）。

口径
----
* 寄存器 33 级 Scr[0..32]，状态用 33 bit 整数表示（bit j = Scr[j]），低 33 位有效。
* 每拍单步：`new Scr[0] = Scr[a] ^ Scr[b]`，其余级朝 Scr[32] 方向搬一格（图 A.15 / A.21 的箭头方向）。
  默认抽头 a=12, b=32（即 Scr0 = Scr12 ^ Scr32）。
* 输出抽头 Scr[0]（公式 A.5）；Scr[32] 只参与反馈。
* 数据位序：D[0] 是最先上线的比特 ⇒ 对应 scr[0]；A[i] = scr[i] ^ D[i]。
* [待核] 抽头下标与公式指数的对应：默认接线对应 x^33+x^20+1；若要 (A.4) x^33+x^13+1 用 --taps 19,32。

用法
----
    python scrambler_parallel.py                       # P=40，抽头 12/32：打印掩码 + 验证 + 示例
    python scrambler_parallel.py --width 32            # 改并行位宽
    python scrambler_parallel.py --verilog             # 额外输出可直接用的 Verilog 片段
    python scrambler_parallel.py --init 0x1FFFFFFFF    # 指定示例用的初值
"""

from __future__ import annotations

import argparse
import random

from scrambler import MASK, WIDTH, bit, step   # 复用逐拍实现的唯一来源

IDENTITY = [1 << j for j in range(WIDTH)]


def advance_vector(vec: int, taps, steps: int) -> int:
    """把一个 33 bit 状态（或任意线性组合）推进 steps 拍。"""
    reg = vec & MASK
    for _ in range(steps):
        reg, _, _ = step(reg, taps)
    return reg


def row_masks(steps: int, taps) -> list[int]:
    """返回 T^steps 的 33 行掩码：row[j] 的 bit k = 1 表示 new Scr[j] 依赖 old Scr[k]。"""
    rows = [0] * WIDTH
    for k in range(WIDTH):                       # 对每个基向量求像，填到各行的第 k 位
        img = advance_vector(IDENTITY[k], taps, steps)
        for j in range(WIDTH):
            if bit(img, j):
                rows[j] |= 1 << k
    return rows


def apply_rows(rows: list[int], state: int) -> int:
    """用掩码（常数 XOR 网）一次推进：new Scr[j] = ^(S & rows[j])。"""
    out = 0
    for j, m in enumerate(rows):
        if bin(m & state).count("1") & 1:
            out |= 1 << j
    return out


def parity(mask: int, state: int) -> int:
    return bin(mask & state).count("1") & 1


# ---------------------------------------------------------------- 滚动窗口算法（任意 P）
# 窗口 W 为“最新位在前”：W[i] = b[n-1-i]（i=0 最新；边界：W[0] 是上一拍最后一个比特，不是本拍第一个比特）。
# 输出 sn[k] = b[n+P-1-k]（同样最新位在前）＝本拍的 P 个扰码比特，且 sn 直接就是下一拍的窗口内容。
#
# 一般式（由“新比特 = 13 拍前 ^ 33 拍前”推出，k 从 P-1 递减到 0 算；实测 P=8/16/32/33/40/41/64 全对）：
#     sn[k] = (k <= P-14 ? sn[k+13] : W[k+13-P]) ^ (k <= P-34 ? sn[k+33] : W[k+33-P])
#   P=40：k>=27 两项都在窗口内（W[k-27] ^ W[k-7]）；7<=k<27 第一项引用本拍 sn；k<7 两项都引用本拍 sn
#   P=32：k>=19 两项都在窗口内（W[k-19] ^ W[k-7]）；k<=18 第一项引用本拍 sn（第二项恒为窗口位）
# 注意：这不是组合环（只引用更高下标的 sn，按 k 递减展开就是纯前馈），但确实带来“本拍内先后依赖”，
#       深度最多 4 级。若 RTL 要求 P 个输出彼此独立、纯从寄存器出，请用下面的 state_only 展开式。
def window_next(W, P: int = 40):
    sn = [0] * P
    for k in range(P - 1, -1, -1):
        t1 = sn[k + 13] if k <= P - 14 else W[k + 13 - P]
        t2 = sn[k + 33] if k <= P - 34 else W[k + 33 - P]
        sn[k] = t1 ^ t2
    return sn


# ------------------------------------------------- 无本拍依赖的状态-only 展开式（推荐给 RTL）
# 把每个输出位完全展开成“只依赖旧寄存器”的异或（等价于对本拍各位反解递推）：
#     b[n+i] = XOR_{age in ages_i} b[n-age]，ages_i ⊂ {0..32}  ⇒ 恰好只用 33 级寄存器
def expand_ages(d: int, lags=(13, 33), memo: dict | None = None) -> frozenset:
    """b[n+d] 展开成过去位年龄集合（GF(2)：同项相消）。d<=0 即过去位，年龄 = -d。"""
    if memo is None:
        memo = expand_ages.memo = {} if getattr(expand_ages, "memo", None) is None else expand_ages.memo
    key = (d, lags)
    if key in memo:
        return memo[key]
    if d <= 0:
        res = frozenset({-d})
    else:
        res = frozenset(expand_ages(d - lags[0], lags, memo) ^ expand_ages(d - lags[1], lags, memo))
    memo[key] = res
    return res


def state_only_rows(P: int, taps) -> list[frozenset]:
    """返回 P 个输出位的年龄集合（只用旧状态，无本拍依赖）。

    单步 new Scr[0] = Scr[a] ^ Scr[b] ⇒ Scr_j = b[n-j] 代回得 b[u] = b[u-1-a] ^ b[u-1-b]，
    即滞后 lags = (a+1, b+1)；默认 (12,32) -> (13,33)。
    """
    lags = (taps[0] + 1, taps[1] + 1)
    return [expand_ages(i, lags) for i in range(P)]


def window_check(init: int, taps, P: int, trials: int = 200) -> tuple[int, int, int]:
    """把窗口法与掩码法、以及序列真值三方对比。返回 (组数, 与掩码法不一致数, 与真值不一致数)。"""
    import random
    out_masks = [row_masks(i, taps)[0] for i in range(P)]
    random.seed(20261013)
    tot = bad_mask = bad_truth = 0
    for _ in range(trials):
        reg, seq = (random.getrandbits(WIDTH) & MASK) or 1, []
        r = reg
        for _ in range(WIDTH + P + 120):
            seq.append(bit(r, 0)); r, _, _ = step(r, taps)
        for n in range(40, 100):
            state = sum(seq[n - j] << j for j in range(WIDTH))       # Scr_n[j] = b[n-j]
            W = [seq[n - 1 - i] for i in range(max(P, 40))]           # 最新位 = b[n-1]
            sn = window_next(W, P)                                   # sn[k] = b[n+P-1-k]
            ref = [parity(m, state) for m in out_masks][::-1]        # 掩码法倒序对齐
            truth = [seq[n + i] for i in range(P)][::-1]
            tot += 1
            if sn != ref:
                bad_mask += 1
            if sn != truth:
                bad_truth += 1
    return tot, bad_mask, bad_truth


def state_only_check(init: int, taps, widths=(8, 16, 32, 33, 40, 41, 64)) -> tuple[int, int]:
    """核验“状态-only 展开式”：每个输出位 = 旧寄存器若干位的异或（无本拍依赖）。"""
    tot = bad = 0
    for P in widths:
        rows = state_only_rows(P, taps)
        r, seq = init, []
        for _ in range(WIDTH + 100 + max(widths) + 10):
            seq.append(bit(r, 0)); r, _, _ = step(r, taps)
        for n in range(40, 100):
            for i, ages in enumerate(rows):
                val = 0
                for age in ages:
                    val ^= seq[n - age]
                tot += 1
                if val != seq[n + i]:
                    bad += 1
    return tot, bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="并行加扰常数掩码生成（一拍 P 比特）")
    ap.add_argument("--width", type=int, default=40, help="并行位宽 P（默认 40）")
    ap.add_argument("--taps", default="12,32", help="反馈抽头（默认 12,32）")
    ap.add_argument("--init", default="0x1FFFFFFFF", help="示例/验证用初值")
    ap.add_argument("--verilog", action="store_true", help="额外打印 Verilog 片段")
    ap.add_argument("--window", action="store_true", help="额外演示并校验“滚动窗口法”（任意 P；每拍 P 个 XOR2，但有本拍内依赖）")
    ap.add_argument("--expand", action="store_true", help="额外打印“状态-only 展开式”（无本拍依赖，纯从 33 级寄存器出）")
    args = ap.parse_args(argv)

    taps = tuple(int(x) for x in args.taps.replace(" ", "").split(","))
    P = args.width
    init = int(args.init, 0) & MASK

    rows_P = row_masks(P, taps)                       # 状态跳 P 拍
    out_masks = [row_masks(i, taps)[0] for i in range(P)]   # 本拍第 i 个扰码比特 = (T^i S)[0]

    print("=" * 78)
    print("并行加扰掩码（一拍 %d 个比特）" % P)
    print("  寄存器      : 33 级 Scr[0..32]（状态按 33 bit 整数，bit j = Scr[j]）")
    print("  单步        : new Scr[0] = Scr[%d] ^ Scr[%d]，其余级朝 Scr[32] 方向搬一格" % taps)
    print("  状态一次跳 %2d 拍: S_{n+%d} = T^%d · S_n（常数 XOR 网）" % (P, P, P))
    print("  本拍扰码位  : scr[i] = Scr_{n+i}[0]，i = 0..%d（仍是常数 XOR 网）" % (P - 1))
    print("  数据位序    : D[0] 最先上线 -> A[i] = scr[i] ^ D[i]")
    print("=" * 78)

    print("\n[1] 本拍 %d 个扰码比特的掩码（scr[i] = ^(S & mask[i])）" % P)
    for i, m in enumerate(out_masks):
        print("   scr[%2d] = ^(S & 33'h%09X)     依赖的寄存器位: %s" % (
            i, m, ",".join("Scr[%d]" % j for j in range(WIDTH) if bit(m, j)) or "无（恒 0）"))

    print("\n[2] 状态一次跳 %d 拍的掩码（下拍状态 S' = T^%d · S）" % (P, P))
    for j, m in enumerate(rows_P):
        print("   S'[%2d] = ^(S & 33'h%09X)      项数 %d" % (j, m, bin(m).count("1")))

    print("\n[3] 交叉验证：并行计算 == 逐拍计算")
    random.seed(12345)
    ok_state = ok_scr = True
    for _ in range(200):
        s = random.getrandbits(WIDTH) & MASK
        ref = s
        ref_scr = []
        for i in range(P):
            ref_scr.append(bit(ref, 0))
            ref, _, _ = step(ref, taps)
        if apply_rows(rows_P, s) != ref:
            ok_state = False
        if [parity(m, s) for m in out_masks] != ref_scr:
            ok_scr = False
    print("   200 组随机状态：状态跳跃一致 = %s ；%d 个扰码位一致 = %s" % (ok_state, P, ok_scr))

    print("\n[4] 例子（你问的那件事）：由 n=1 的状态直接得到 n=41 的状态")
    s1, _, _ = step(init, taps)                        # n=1
    s41_par = apply_rows(rows_P, s1)                   # 一次跳跃
    ref = s1
    for _ in range(P):
        ref, _, _ = step(ref, taps)                    # 逐拍 40 次
    print("   n=1  S = 0x%09X" % s1)
    print("   并行  -> S(41) = 0x%09X" % s41_par)
    print("   逐拍  -> S(41) = 0x%09X    （一致 = %s）" % (ref, s41_par == ref))
    msb = "".join(str(bit(s41_par, j)) for j in range(WIDTH - 1, -1, -1))
    print("   S(41) 二进制 Scr[32]..Scr[0] = %s" % msb)

    if args.expand:
        print("\n[5] 状态-only 展开式（无本拍依赖，纯从 33 级寄存器出；推荐给 RTL）")
        rows_s = state_only_rows(P, taps)
        terms = [len(r) for r in rows_s]
        gates = sum(t - 1 for t in terms)
        maxage = max((max(r) for r in rows_s if r), default=0)
        print("   每拍 %d 个 XOR2（各输出位项数 %d~%d），最深年龄 %d ⇒ 只需 33 级寄存器（%d bit）"
              % (gates, min(terms), max(terms), maxage, WIDTH))
        print("   各输出位依赖的寄存器（年龄 = b[n-age]）：")
        for i, r in enumerate(rows_s):
            print("     scr[%2d] = XOR of %s      （%d 项）" % (
                i, " ".join("b[n-%d]" % a for a in sorted(r)) or "0（恒 0）", len(r)))
        tot, bad = state_only_check(init, taps)
        print("   与逐拍序列核验：%d 位次对比，不一致 %d" % (tot, bad))
        print("   对比：窗口递推式 = 每拍 %d 个 XOR2，但有本拍内先后依赖（组合链 <= 4 级）。" % P)

    if args.window:
        print("\n[6] 滚动窗口法（33 bit 就够，不是 40；每拍 %d 个 XOR2，但有本拍内先后依赖）" % P)
        r, seq = init, []
        for _ in range(WIDTH + P + 120):
            seq.append(bit(r, 0)); r, _, _ = step(r, taps)
        n0 = 40
        WLEN = max(P, WIDTH + 1)                     # 窗口至少要 33 项（公式最多引用到 W[32]）
        W = [seq[n0 - 1 - i] for i in range(WLEN)]
        print("   起始窗口（索引即“离当前拍多远”，W[0] = 最新 = b[n-1]，n=%d）：" % n0)
        print("      W[0..%d]（最新->最旧） = %s" % (WLEN - 1, "".join(str(W[j]) for j in range(WLEN))))
        for t in range(3):
            sn = window_next(W, P)
            truth = [seq[n0 + t * P + P - 1 - i] for i in range(P)]     # 同样“最新位在前”
            print("      第 %d 拍 sn[0..%d]（最新->最旧） = %s   与序列真值一致 = %s"
                  % (t + 1, P - 1, "".join(str(sn[j]) for j in range(P)), sn == truth))
            W = (sn + W)[:WLEN]                      # 窗口右移 P 位：P>=33 时等于整体翻新；P<33 时要保留旧尾巴
        print("      窗口推进：W' = (sn + W)[:33]；P<33 时必须保留旧尾巴（%d 项），否则算第二拍就会越界" % max(0, 33 - P))
        tot, bad_mask, bad_truth = window_check(init, taps, P)
        print("   交叉校验（%d 组）：与掩码法不一致 %d 组；与序列真值不一致 %d 组" % (tot, bad_mask, bad_truth))
        print("   边界提示：窗口最新位必须是“上一拍的最后一个比特”；若当成“本拍第一个比特”，整段结果会差 1 位。")

    if args.verilog:
        print("\n[7] Verilog 片段（33 级寄存器 + 一拍 %d bit 加扰；常数掩码已算好）" % P)
        print("    // S = 33 bit 当前扰码状态；D = %d bit 数据（D[0] 最先上线）" % P)
        print("    // A = %d bit 加扰输出；S_next = 下拍状态" % P)
        print("    wire [32:0] S;")
        print("    wire [%d:0] D, A;" % (P - 1) if P > 1 else "    wire D, A;")
        for i, m in enumerate(out_masks):
            print("    wire scr%-2d = ^(S & 33'h%09X);" % (i, m))
        if P > 1:
            print("    assign A = { %s };" % ", ".join(
                "scr%d ^ D[%d]" % (i, i) for i in range(P - 1, -1, -1)))
        else:
            print("    assign A = scr0 ^ D;")
        print("    wire [32:0] S_next;")
        for j, m in enumerate(rows_P):
            print("    assign S_next[%2d] = ^(S & 33'h%09X);" % (j, m))

    print("\n提示：掩码只由 (多项式抽头, 并行位宽 P) 决定，与数据无关，可离线算好写死进 RTL。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
