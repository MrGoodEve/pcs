#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrambler.py —— QC/T 1217 物理层数据域加扰：扰码移位寄存器逐拍追踪

口径（与国标对照）
------------------
* 多项式：正向 (A.4) x^33 + x^13 + 1；反向 (A.7) x^33 + x^20 + 1（A.2.2.6 / A.2.3.5）。
* 寄存器：33 级 Scr[0]..Scr[32]；本脚本按"内容从 Scr[0] 向 Scr[32] 搬"实现（图 A.15 / A.21 的箭头方向），
  即每拍：new Scr[j] = old Scr[j-1] (j=1..32)，new Scr[0] = 反馈 = Scr[a] ^ Scr[b]（默认 a=12, b=32）。
* 输出抽头是 Scr[0]（公式 A.5：A_n = Scr_n[0] ^ D_n）⇒ **Scr[32] 只参与反馈，不上线**。
* 初始值：标准只说"不应全为 0"（p27），取值自定；本脚本默认 0x1FFFFFFFF（33 位全 1），可用 --init 改。
* 位序：按 A.2 注（p24）"从最低比特到最高比特传输"，即 A_0 最先上线；寄存器打印用 Scr[32]..Scr[0]（左高右低）。

[待核] 抽头下标与公式指数的对应关系
----------------------------------
按本脚本的默认接线（抽头取 Scr[12] 与 Scr[32]）实测，输出序列满足 b[n+33] = b[n+20] ^ b[n]；
若目标是 (A.4) x^33+x^13+1（对应 b[n+33] = b[n+13] ^ b[n]），同一拓扑下抽头应取 Scr[19]。
两图（A.15 / A.21）的抽头位置与各自公式看起来正好互换，属于下标/方向约定的经典坑。
⇒ 写 RTL 或与对端联调前，用 --taps 切换两种读法，与对端逐位比对扰码序列来定死。

用法
----
    python scrambler.py                          # 默认：初值 0x1FFFFFFFF，抽头 12/32，移 66 拍，全部打印
    python scrambler.py --init 0x1FFFFFFFF --steps 66
    python scrambler.py --taps 19,32             # 换成 (A.4) 对应的另一种读法
    python scrambler.py --data 1011001010        # 同时演示 A_n = Scr_n[0] ^ D_n（数据位先发的在前）
    python scrambler.py --no-bits                # 打印时省略二进制列
