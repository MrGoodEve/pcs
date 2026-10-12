# -*- coding: utf-8 -*-
"""判据探针：统计 4 条失败判据各自拦下什么，并验证「②通过时 ③ 与 ④ 是否等价」。

用法
    python criteria_probe.py                 # 默认两组码都扫
    python criteria_probe.py --code rev --nu-max 8 --seeds 200
    python criteria_probe.py --cases 10      # 只打印前 10 条命中用例的明细

不改动 spec_impl / ref_impl，只调用它们；本文件是对拍体系之外的统计工具。
"""

import argparse
import collections

from common import CODES, GF, make_case, n_of
import spec_impl


def probe_one(cfgname, nu, seed):
    """跑一次，返回分类结果 dict。

    bucket 取值：
      OK_正确      —— 判据全过，且纠正结果 == 原码字
      OK_误纠      —— 判据全过，但纠正结果 ≠ 原码字（输出仍是合法码字）
      FAIL②        —— Chien 根数 < deg Λ
      FAIL③        —— ∃ j ≥ L 使 Ω[j] ≠ 0（此时纠正后 S 必然非 0）
      FAIL④        —— ③ 通过但纠正后重算 S ≠ 0（本条路径当前实现不会走到，留作对照）
    """
    cfg = CODES[cfgname]
    gf = GF(cfg["mu"], cfg["poly"])
    cw, rw, errs = make_case(gf, cfg, nu, seed)

    S = spec_impl.rx_syndrome(gf, cfg, rw)
    Lam, _rows = spec_impl.bm(gf, cfg, S)
    L = spec_impl.deg(Lam)
    ds, Lt = spec_impl.chien(gf, cfg, Lam)

    out = dict(code=cfgname, nu=nu, seed=seed, L=L, Ltilde=Lt,
               roots=len(ds), deg_omega=None, omega_ge_L=None,
               post_s_zero=None, fixed_is_cw=None, bucket=None)

    if len(ds) < L:
        out["bucket"] = "FAIL②"
        return out

    # ② 通过：L 个根都在域内。下面独立算 Ω，看 ③ 与 ④ 谁先响。
    Om = spec_impl.omega(gf, cfg, Lam, S)
    dv = spec_impl.lam_deriv(Lam)
    fs = spec_impl.forney(gf, Om, dv, ds)
    Es = [f[4] for f in fs]
    pos = [spec_impl.pos_of(cfg, d) for d in ds]
    fixed = list(rw)
    for p, e in zip(pos, Es):
        fixed[p] ^= e
    S2 = spec_impl.rx_syndrome(gf, cfg, fixed)

    out["deg_omega"] = spec_impl.deg(Om)
    out["omega_ge_L"] = out["deg_omega"] >= L                  # 判据③ 的实质
    out["post_s_zero"] = all(v == 0 for v in S2)               # 判据④ 的实质
    out["fixed_is_cw"] = out["post_s_zero"]
    if out["omega_ge_L"]:
        out["bucket"] = "FAIL③"
        out["pos"] = pos
    elif not out["post_s_zero"]:
        out["bucket"] = "FAIL④"                                # 理论上不该出现
    else:
        out["bucket"] = "OK_正确" if fixed == cw else "OK_误纠"
        out["pos"] = pos
    return out


def sweep(cfgname, nu_list, seeds, examples=0):
    tally = collections.Counter()
    mism = []       # ③ 与 ④ 不等价的用例
    samples = collections.defaultdict(list)
    for nu in nu_list:
        for seed in seeds:
            r = probe_one(cfgname, nu, seed)
            tally[r["bucket"]] += 1
            if r["deg_omega"] is not None and r["omega_ge_L"] == r["post_s_zero"]:
                mism.append(r)          # ③ 为真（degΩ≥L）却 ④ 为真（S 全 0），或反之
            if len(samples[r["bucket"]]) < examples:
                samples[r["bucket"]].append(r)
    return tally, mism, samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", choices=["rev", "fwd", "both"], default="both")
    ap.add_argument("--nu-max", type=int, default=None)
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--cases", type=int, default=5, help="每类打印几条明细")
    a = ap.parse_args()

    codes = ["rev", "fwd"] if a.code == "both" else [a.code]
    for cname in codes:
        cfg = CODES[cname]
        t = cfg["two_t"] // 2
        n = n_of(cfg)
        nu_max = a.nu_max or (n - 1)
        nu_list = list(range(t + 1, nu_max + 1))
        seeds = range(1, a.seeds + 1)
        tally, mism, samples = sweep(cname, nu_list, seeds, a.cases)
        total = sum(tally.values())
        print("=" * 78)
        print("%s  n=%d t=%d | ν ∈ [%d, %d] × seed 1..%d = %d 次"
              % (cname, n, t, t + 1, nu_max, a.seeds, total))
        for k in ("OK_正确", "OK_误纠", "FAIL②", "FAIL③", "FAIL④"):
            if tally.get(k):
                print("  %-8s %5d  (%.1f%%)" % (k, tally[k], 100.0 * tally[k] / total))
        print("  ③/④ 等价性反例：%d 条" % len(mism))
        for r in mism[:5]:
            print("     nu=%d seed=%d L=%d roots=%d degΩ=%d ω≥L=%s S'全0=%s"
                  % (r["nu"], r["seed"], r["L"], r["roots"], r["deg_omega"],
                     r["omega_ge_L"], r["post_s_zero"]))
        for k, lst in sorted(samples.items()):
            for r in lst:
                print("  · %-8s nu=%-3d seed=%-4d L=%-3d 根数=%d%s"
                      % (k, r["nu"], r["seed"], r["L"], r["roots"],
                         ("  位置=%s" % r.get("pos")) if r.get("pos") else ""))
    print("=" * 78)


if __name__ == "__main__":
    main()
