#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crc.py —— QCT 1217 的 CRC8/16/32：逐比特串行实现 + 并行(K bit/拍)实现，同文件互相验证

依据
----
* 表 A.7（p28）生成多项式：
    CRC8  = x^8+x^5+x^3+x^2+x+1        CRC16 = x^16+x^15+x^2+1
    CRC32 = x^32+x^26+x^23+x^22+x^16+x^12+x^11+x^10+x^8+x^7+x^5+x^4+x^2+x+1
* 图 A.18（p29）线性反馈移位寄存器（右移/反射型）；标准注：C0 对应 x^(m-1)
* 处理步骤（p29 a~d）：a) 初值全 1；b) 被保护序列 D(0)~D(n-1) 逐比特取反后按 D(0) 先入；
  c) 读寄存器状态 C0~Cm-1；d) 取反得校验序列 B(0)~B(m-1)，B(0) 是校验字段最低位
* 位序（p29 注）：比特序列靠左为最低位、靠右为最高位

串行接线（图 A.18 a，方框 C7 C6 C5 C4 C3 C2 C1 C0 从左到右）
    输入 --->(+)---> [C7] -->(+)--> [C6] ... 底部一根反馈线从 C0 拉回输入端
    fb = C0 ^ D_in（D_in 为取反后的输入比特）；新 C7 = fb
    新 C_j = C_{j+1} ^ (fb 仅在“反射多项式第 j 位为 1”时)
    反射多项式：CRC8 = 0xF4、CRC16 = 0xA001、CRC32 = 0xEDB88320
    （异或门个数 = 反射多项式里 1 的个数：CRC8 图上 5 个、CRC16 图上 3 个）

并行（一拍 K bit，与加扰器同一套线性代数）
    R_{n+K} = T^K · R_n  ^  SUM_{i=0..K-1} ( T^{K-1-i} · REFPOLY ) · d_i
    => 每条输出位 = 旧状态若干位的异或 ^ 本拍 K 个数据位中若干位的异或（常数异或网，一拍出结果）
    常数只由 (m,K) 决定、与数据无关；输入取反可折进常数 SUM B_i；初值/输出取反也都是常数
    长度不是 K 的整数倍时，尾巴按**真实剩余位数**另算掩码，不能补 0 凑满

用法
    python crc.py                                   # 自检：PRBS7 逐拍 + 标准三示例 + 串行/并行互验 + 补零/重置对比
    python crc.py --data 0110_0000_1010_0000         # 指定数据：串行逐拍 + 并行分组结果
    python crc.py --len 544 --width 40               # 544 bit（反向 PLDB）按 K=40 处理
    python crc.py --crc 16 --data 0110_0000_1010_0000_0110_0000_1010_0000
"""

from __future__ import annotations

import argparse
import random

REFPOLY = {8: 0xF4, 16: 0xA001, 32: 0xEDB88320}          # rev(表 A.7 多项式) >> 1
STD_EXAMPLES = ((8, "0110000010100000", "11110011"),
                (16, "01100000101000000110000010100000", "1011010010100110"),
                (32, "0110000010100000" * 4, "11110110110110100101110001110101"))


# ----------------------------------------------------------------- 串行（逐比特）
def crc_step(R: int, d_in: int, m: int) -> int:
    """按图 A.18 打一拍（整数形式，bit j = C_j）：R' = (R>>1) ^ (fb ? REFPOLY : 0)，fb = C0 ^ d_in。"""
    return (R >> 1) ^ (REFPOLY[m] if ((R & 1) ^ d_in) else 0)


def crc_serial(bits, m: int, init: int | None = None, trace: list | None = None):
    """逐比特串行：bits = [D(0), D(1), ...]。返回 (校验序列 B(0..m-1) 的字符串, 最终寄存器)。"""
    R = (1 << m) - 1 if init is None else init            # a) 初值全 1
    for t, D in enumerate(bits):
        R_old = R
        R = crc_step(R, D ^ 1, m)                         # b) 输入比特取反
        if trace is not None:
            fb = (R_old & 1) ^ (D ^ 1)
            trace.append((t, D, R_old, fb, R))
    B = [1 ^ ((R >> i) & 1) for i in range(m)]            # d) 状态取反；B(i) = ~C_i
    return "".join(str(b) for b in B), R


def B_hex(Bstr: str) -> int:
    return sum(int(c) << i for i, c in enumerate(Bstr))   # 靠左为最低位


