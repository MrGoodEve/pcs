#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrambler_parallel.py —— 并行加扰：一拍同时得到 P 个 scr 比特的常数掩码

默认只做一件事：打印本拍 P 个 scr 比特的掩码 / 计算方法。

口径
----
* 寄存器 33 级 Scr[0..32]（Scr[0] 为最新位）；状态用 33 bit 整数 S 表示，bit j = Scr[j]。
* 单步：new Scr[0] = Scr[a] ^ Scr[b]（默认 a=12, b=32），其余各级朝 Scr[32] 方向搬一格。
* 加扰：A[i] = scr[i] ^ D[i]（公式 A.5：A_n = Scr_n[0] ^ D_n）；
  i = 0 对应本拍最先上线的数据比特 D[0]（最低比特先传）。
* scr[i] = Scr_{n+i}[0] = ^(S & mask[i])：纯组合、各位之间无依赖、一拍全部出；
  掩码只由 (抽头, P) 决定，与数据无关，可离线算好写死进 RTL。
* [待核] 抽头下标与公式指数的对应：默认接线对应 x^33+x^20+1；若要 (A.4) x^33+x^13+1 用 --taps 19,32。

用法
----
    python scrambler_parallel.py                    # 打印 P=40 的 scr 掩码表（默认）
    python scrambler_parallel.py --width 32         # 改并行位宽
    python scrambler_parallel.py --taps 19,32       # 换抽头读法
    python scrambler_parallel.py --verilog          # 输出 Verilog 片段
    python scrambler_parallel.py --state            # 附带下拍状态 S' 的掩码
    python scrambler_parallel.py --window           # 附带滚动窗口写法
    python scrambler_parallel.py --verify           # 与逐拍实现交叉验证
"""

from __future__ import annotations

import argparse
import random

WIDTH = 33
MASK = (1 << WIDTH) - 1


def bit(x: int, j: int) -> int:
    return (x >> j) & 1


def step(reg: int, taps) -> int:
    """单步：new Scr[0] = Scr[a] ^ Scr[b]，其余级搬一格。"""
    a, b = taps
    return ((reg << 1) | (bit(reg, a) ^ bit(reg, b))) & MASK


def advance(state: int, taps, steps: int) -> int:
    for _ in range(steps):
        state = step(state, taps)
    return state


def row_mask(steps: int, taps, j: int = 0) -> int:
    """T^steps 第 j 行掩码：该位 = ^(S & mask)。对基向量 e_k 求像即可。"""
    mask = 0
    for k in range(WIDTH):
        if bit(advance(1 << k, taps, steps), j):
            mask |= 1 << k
    return mask


def parity(mask: int, state: int) -> int:
    return bin(mask & state).count("1") & 1


def scr_masks(P: int, taps) -> list[int]:
    """scr[i] = Scr_{n+i}[0] = (T^i · S) 的第 0 位。"""
    return [row_mask(i, taps, 0) for i in range(P)]


def state_masks(P: int, taps) -> list[int]:
    """下拍状态 S' = T^P · S 的 33 行掩码。"""
    return [row_mask(P, taps, j) for j in range(WIDTH)]


def expr_of(mask: int, name: str = "S") -> str:
    bits = [j for j in range(WIDTH) if bit(mask, j)]
    return " ^ ".join("%s[%d]" % (name, j) for j in bits) if bits else "0"


def window_next(W, P: int, taps):
    """滚动窗口写法：W[i] = b[n-1-i]（最新位在前），返回 sn[k] = b[n+P-1-k]。

    一般式（k 从 P-1 递减到 0；抽头 (a,b) -> 滞后 la=a+1 / lb=b+1）：
        sn[k] = (k <= P-1-la ? sn[k+la] : W[k+la-P]) ^ (k <= P-1-lb ? sn[k+lb] : W[k+lb-P])
    每拍 P 个 XOR2，但有本拍内先后依赖；窗口至少 33 项，推进 W' = (sn + W)[:33]。
    """
    la, lb = taps[0] + 1, taps[1] + 1
    sn = [0] * P
    for k in range(P - 1, -1, -1):
        t1 = sn[k + la] if k <= P - 1 - la else W[k + la - P]
        t2 = sn[k + lb] if k <= P - 1 - lb else W[k + lb - P]
        sn[k] = t1 ^ t2
    return sn


