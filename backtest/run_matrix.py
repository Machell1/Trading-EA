"""Run the EmaCciMacdEA backtest matrix over all pulled symbols/timeframes.

Configs: the EA defaults (video set A 60/125/250) + the video's other two EMA
sets, ablations on set A, an optimistic break-even bound, and cost stress.
70/30 chronological in-sample / out-of-sample split per symbol-timeframe.
"""
import json
import os
import sys
from dataclasses import replace

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Config, SymbolSpec, run_backtest  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
RESULTS = os.path.join(BASE, "results")
os.makedirs(RESULTS, exist_ok=True)

SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "XAUUSD", "XAGUSD",
    "BTCUSD", "ETHUSD", "SOLUSD",
    "Volatility 75 Index", "Volatility 100 Index", "Step Index",
    "US Tech 100", "US SP 500", "Wall Street 30", "Germany 40",
]
TIMEFRAMES = ["H1", "M15"]

CONFIGS = {
    # the three EMA sets shown in the video (all other inputs = EA defaults)
    "setA_60_125_250": Config(fast_ema=60, mid_ema=125, slow_ema=250),
    "setB_50_110_250": Config(fast_ema=50, mid_ema=110, slow_ema=250),
    "setC_40_120_350": Config(fast_ema=40, mid_ema=120, slow_ema=350),
    # ablations on set A (robustness scans, labeled as such — not tuning)
    "A_macd_off": Config(use_macd_filter=False),
    "A_be_off": Config(use_break_even=False),
    "A_stack_off": Config(require_stacking=False),
    "A_tp3": Config(take_profit_rr=3.0),
    "A_be_optimistic": Config(be_intrabar=True),
}
COST_STRESS = {"setA_x0spread": 0.0, "setA_x2spread": 2.0}  # on set A


def summarize(trades: pd.DataFrame, label: dict) -> list[dict]:
    rows = []
    for split_name, part in trades.groupby("split") if len(trades) else []:
        r = part["r_mult"].to_numpy()
        n = len(r)
        eq = np.cumsum(r)
        dd = float((np.maximum.accumulate(eq) - eq).max()) if n else 0.0
        gross_w = r[r > 0].sum()
        gross_l = -r[r <= 0].sum()
        rows.append({
            **label, "split": split_name, "n": n,
            "total_R": round(float(r.sum()), 2),
            "avg_R": round(float(r.mean()), 4) if n else np.nan,
            "win_pct": round(float((r > 0).mean() * 100), 1) if n else np.nan,
            "t_stat": round(float(r.mean() / r.std(ddof=1) * np.sqrt(n)), 2) if n > 2 and r.std(ddof=1) > 0 else np.nan,
            "profit_factor": round(float(gross_w / gross_l), 2) if gross_l > 0 else np.inf,
            "maxDD_R": round(dd, 1),
            "n_long": int((part["direction"] > 0).sum()),
            "n_short": int((part["direction"] < 0).sum()),
        })
    return rows


def main() -> int:
    with open(os.path.join(DATA, "symbols_info.json")) as f:
        specs = json.load(f)

    all_rows = []
    all_trades = []
    for sym in SYMBOLS:
        sp = specs.get(sym)
        if sp is None:
            continue
        for tf in TIMEFRAMES:
            path = os.path.join(DATA, f"{sym.replace(' ', '_')}_{tf}.csv")
            if not os.path.exists(path):
                continue
            df = pd.read_csv(path, parse_dates=["time"])
            split_i = int(len(df) * 0.7)

            runs = {}
            for name, cfg in CONFIGS.items():
                runs[name] = (cfg, 1.0)
            for name, mult in COST_STRESS.items():
                runs[name] = (CONFIGS["setA_60_125_250"], mult)

            for name, (cfg, spread_mult) in runs.items():
                spec = SymbolSpec(
                    point=sp["point"],
                    spread_price=sp["spread_price"] * spread_mult,
                    stops_level_points=sp["stops_level_points"],
                )
                trades = run_backtest(df, spec, cfg)
                if len(trades):
                    trades["split"] = np.where(trades["entry_i"] < split_i, "IS", "OOS")
                    trades["symbol"], trades["tf"], trades["config"] = sym, tf, name
                    if name.startswith("set"):
                        all_trades.append(trades)
                label = {"symbol": sym, "tf": tf, "config": name}
                rows = summarize(trades, label)
                if not rows:
                    rows = [{**label, "split": s, "n": 0} for s in ("IS", "OOS")]
                all_rows.extend(rows)
            print(f"done {sym} {tf}", flush=True)

    summary = pd.DataFrame(all_rows)
    summary.to_csv(os.path.join(RESULTS, "summary.csv"), index=False)
    if all_trades:
        pd.concat(all_trades, ignore_index=True).to_csv(
            os.path.join(RESULTS, "trades_main_sets.csv"), index=False)

    # pooled views
    for cfg_name in list(CONFIGS) + list(COST_STRESS):
        for split in ("IS", "OOS"):
            part = summary[(summary["config"] == cfg_name) & (summary["split"] == split) & (summary["n"] > 0)]
            if not len(part):
                continue
            n = part["n"].sum()
            tot = part["total_R"].sum()
            print(f"POOLED {cfg_name:18s} {split:3s}  trades={n:5d}  total_R={tot:8.1f}  "
                  f"avg_R={tot / n:7.4f}  symbols_positive={int((part['total_R'] > 0).sum())}/{len(part)}")
    return 0


if __name__ == "__main__":
    main()