"""

from __future__ import annotations

import argparse

WIDTH = 33
MASK = (1 << WIDTH) - 1
DEFAULT_INIT = 0x1FFFFFFFF          # 33 位全 1


def parse_int(text: str) -> int:
    """支持 0x.. / 0b.. / 十进制，也支持 33 个 0/1 的比特串（左高右低）。"""
    s = text.strip().replace("_", "")
    if s.lower().startswith(("0x", "0b")):
        return int(s, 0)
    if set(s) <= {"0", "1"} and len(s) == WIDTH:
        return int(s, 2)
    return int(s, 10)


def bit(reg: int, idx: int) -> int:
    return (reg >> idx) & 1


def step(reg: int, taps) -> tuple[int, int, int]:
    """走一拍：返回 (新寄存器, 反馈比特, 本拍上线抽头 Scr[0])。

    newScr[0] = Scr[a] ^ Scr[b]；其余级依次右移一位（内容朝 Scr[32] 方向）。
    """
    a, b = taps
    fb = bit(reg, a) ^ bit(reg, b)
    out = bit(reg, 0)                 # 公式 A.5 的 Scr_n[0]
    return (((reg << 1) | fb) & MASK), fb, out


def bin_str(reg: int) -> str:
    """Scr[32] ... Scr[0]（左为最高下标），便于与图对照。"""
    return format(reg & MASK, "0%db" % WIDTH)


def build_sequence(init: int, taps, length: int):
    """按同一初值/抽头跑 length 拍，返回扰码序列（够长才能唯一判定递推）。"""
    reg = init & MASK
    out = []
    for _ in range(length):
        out.append(bit(reg, 0))
        reg, _, _ = step(reg, taps)
    return out


def detect_recurrence(seq, degree=WIDTH, min_windows=20):
    """找出 k 使 b[n+degree] = b[n+k] ^ b[n]（反查本实现对应哪个多项式）。

    样本不足或序列退化（全 0）时不硬判，返回 (found, reason)。
    """
    if len(seq) - degree < min_windows:
        return [], "样本不足（需要至少 %d 个窗口）" % min_windows
    found = []
    for k in range(0, degree):
        if all(seq[n + degree] == (seq[n + k] ^ seq[n]) for n in range(len(seq) - degree)):
            found.append(k)
    if len(found) > 1:
        return found, "序列退化（多条递推同时成立，典型是全 0 自锁）"
    return found, ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="QC/T 1217 加扰寄存器逐拍追踪（Scr0 = Scr12 ^ Scr32 形式）")
    ap.add_argument("--init", default="0x1FFFFFFFF", help="寄存器初值（默认 0x1FFFFFFFF，可用 0x.. / 0b.. / 33 位比特串）")
    ap.add_argument("--taps", default="12,32", help="反馈抽头（默认 12,32，即图 A.15 画法）")
    ap.add_argument("--steps", type=int, default=66, help="移位拍数（默认 66）")
    ap.add_argument("--data", default=None, help="可选的被加扰比特流（按发送顺序，第一位先发），用于演示 A_n = Scr_n[0] ^ D_n")
    ap.add_argument("--no-bits", action="store_true", help="不打印二进制列")
    args = ap.parse_args(argv)

    taps = tuple(int(x) for x in args.taps.replace(" ", "").split(","))
    reg = parse_int(args.init) & MASK
    init_reg = reg
    if reg == 0:
        print("[注意] 初值为 0：标准要求初值不应全为 0，这里仅用于观察自锁现象。")
    data = None
    if args.data:
        data = [int(c) for c in args.data.strip() if c in "01"]

    print("=" * 78)
    print("QC/T 1217 加扰寄存器逐拍追踪")
    print("  初值        : 0x%09X（%s）" % (reg, bin_str(reg)))
    print("  抽头        : Scr[%d] ^ Scr[%d]  ->  new Scr[0]" % taps)
    print("  移位方向    : Scr[0] -> Scr[32]（每拍整体右移一格，反馈从 Scr[0] 灌入）")
    print("  输出抽头    : Scr[0]（公式 A.5：A_n = Scr_n[0] ^ D_n）")
    print("  拍数        : %d" % args.steps)
    print("  二进制列    : Scr[32] ... Scr[0]（左高右低）")
    print("=" * 78)
    head = "  拍   Scr[31:0] 低32位     Hex(33b)     二进制 Scr[32..0]                      反馈  扰码Scr[0]"
    if data is not None:
        head += "   D_n  A_n"
    print(head)
    print("-" * len(head))

    seq = []
    for n in range(args.steps + 1):
        out = bit(reg, 0)
        seq.append(out)
        line = "  %3d  %08X  %10s  %s" % (n, reg & 0xFFFFFFFF, "0x%09X" % reg,
                                          ("    " + bin_str(reg)) if not args.no_bits else "")
        if n < args.steps:
            _, fb, _ = step(reg, taps)
            line += "   %4s" % ("->" if args.no_bits else fb)
        else:
            line += "   %4s" % "-"
        line += "  %6d" % out
        if data is not None:
            d = data[n] if n < len(data) else None
            line += "  %3s  %3s" % ("-" if d is None else d, "-" if d is None else (d ^ out))
        print(line)
        if n < args.steps:
            reg, _, _ = step(reg, taps)
    print("-" * len(head))
    print("扰码序列 b[n] = Scr_n[0]（发送顺序，b[0] 最先上线）：")
    print("  " + "".join(str(x) for x in seq))
    print("  前 33 位：%s" % "".join(str(x) for x in seq[:33]))
    chk = build_sequence(init_reg, taps, 4 * WIDTH + 40)
    ks, why = detect_recurrence(chk)
    if ks and not why:
        k = ks[0]
        cur_exp = 32 - taps[0]
        print("  自检（用同一初值另跑 %d 拍判定）：" % len(chk))
        print("      本实现生成的序列满足  b[n+33] = b[n+%d] ^ b[n]  ->  多项式 x^33 + x^%d + 1" % (k, k))
        print("      抽头 Scr[%d] 对应的指数 = 32 - %d = x^%d。" % (taps[0], taps[0], cur_exp))
        print("      标准：正向 (A.4) 是 x^33+x^13+1（同拓扑需 --taps %d,32）；反向 (A.7) 是 x^33+x^20+1。" % (32 - 13))
    else:
        print("  自检：%s，无法判定递推（初值 0 会自锁）" % (why or "无匹配"))
    print("  提示：把这条序列与对端/基线逐位比对，即可确认两端的抽头读法是否一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
