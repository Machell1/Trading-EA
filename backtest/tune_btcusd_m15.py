"""Per-asset tuning study: EmaCciMacdEA on BTCUSD M15 (the video's core claim).

Pre-registered design (written BEFORE any results were seen):
  - Grid: EMA fast {20,30,40,50,60,80} x mid {90,110,125,150} x slow
    {200,250,300,350} x CCI zone {100,150} x expiry {8,12,16} x BE {on,off}
    = 1152 configs. All other inputs = EA defaults. Real Deriv spread.
  - Selection: rank by IS t-stat on the FIRST 70% of bars, min 60 IS trades.
  - Test: the single IS winner is evaluated ONCE on the last 30% (OOS).
  - Gate 1: best IS t-stat must clear the expected max of N=1152 null trials
    (~sqrt(2 ln N) ~ 3.75; config correlation lowers effective N, so clearing
    3.0 is already marginal, below is plain noise).
  - Gate 2: winner OOS must be positive with t >= 2.
  - Gate 3: +/-1-step parameter neighborhood must also be IS-positive
    (plateau, not spike).
"""
import itertools
import json
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from engine import Config, SymbolSpec, run_backtest  # noqa: E402

DATA_CSV = os.path.join(BASE, "data", "BTCUSD_M15.csv")
SPECS = os.path.join(BASE, "data", "symbols_info.json")
OUT = os.path.join(BASE, "results", "tune_btcusd_m15.csv")

FASTS = [20, 30, 40, 50, 60, 80]
MIDS = [90, 110, 125, 150]
SLOWS = [200, 250, 300, 350]
ZONES = [100.0, 150.0]
EXPIRIES = [8, 12, 16]
BES = [True, False]

_df = None
_spec = None
_split = None


def _init():
    global _df, _spec, _split
    _df = pd.read_csv(DATA_CSV, parse_dates=["time"])
    with open(SPECS) as f:
        sp = json.load(f)["BTCUSD"]
    _spec = SymbolSpec(point=sp["point"], spread_price=sp["spread_price"],
                       stops_level_points=sp["stops_level_points"])
    _split = int(len(_df) * 0.7)


def _stats(r: np.ndarray) -> dict:
    n = len(r)
    if n == 0:
        return {"n": 0, "total_R": 0.0, "avg_R": np.nan, "t": np.nan, "win": np.nan}
    sd = r.std(ddof=1) if n > 2 else 0.0
    return {"n": n, "total_R": float(r.sum()), "avg_R": float(r.mean()),
            "t": float(r.mean() / sd * np.sqrt(n)) if sd > 0 else np.nan,
            "win": float((r > 0).mean() * 100)}


def run_one(params):
    fast, mid, slow, zone, expiry, be = params
    cfg = Config(fast_ema=fast, mid_ema=mid, slow_ema=slow, cci_zone=zone,
                 setup_expiry_bars=expiry, use_break_even=be)
    trades = run_backtest(_df, _spec, cfg)
    row = {"fast": fast, "mid": mid, "slow": slow, "zone": zone,
           "expiry": expiry, "be": be}
    if len(trades):
        is_r = trades.loc[trades["entry_i"] < _split, "r_mult"].to_numpy()
        oos_r = trades.loc[trades["entry_i"] >= _split, "r_mult"].to_numpy()
    else:
        is_r = oos_r = np.array([])
    row.update({f"is_{k}": v for k, v in _stats(is_r).items()})
    row.update({f"oos_{k}": v for k, v in _stats(oos_r).items()})
    return row


def main():
    grid = list(itertools.product(FASTS, MIDS, SLOWS, ZONES, EXPIRIES, BES))
    print(f"{len(grid)} configs, BTCUSD M15")
    with Pool(processes=8, initializer=_init) as pool:
        rows = []
        for k, row in enumerate(pool.imap_unordered(run_one, grid, chunksize=8)):
            rows.append(row)
            if (k + 1) % 100 == 0:
                print(f"{k + 1}/{len(grid)}", flush=True)
    res = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    res.to_csv(OUT, index=False)

    # ---- analysis (selection on IS only) ----
    n_trials = len(grid)
    hurdle = float(np.sqrt(2 * np.log(n_trials)))
    eligible = res[res["is_n"] >= 60].copy()
    ranked = eligible.sort_values("is_t", ascending=False)
    print(f"\nGate 1 hurdle (expected max |t| of {n_trials} null trials): ~{hurdle:.2f}")
    print("\nTOP 15 by IS t-stat (min 60 IS trades):")
    cols = ["fast", "mid", "slow", "zone", "expiry", "be",
            "is_n", "is_total_R", "is_t", "is_win",
            "oos_n", "oos_total_R", "oos_t", "oos_win"]
    print(ranked[cols].head(15).to_string(index=False))

    w = ranked.iloc[0]
    print(f"\nWINNER (selected on IS only): fast={w.fast} mid={w.mid} slow={w.slow} "
          f"zone={w.zone} expiry={w.expiry} be={w.be}")
    print(f"  IS : n={w.is_n:.0f} total={w.is_total_R:+.1f}R t={w.is_t:.2f}")
    print(f"  OOS: n={w.oos_n:.0f} total={w.oos_total_R:+.1f}R t={w.oos_t:.2f}")

    # Gate 3: +/-1-step neighborhood of the winner (same zone/expiry/be)
    def steps(vals, v):
        i = vals.index(v)
        return [vals[j] for j in (i - 1, i, i + 1) if 0 <= j < len(vals)]
    nb = res[res["fast"].isin(steps(FASTS, int(w.fast)))
             & res["mid"].isin(steps(MIDS, int(w.mid)))
             & res["slow"].isin(steps(SLOWS, int(w.slow)))
             & (res["zone"] == w.zone) & (res["expiry"] == w.expiry) & (res["be"] == w.be)]
    print(f"\nNeighborhood ({len(nb)} configs): "
          f"IS total_R mean={nb['is_total_R'].mean():+.1f} "
          f"({int((nb['is_total_R'] > 0).sum())}/{len(nb)} positive) | "
          f"OOS total_R mean={nb['oos_total_R'].mean():+.1f} "
          f"({int((nb['oos_total_R'] > 0).sum())}/{len(nb)} positive)")

    base = res[(res.fast == 60) & (res.mid == 125) & (res.slow == 250)
               & (res.zone == 100.0) & (res.expiry == 12) & (res.be == True)]  # noqa: E712
    if len(base):
        b = base.iloc[0]
        print(f"\nBaseline setA defaults: IS {b.is_total_R:+.1f}R (t={b.is_t:.2f}) | "
              f"OOS {b.oos_total_R:+.1f}R (t={b.oos_t:.2f})")


if __name__ == "__main__":
    main()