def verify(P: int, taps, trials: int = 200) -> tuple[bool, bool]:
    """与逐拍实现交叉验证：本拍 P 个 scr 位、下拍状态。"""
    random.seed(20261013)
    sm, stm = scr_masks(P, taps), state_masks(P, taps)
    ok_scr = ok_state = True
    for _ in range(trials):
        s = random.getrandbits(WIDTH) & MASK
        ref, ref_scr = s, []
        for _ in range(P):
            ref_scr.append(bit(ref, 0))
            ref = step(ref, taps)
        if [parity(m, s) for m in sm] != ref_scr:
            ok_scr = False
        if [parity(m, s) for m in stm] != [bit(ref, j) for j in range(WIDTH)]:
            ok_state = False
    return ok_scr, ok_state


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="并行加扰 scr 掩码（一拍 P 个比特）")
    ap.add_argument("--width", type=int, default=40, help="并行位宽 P（默认 40）")
    ap.add_argument("--taps", default="12,32", help="反馈抽头 a,b（默认 12,32）")
    ap.add_argument("--verilog", action="store_true", help="输出 Verilog 片段")
    ap.add_argument("--state", action="store_true", help="附带下拍状态 S' 的掩码")
    ap.add_argument("--window", action="store_true", help="附带滚动窗口写法")
    ap.add_argument("--verify", action="store_true", help="与逐拍实现交叉验证")
    args = ap.parse_args(argv)

    taps = tuple(int(x) for x in args.taps.replace(" ", "").split(","))
    P = args.width
    masks = scr_masks(P, taps)

    print("并行加扰 scr 掩码：P = %d，寄存器 33 级，Scr0 = Scr%d ^ Scr%d" % (P, taps[0], taps[1]))
    print("scr[i] = ^(S & mask)    （S = 本拍寄存器状态；i = 0 是本拍最先上线的比特）")
    print()
    for i, m in enumerate(masks):
        print("scr[%2d] = 33'h%09X    %s" % (i, m, expr_of(m)))
    print()
    print("加扰：A[i] = scr[i] ^ D[i]")

    if args.state:
        print()
        print("下拍状态 S' = T^%d · S：" % P)
        for j, m in enumerate(state_masks(P, taps)):
            print("S'[%2d] = 33'h%09X    %s" % (j, m, expr_of(m)))

    if args.window:
        la, lb = taps[0] + 1, taps[1] + 1
        print()
        print("滚动窗口写法：W[i] = b[n-1-i]（最新位在前），sn[k] = b[n+P-1-k]，k 从 %d 递减到 0" % (P - 1))
        print("  sn[k] = (k <= %d ? sn[k%+d] : W[k%+d]) ^ (k <= %d ? sn[k%+d] : W[k%+d])"
              % (P - 1 - la, la, la - P, P - 1 - lb, lb, lb - P))
        print("  每拍 %d 个 XOR2；窗口至少 33 项，推进 W' = (sn + W)[:33]（P<33 时必须保留尾部旧比特）" % P)

    if args.verify:
        ok_scr, ok_state = verify(P, taps)
        print()
        print("交叉验证（200 组随机状态）：scr 位一致 = %s ；下拍状态一致 = %s" % (ok_scr, ok_state))

    if args.verilog:
        print()
        print("// S = 33 bit 当前扰码状态；D = %d bit 数据（D[0] 最先上线）；A = %d bit 加扰输出" % (P, P))
        print("wire [32:0] S;")
        print("wire [%d:0] D, A;" % (P - 1) if P > 1 else "wire D, A;")
        for i, m in enumerate(masks):
            print("wire scr%-2d = ^(S & 33'h%09X);" % (i, m))
        if P > 1:
            print("assign A = { %s };" % ", ".join("scr%d ^ D[%d]" % (i, i) for i in range(P - 1, -1, -1)))
        else:
            print("assign A = scr0 ^ D;")
        print("wire [32:0] S_next;")
        for j, m in enumerate(state_masks(P, taps)):
            print("assign S_next[%2d] = ^(S & 33'h%09X);" % (j, m))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