# ----------------------------------------------------------------- 并行（K bit/拍）
def masks(K: int, m: int):
    """返回 (state_mask[j]: 旧状态哪些位影响新 bit j, in_mask[j]: 本拍哪些数据位影响新 bit j, cinv)。"""
    cols = []
    for k in range(m):                                    # T^K 的每一列：基向量 e_k 经 K 拍的像
        v = 1 << k
        for _ in range(K):
            v = crc_step(v, 0, m)
        cols.append(v)
    state_mask = [0] * m
    for k, v in enumerate(cols):
        for j in range(m):
            if (v >> j) & 1:
                state_mask[j] |= 1 << k
    B = []
    for i in range(K):                                    # 第 i 位（i=0 最先入）的贡献 B_i = T^{K-1-i}(REFPOLY)
        v = REFPOLY[m]
        for _ in range(K - 1 - i):
            v = crc_step(v, 0, m)
        B.append(v)
    in_mask = [0] * m
    for i, v in enumerate(B):
        for j in range(m):
            if (v >> j) & 1:
                in_mask[j] |= 1 << i
    cinv = 0
    for v in B:
        cinv ^= v                                         # 输入全 1（原数据全 0）的常数贡献
    return state_mask, in_mask, cinv


def crc_parallel(bits, m: int, K: int, init: int | None = None, trace: list | None = None):
    """并行：按 K 位一组推进，尾组按剩余位数现算掩码。返回 (校验序列字符串, 最终寄存器)。"""
    R = (1 << m) - 1 if init is None else init
    pos, n = 0, len(bits)
    while pos < n:
        w = min(K, n - pos)
        chunk = bits[pos:pos + w]
        sm, im, _ = masks(w, m)
        newR = 0
        for j in range(m):
            acc = bin(sm[j] & R).count("1") & 1
            for i, d in enumerate(chunk):
                if (im[j] >> i) & 1:
                    acc ^= (d ^ 1)
            newR |= (acc & 1) << j
        R = newR
        pos += w
        if trace is not None:
            trace.append((w, R))
    return "".join(str(1 ^ ((R >> i) & 1)) for i in range(m)), R


def prbs7(n, seed=0x7F):
    """PRBS7（x^7+x^6+1），每拍输出 state[6]，周期 127。"""
    st, out = seed & 0x7F, []
    for _ in range(n):
        out.append((st >> 6) & 1)
        st = ((st << 1) | (((st >> 6) & 1) ^ ((st >> 5) & 1))) & 0x7F
    return out


