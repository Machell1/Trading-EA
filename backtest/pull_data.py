"""Pull real candle history + symbol specs from the local Deriv MT5 terminal.

Saves per-symbol CSVs into backtest/data/ and a symbols_info.json with the
contract specs needed for faithful cost modeling.
"""
import json
import os
import sys

import MetaTrader5 as mt5
import pandas as pd

SYMBOLS = [
    # FX majors
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    # metals
    "XAUUSD", "XAGUSD",
    # crypto
    "BTCUSD", "ETHUSD", "SOLUSD",
    # Deriv synthetics (24/7, genuine volume-free trend behaviour)
    "Volatility 75 Index", "Volatility 100 Index", "Step Index",
    # real equity indices
    "US Tech 100", "US SP 500", "Wall Street 30", "Germany 40",
]

TIMEFRAMES = {
    "H1": mt5.TIMEFRAME_H1,
    "M15": mt5.TIMEFRAME_M15,
}

COUNT_LADDER = [200_000, 100_000, 50_000, 20_000, 10_000, 5_000, 2_000]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def safe_name(symbol: str) -> str:
    return symbol.replace(" ", "_")


def main() -> int:
    if not mt5.initialize():
        print(f"MT5 initialize failed: {mt5.last_error()}")
        return 1

    acct = mt5.account_info()
    print(f"Connected: login={acct.login} server={acct.server} balance={acct.balance}")

    info_out = {}
    for sym in SYMBOLS:
        if not mt5.symbol_select(sym, True):
            print(f"  !! cannot select {sym}: {mt5.last_error()}")
            continue
        si = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        spread_price = (tick.ask - tick.bid) if (tick and tick.ask > 0) else si.spread * si.point
        info_out[sym] = {
            "point": si.point,
            "digits": si.digits,
            "spread_points": si.spread,
            "spread_price": spread_price,
            "stops_level_points": si.trade_stops_level,
            "tick_size": si.trade_tick_size,
            "tick_value": si.trade_tick_value,
            "volume_min": si.volume_min,
            "volume_step": si.volume_step,
            "bid": tick.bid if tick else None,
            "ask": tick.ask if tick else None,
        }

        for tf_name, tf in TIMEFRAMES.items():
            rates = None
            for count in COUNT_LADDER:
                rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
                if rates is not None and len(rates) > 0:
                    break
            if rates is None or len(rates) == 0:
                print(f"  !! no {tf_name} data for {sym}: {mt5.last_error()}")
                continue
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            path = os.path.join(DATA_DIR, f"{safe_name(sym)}_{tf_name}.csv")
            df.to_csv(path, index=False)
            print(f"  {sym} {tf_name}: {len(df)} bars  {df['time'].iloc[0]} -> {df['time'].iloc[-1]}")

    with open(os.path.join(DATA_DIR, "symbols_info.json"), "w") as f:
        json.dump(info_out, f, indent=2)
    print(f"Saved specs for {len(info_out)} symbols.")

    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
