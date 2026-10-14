#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crc_mask_gen.py —— 并行 CRC 的常数表生成器（CRC 宽度与 K 可自行指定）

生成的常数（每一拍吃 K bit）
--------------------------
    R_next = A · R  ^  B · D  ^  c          （A、B、c 全是常数，D 为**未取反**的原始数据字）
    · A：m 位状态 -> m 位状态（T^K 的每一行）
    · B：K 位数据 -> m 位状态（第 i 位数据对应掩码的第 i 位；i=0 是最先入的比特）
    · c：输入取反折算出的常数（c = XOR_{i} B_i），省掉 K 个反相器
    另有：CRC 校验字段 = ~R_final（输出取反），初值 = 全 1（写进寄存器复位值即可）
    长度不是 K 的整数倍时，尾巴按**真实剩余位数**再生成一套（不要补 0 凑满）

用法
    python crc_mask_gen.py --crc 8 --width 40                 # 打印 K=40 的常数表 + 自检
    python crc_mask_gen.py --crc 8 --width 40 --verilog       # 另出可粘贴的 Verilog
    python crc_mask_gen.py --crc 32 --width 64
    python crc_mask_gen.py --crc 8 --widths 8,16,24,40,64     # 一次比较多种 K 的规模
    python crc_mask_gen.py --crc 8 --width 40 --raw           # 只出十六进制掩码