# ----------------------------------------------------------------- 输出辅助
def print_trace(bits, m, title="串行逐拍"):
    tr = []
    Bs, Rs = crc_serial(bits, m, trace=tr)
    print("    %s（初值全 1；D 为输入数据比特，D^1 才是进寄存器的比特）" % title)
    print("      拍   D  D^1   fb  " + "".join("C%-2d " % j for j in range(m - 1, -1, -1)))
    print("       -   -   -    -   " + "".join("1   " for _ in range(m)))
    for t, D, Rold, fb, R in tr:
        print("      %2d   %d   %d    %d   %s" % (t, D, D ^ 1, fb,
              "".join("%d   " % ((R >> j) & 1) for j in range(m - 1, -1, -1))))
    print("      最终寄存器 C%d..C0 = %s   校验序列 B(0)..B(%d) = %s（0x%0*X）"
          % (m - 1, "".join(str((Rs >> j) & 1) for j in range(m - 1, -1, -1)), m - 1, Bs, m // 4, B_hex(Bs)))
    return Bs, Rs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="QCT 1217 CRC：串行 + 并行（同文件互验）")
    ap.add_argument("--crc", type=int, default=8, choices=(8, 16, 32))
    ap.add_argument("--width", type=int, default=40, help="并行位宽 K（默认 40）")
    ap.add_argument("--len", type=int, default=544, help="--len 模式下的被保护序列比特数（默认 544）")
    ap.add_argument("--data", default=None, help="直接给数据比特串（可含下划线/空格）")
    args = ap.parse_args(argv)
    m, K = args.crc, args.width

    print("=" * 78)
    print("CRC%d：反射多项式 0x%0*X；串行=逐比特（图 A.18），并行=一拍 %d bit" % (m, m // 4, REFPOLY[m], K))
    print("=" * 78)

    # ---- 模式 A：指定数据
    if args.data:
        s = args.data.replace("_", "").replace(" ", "")
        bits = [int(c) for c in s]
        print("\n输入数据：%s（%d bit；靠左为最低位 D(0)，最先入）" % (s, len(bits)))
        Bs, Rs = print_trace(bits, m)
        print("\n    并行（K=%d）：" % K)
        tr = []
        Bp, Rp = crc_parallel(bits, m, K, trace=tr)
        for i, (w, R) in enumerate(tr, 1):
            print("      拍 %2d：吃 %2d bit -> 寄存器 0x%0*X" % (i, w, m // 4, R))
        print("    并行校验序列 = %s（0x%0*X）  == 串行 = %s" % (Bp, m // 4, B_hex(Bp), Bp == Bs))
        return 0

    # ---- 模式 B：任意长度 / 反向 PLDB 544 bit
    print("\n(1) 串行自检：PRBS7（周期 %d）、初值全 1、前 16 拍逐拍" % 127)
    seq = prbs7(40)
    print_trace(seq[:16], m)

    print("\n(2) 核对标准 p29 的三个示例（串行与并行都过一遍）")
    for mm, ds, cs in STD_EXAMPLES:
        bits = [int(c) for c in ds]
        Bs, _ = crc_serial(bits, mm)
        Bp, _ = crc_parallel(bits, mm, K if K <= len(bits) else len(bits))
        print("    CRC%-2d 串行 %s / 并行 %s / 标准 %s -> %s"
              % (mm, Bs, Bp, cs, "一致" if Bs == cs == Bp else "有问题"))

    print("\n(3) 串行 vs 并行 互验（随机数据，跨长度、跨位宽，含不整除的尾巴）")
    random.seed(20261014)
    bad = []
    for w in (8, 16, 24, 33, 40, 64):
        for n in (7, 8, 16, 40, 41, 80, 544, 552, 1000):
            data = [random.randint(0, 1) for _ in range(n)]
            Bs, _ = crc_serial(data, m)
            Bp, _ = crc_parallel(data, m, w)
            if Bs != Bp:
                bad.append((w, n))
    print("    位宽 8/16/24/33/40/64 x 长度 7/8/16/40/41/80/544/552/1000 共 54 组：%s"
          % ("全部一致" if not bad else "不一致 %s" % bad))

    print("\n(4) 反向 PLDB 例子：被保护序列 %d bit" % args.len)
    if args.len == 544:
        print("    构成：反向 PLDB 控制 16 bit + 净荷 8 x 66 = 528 bit = 544 bit（CRC8 另占 8 bit，线上 552 bit）")
    data = [random.randint(0, 1) for _ in range(args.len)]
    full, tail = divmod(args.len, K)
    print("    按 K=%d：%d 拍满 + 最后一拍 %d bit = %d 拍%s" % (
        K, full, tail, full + (1 if tail else 0), "；尾巴按真实位数另算掩码，不能补 0" if tail else "（整除，无尾巴）"))
    tr = []
    Bp, Rp = crc_parallel(data, m, K, trace=tr)
    Bs, Rs = crc_serial(data, m)
    for i, (w, R) in enumerate(tr, 1):
        print("      拍 %2d：吃 %2d bit -> 状态 0x%0*X" % (i, w, m // 4, R))
    print("    并行 = %s（0x%0*X）  串行 = %s  一致 = %s" % (Bp, m // 4, B_hex(Bp), Bs, Bp == Bs))
    print("    同一数据换位宽：", ", ".join("K=%d->0x%0*X" % (w, m // 4, B_hex(crc_parallel(data, m, w)[0]))
          for w in (8, 16, 32, 40, 64)))

    print("\n(5) 两个易错点（用串行实现实测）")
    base = prbs7(16)
    B_std, R_std = crc_serial(base, m)
    v_std = B_hex(B_std)
    B_pad, _ = crc_serial(base + [0] * m, m)              # 末尾补 m 个 0 当数据喂入
    Rc = R_std
    for _ in range(m):
        Rc = crc_step(Rc, 0, m)                           # 末尾再打 m 拍、输入喂 0
    print("    补零？A 标准不补 = 0x%0*X ；B 补 %d 个 0 当数据 = 0x%0*X ；C 再打 %d 拍输入喂 0 取反 = 0x%0*X"
          % (m // 4, v_std, m, m // 4, B_hex(B_pad), m, m // 4,
             sum((1 ^ ((Rc >> i) & 1)) << i for i in range(m))))
    print("    => 补 0 的结果与标准不同，标准只要 a)~d) 四步（喂完读数取反），不需要补 0")
    b1, b2 = base, prbs7(16, seed=0x33)
    B1, R1 = crc_serial(b1, m)
    B2r, _ = crc_serial(b2, m)                            # 重置
    B2c, _ = crc_serial(b2, m, init=R1)                   # 不重置
    print("    重置？块1 = 0x%0*X ；块2 重置 = 0x%0*X ；块2 不重置 = 0x%0*X" % (
        m // 4, B_hex(B1), m // 4, B_hex(B2r), m // 4, B_hex(B2c)))
    print("    => 每块必须把初值重置为全 1（标准 a 步），不重置必然与收端不一致")

    print("\n(6) 收侧校验（标准未写，[推论]）：数据 + 收到的 CRC 字段 都按输入规则取反后一起喂入，末态应为固定常数")
    res = set()
    for _ in range(50):
        d = [random.randint(0, 1) for _ in range(48)]
        Bf, _ = crc_serial(d, m)
        R = (1 << m) - 1
        for x in d:
            R = crc_step(R, x ^ 1, m)
        for c in Bf:
            R = crc_step(R, (int(c)) ^ 1, m)
        res.add(R)
    print("    CRC%d：末态 = %s（与数据无关）" % (m, ", ".join("0x%0*X" % (m // 4, v) for v in res)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
