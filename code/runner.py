# -*- coding: utf-8 -*-
"""主线入口：读配置 → 两个实现都跑 → 对拍。

用法
    python runner.py                 # 问答式（不记得参数就用这个）
    python runner.py --code fwd --nu 3 --seed 1
    python runner.py --code rev --err 10:0x5A,370:0xA5 --trace
    python runner.py --selftest      # 跑一批组合，输出两实现的一致率

配置项
    --code rev|fwd     反向 RS(73,69,8) / 正向 RS(384,354,9)
    --nu N            注入错误个数（>t 触发失败判据或误纠）
    --seed N          随机种子（数据与错误位置/幅值都由它决定）
    --err p:v,...     手工指定错误（覆盖随机）：位置:误码值，发送序 0..n-1
    --trace           打印规格版的逐轮账目
    --selftest        跑一批组合看一致率
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import CODES, GF, make_case, n_of, parse_errs      # noqa: E402
import spec_impl                                               # noqa: E402
import ref_impl                                                # noqa: E402

W = 78


def hr(t=""):
    print("=" * W if not t else t.center(W, "="))


def pad(P, m):
    return list(P) + [0] * max(0, m - len(P))


def cmp_poly(gf, a, b):
    m = max(len(a), len(b))
    A, B = pad(a, m), pad(b, m)
    first = next((i for i in range(m) if A[i] != B[i]), None)
    return A == B, first, A, B


def agree_only(ch):
    """只看两实现之间是否一致（"与注入真值"是外部真值，不算分歧）。"""
    return all(v for k, v in ch.items() if v is not None and not k.startswith("_"))


def run_one(cfgname, nu, seed, errs=None, trace=False, quiet=False):
    cfg = CODES[cfgname]
    gf = GF(cfg["mu"], cfg["poly"])
    cw, rw, errs = make_case(gf, cfg, nu, seed, errs)
    n = n_of(cfg)
    t = cfg["two_t"] // 2
    true_map = dict(errs)

    so = spec_impl.decode(gf, cfg, rw)
    ro = ref_impl.decode(gf, cfg, rw)

    if not quiet:
        hr()
        print("配置：%s" % cfg["title"])
        print("      n=%d  k=%d  2t=%d  t=%d   |  ν=%d  seed=%d  FCR=%d"
              % (n, cfg["k"], cfg["two_t"], t, len(errs), seed, cfg["fcr"]))
        print("      注入：%s" % "  ".join("位置%d=0x%0*X" % (p, (gf.mu + 3) // 4, e) for p, e in errs))
        print("      （位置 0..%d：0..%d 是数据段，%d..%d 是校验段）" % (n - 1, cfg["k"] - 1, cfg["k"], n - 1))
        print()

    # ---- 规格版 ----
    if not quiet:
        hr("① 规格版 spec_impl（你的定稿算法）")
        print("伴随式 S = %s" % gf.arr(so["S"]))
        print("Λ（BM 8 步）= %s   deg Λ = %d" % (gf.arr(so["Lam"]), so["L"]))
        if trace:
            print("  ── 逐轮账目 ──")
            for r in so["rows"]:
                tail = ("s=%d  δ/b=%s  修正块=%s  C_len=%d  L=%d  B=%s  b=%s  H=%d"
                        % (r["s"], gf.v(r["coef"]), gf.arr(r["blk"]), r["C_len"],
                           r["L_out"], gf.arr(r["B_out"]), gf.v(r["b_out"]), r["H_out"])
                        ) if r["action"] == "修正" else "δ=0 空转"
                print("   N=%-3d L:%d→%-2d  δ=%s   %s"
                      % (r["N"], r["L_in"], r["L_out"], gf.v(r["delta"]), tail))
                print("          Λout = %s" % gf.arr(r["C_out"]))
        if so["status"] == "FAIL①":
            print("判据①：BM 递推长度 L = %s > t = %d ⇒ decoder failure（提前中止，不跑 Chien/Forney）✓"
                  % (so.get("L_rec"), t))
            print("      Λ = %s   deg Λ = %d" % (gf.arr(so["Lam"]), so["L"]))
        else:
            print("Chien（根形式）= d %s ⇒ 位置 %s   [根数 %d vs deg Λ %d]"
                  % (so["ds"], so.get("pos", []), len(so["ds"]), so["L"]))
        if so["status"] == "FAIL②":
            print("判据②：根数 < deg Λ ⇒ decoder failure（不输出数据）✓")
        elif so["status"] == "FAIL③":
            print("判据③：Ω[%s] ≠ 0（门槛 j≥L 应为 0）⇒ decoder failure ✓" % so["over"])
        else:
            print("Ω = %s" % gf.arr(so["Omega"]))
            print("λ′ = %s" % gf.arr(so["dv"]))
            for f, p in zip(so["fs"], so["pos"]):
                print("  位置 %-4d d=%-3d X⁻¹=%-12s Ω=%-12s λ′=%-12s ⇒ E=%s"
                      % (p, f[0], gf.v(f[1]), gf.v(f[2]), gf.v(f[3]), gf.v(f[4])))
            print("判据④：纠正后 S %s ⇒ %s" % ("全 0 ✓" if so["status"] == "OK" else "非 0 ✗", so["status"]))

    # ---- 参考版 ----
    if not quiet:
        print()
        hr("② 参考版 ref_impl（独立路线：经典 BM + 折返指数 Chien + 高斯消元幅值）")
        print("Λ（教科书 BM）= %s   deg Λ = %d" % (gf.arr(ro["Lam"]), ro["L"]))
        print("Chien（直接代入）= 位置 %s" % ro.get("pos", []))
        if ro["status"] == "FAIL②":
            print("判据②：根数/方程组不成立 ⇒ decoder failure ✓")
        else:
            for p, e in zip(ro["pos"], ro["Es"]):
                print("  位置 %-4d ⇒ E=%s（高斯解）" % (p, gf.v(e)))
            print("判据④：纠正后 S %s ⇒ %s" % ("全 0 ✓" if ro["status"] == "OK" else "非 0 ✗", ro["status"]))

    # ---- 对拍 ----
    checks = {}
    ok_poly, firstdiff, A, B = cmp_poly(gf, so["Lam"], ro["Lam"])
    checks["Λ 逐系数"] = ok_poly
    if not ok_poly and not quiet:
        print("   （首个不一致下标 %d：spec=%s  ref=%s）" % (firstdiff, gf.v(A[firstdiff]), gf.v(B[firstdiff])))

    so_fail = so["status"].startswith("FAIL")
    ro_fail = ro["status"].startswith("FAIL")
    checks["判定(成功/失败)"] = so_fail == ro_fail
    if so["status"] == "OK" and ro["status"] == "OK":
        checks["位置集合"] = set(so["pos"]) == set(ro["pos"])
        m1 = dict(zip(so["pos"], so["Es"]))
        m2 = dict(zip(ro["pos"], ro["Es"]))
        checks["幅值"] = m1 == m2
        checks["纠正后码字"] = so["fixed"] == ro["fixed"]
        checks["与注入真值"] = (so["fixed"] == cw) and (m1 == true_map)
    else:
        checks["位置集合"] = None
        checks["幅值"] = None
        checks["纠正后码字"] = None
        checks["与注入真值"] = None

    # 记录实际状态（"_" 前缀 = 元信息，不参与一致性判定）
    checks["_status"] = so["status"]
    checks["_labels"] = "%s / %s" % (so["status"], ro["status"])

    if not quiet:
        print()
        hr("对拍结果")
        for k, v in checks.items():
            if k.startswith("_"):
                continue
            print("  %-12s : %s" % (k, "一致 ✓" if v else ("—（未走到这步）" if v is None else "★不一致 ✗")))
        print("  %-12s : %s" % ("spec 状态", so["status"]))
        print("  %-12s : %s" % ("ref 状态", ro["status"]))
        if so["status"] != ro["status"] and so_fail and ro_fail:
            print("  注：两实现判定一致（都是解码失败），只是判据标签不同 —— 规格版按 ①/②/③ 提前返回，"
                  "参考版只有 ②/④。")
        agree = agree_only(checks)
        print()
        print("  ⇒ %s" % ("两实现完全一致 ✓" if agree else "★存在分歧，需要查！"))
        if checks.get("与注入真值") is False:
            print("  注：两实现同时正确/同时错；本次纠正结果 ≠ 原码字 —— 若 ν>t，这是「误纠」")
            print("      （输出是合法码字、S 全 0，任何内部判据都不可检，需上层 CRC/重传兜）")
        hr()
    return checks


def selftest():
    hr("自检：两实现一致率 / 与注入真值一致率")
    print("  %-5s %-4s %-8s %-10s %-14s %s" % ("码", "ν", "用例", "两实现一致", "判对(==原码字)", "spec 状态分布"))
    for cname in ("rev", "fwd"):
        cfg = CODES[cname]
        t = cfg["two_t"] // 2
        for nu in sorted({1, 2, t, t + 1, 2 * cfg["two_t"]}):
            if nu > 2 * cfg["two_t"]:
                continue
            agree = correct = total = 0
            dist = {}
            for seed in range(1, 5):
                ch = run_one(cname, nu, seed, quiet=True)
                total += 1
                if agree_only(ch):
                    agree += 1
                if ch.get("与注入真值"):
                    correct += 1
                key = ch["_status"]
                if key == "OK" and not ch.get("与注入真值"):
                    key = "OK(误纠)"
                dist[key] = dist.get(key, 0) + 1
            print("  %-5s %-4d %-8d %-10s %-14s %s"
                  % (cname, nu, total, "%d/%d" % (agree, total),
                     "%d/%d" % (correct, total),
                     " ".join("%s×%d" % (k, v) for k, v in sorted(dist.items()))))
    hr()


def ask_and_run():
    print("=" * W)
    print("RS-FEC 解码链对拍 —— 回车用默认值".center(W - 6))
    print("=" * W)
    c = input("1) 用哪个码？  1 = 反向 RS(73,69,8)   2 = 正向 RS(384,354,9)        [1] ").strip() or "1"
    cfgname = "rev" if c == "1" else "fwd"
    cfg = CODES[cfgname]
    t, two_t = cfg["two_t"] // 2, cfg["two_t"]
    print("   → %s   t=%d, 2t=%d, k=%d, n=%d" % (cfg["title"], t, two_t, cfg["k"], n_of(cfg)))
    s = input("2) 注入几个错 ν？  （≤%d 可纠；>%d 看失败判据/误纠）      [2] " % (t, t)).strip() or "2"
    nu = int(s, 0)
    s = input("3) 随机种子？                                                [1] ").strip() or "1"
    seed = int(s, 0)
    s = input("4) 错误位置：回车=随机；或 p:v,p:v（如 10:0x5A,370:0xA5）  [回车] ").strip()
    errs = parse_errs(s) if s else None
    trace = input("5) 打印逐轮账目？                                         [y/N] ").strip().lower()[:1] == "y"
    print()
    run_one(cfgname, nu, seed, errs=errs, trace=trace)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--code", choices=["rev", "fwd"], default=None)
    ap.add_argument("--nu", type=int, default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--err", default=None)
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if a.code is None or a.nu is None:
        ask_and_run()
        return
    run_one(a.code, a.nu, a.seed, errs=parse_errs(a.err) if a.err else None, trace=a.trace)


if __name__ == "__main__":
    main()