参考实现（串行 + 并行）在同一目录的 `crc.py`；本脚本生成后再回灌 `crc.py` 的串行实现做交叉验证。
"""

from __future__ import annotations

import argparse
import random

from crc import REFPOLY, crc_parallel, crc_serial


def gen(K: int, m: int):
    """返回 (A[j] 状态掩码, B[j] 数据掩码, c 常数)。

    A[j]: 第 j 位输出依赖哪些旧状态位（bit k = 依赖 R_k）
    B[j]: 第 j 位输出依赖哪些数据位（bit i = 依赖 D_i，i=0 最先入）
    c   : 常数向量（m bit），把“输入取反”折进来
    """
    mask_all = (1 << m) - 1
    # T^K 的每一列：基向量 e_k 经 K 拍
    cols = []
    for k in range(m):
        v = 1 << k
        for _ in range(K):
            v = (v >> 1) ^ (REFPOLY[m] if (v & 1) else 0)
        cols.append(v)
    A = [0] * m
    for k, v in enumerate(cols):
        for j in range(m):
            if (v >> j) & 1:
                A[j] |= 1 << k
    # 数据位贡献 B_i = T^{K-1-i}(REFPOLY)
    Bi = []
    for i in range(K):
        v = REFPOLY[m]
        for _ in range(K - 1 - i):
            v = (v >> 1) ^ (REFPOLY[m] if (v & 1) else 0)
        Bi.append(v)
    B = [0] * m
    for i, v in enumerate(Bi):
        for j in range(m):
            if (v >> j) & 1:
                B[j] |= 1 << i
    c = 0
    for v in Bi:
        c ^= v
    return A, B, c, mask_all


def sim_masks(state: int, word: list, A, B, c, m: int) -> int:
    """按生成的常数直接算一拍（D 为未取反的原始数据）。"""
    D = sum(bit << i for i, bit in enumerate(word))
    out = 0
    for j in range(m):
        acc = bin(A[j] & state).count("1") & 1
        acc ^= bin(B[j] & D).count("1") & 1
        acc ^= (c >> j) & 1
        out |= acc << j
    return out


def verify(K: int, m: int, A, B, c, trials: int = 200) -> bool:
    """常数表 vs 逐比特串行实现（含随机长度：整除与非整除都试）。"""
    random.seed(20261014 + K + m)
    for n in list(range(1, min(K, 12))) + [K, K + 1, 2 * K, 2 * K + 3, 3 * K - 1]:
        for _ in range(trials // 5 if n > 4 * K else 8):
            data = [random.randint(0, 1) for _ in range(n)]
            R = (1 << m) - 1
            pos = 0
            while pos < n:
                w = min(K, n - pos)
                if w == K:
                    R = sim_masks(R, data[pos:pos + w], A, B, c, m)
                else:
                    A2, B2, c2, _ = gen(w, m)
                    R = sim_masks(R, data[pos:pos + w], A2, B2, c2, m)
                pos += w
            Bc = [1 ^ ((R >> i) & 1) for i in range(m)]
            Bs, _ = crc_serial(data, m)
            if "".join(str(b) for b in Bc) != Bs:
                return False
    return True


def print_verilog(K: int, m: int, A, B, c) -> None:
    print("    // K=%d 步进：R_next = A*R ^ B*D ^ c ；D 为未取反的原始数据字（D[0] 最先入）" % K)
    print("    wire [%d:0] R;" % (m - 1))
    print("    wire [%d:0] D;" % (K - 1))
    print("    wire [%d:0] R_next;" % (m - 1))
    for j in range(m):
        print("    assign R_next[%-2d] = ^(R & %d'h%0*X) ^ ^(D & %d'h%0*X) ^ 1'b%d;   // c=%d"
              % (j, m, m // 4, A[j], K, (K + 3) // 4, B[j], (c >> j) & 1, (c >> j) & 1))
    print("    // CRC 校验字段 = ~R_final（输出取反），寄存器复位值 = %d'h%0*X（全 1）"
          % (m, m // 4, (1 << m) - 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="并行 CRC 常数表生成器（CRC 与 K 可指定）")
    ap.add_argument("--crc", type=int, default=8, choices=(8, 16, 32))
    ap.add_argument("--width", type=int, default=40, help="并行位宽 K")
    ap.add_argument("--widths", default=None, help="一次生成多套，例如 8,16,24,40,64")
    ap.add_argument("--verilog", action="store_true", help="输出 Verilog 片段")
    ap.add_argument("--raw", action="store_true", help="只输出十六进制掩码")
    ap.add_argument("--show", type=int, default=10, help="每个输出位最多展开几项")
    args = ap.parse_args(argv)
    m = args.crc
    widths = [int(x) for x in args.widths.split(",")] if args.widths else [args.width]

    for K in widths:
        A, B, c, _ = gen(K, m)
        ok = verify(K, m, A, B, c)
        if args.raw:
            print("# CRC%d K=%d  A=%s  B=%s  c=0x%0*X" % (
                m, K,
                ",".join("%0*X" % (m // 4, v) for v in A),
                ",".join("%0*X" % ((K + 3) // 4, v) for v in B), m // 4, c))
            print("#   自检 vs 串行实现：%s" % ("一致" if ok else "不一致"))
            continue

        print("=" * 78)
        print("CRC%d 并行常数表：K = %d bit/拍；反射多项式 0x%0*X" % (m, K, m // 4, REFPOLY[m]))
        print("  R_next = A·R ^ B·D ^ c ；D 为未取反的原始数据字（D[0] 是最先入的比特）")
        print("=" * 78)
        tot = 0
        for j in range(m):
            st = [k for k in range(m) if (A[j] >> k) & 1]
            dt = [i for i in range(K) if (B[j] >> i) & 1]
            tot += len(st) + len(dt)
            print("  R_next[%-2d] = ^(R & %d'h%0*X) ^ ^(D & %d'h%0*X) ^ 1'b%d"
                  % (j, m, m // 4, A[j], K, (K + 3) // 4, B[j], (c >> j) & 1))
            print("             状态项 %s | 数据项 %s%s"
                  % (",".join("R%d" % k for k in st) or "无",
                     " ".join("D%d" % i for i in dt[:args.show]) or "无",
                     " ...(共 %d 项)" % len(dt) if len(dt) > args.show else ""))
        gates = sum(min(bin(v).count("1") - 1, 1 << 30) for v in A + B if v)
        print("  常数规模：状态项 %d + 数据项 %d = %d；折 XOR2 约 %d 个；输入取反常数 c = 0x%0*X"
              % (sum(bin(v).count("1") for v in A), sum(bin(v).count("1") for v in B), tot, gates, m // 4, c))
        print("  自检（与 crc.py 的逐比特串行实现对照，含非整除尾巴）：%s" % ("一致" if ok else "不一致"))
        if args.verilog:
            print()
            print_verilog(K, m, A, B, c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
