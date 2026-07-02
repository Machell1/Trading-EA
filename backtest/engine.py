"""Faithful bar-close Python port of Experts/EmaCciMacdEA.mq5 (Trading-EA repo).

Replicates the EA's OnTick new-bar logic exactly:
  - trend filter: close[1] vs slow EMA[1], optional EMA stacking
  - arming state machine: fast-EMA touch + CCI beyond +/-zone, expiry in bars,
    disarm on trend loss (same evaluation order as the EA)
  - trigger: CCI zero-line cross on closed bar + close vs fast EMA + MACD filter
    (MACD "histogram" = MT5 iMACD buffer 0 = MAIN line = EMA12-EMA26, exactly
    what the EA's CopyBuffer(handle, 0, ...) reads)
  - SL beyond mid EMA with buffer, broker min-stop widening, geometry-invalid skip
  - TP at an R-multiple of the stop distance
  - break-even move at 1R (EA does this per tick; here it activates on the bar
    AFTER the 1R touch — the conservative bar approximation)
  - exit-on-opposite-signal, with same-bar reversal (the EA closes then opens
    on the same tick)
  - one position at a time

Prices: MT5 candles are BID. ask = bid + spread (constant per symbol).
BUY enters at ask, exits at bid. SELL enters at bid, exits at ask.
Pessimistic intrabar rule: SL and TP both inside one bar -> SL.
Results are reported in R multiples (risk-normalized), like all prior audits.
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- indicators
def ema(x: np.ndarray, period: int) -> np.ndarray:
    """MT5-style EMA: alpha = 2/(period+1), seeded with the first value."""
    alpha = 2.0 / (period + 1.0)
    return pd.Series(x).ewm(alpha=alpha, adjust=False).mean().to_numpy()


def cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Classic/MT5 CCI on typical price: (TP - SMA) / (0.015 * mean |TP - SMA_current|)."""
    tp = (high + low + close) / 3.0
    n = len(tp)
    out = np.full(n, np.nan)
    if n < period:
        return out
    win = np.lib.stride_tricks.sliding_window_view(tp, period)  # shape (n-period+1, period)
    sma = win.mean(axis=1)
    md = np.abs(win - sma[:, None]).mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        vals = (tp[period - 1:] - sma) / (0.015 * md)
    vals = np.where(md > 0, vals, 0.0)
    out[period - 1:] = vals
    return out


def macd_main(close: np.ndarray, fast: int, slow: int) -> np.ndarray:
    """MT5 iMACD buffer 0 (the 'histogram' the EA reads) = fast EMA - slow EMA."""
    return ema(close, fast) - ema(close, slow)


# ---------------------------------------------------------------- config
@dataclass
class Config:
    fast_ema: int = 60
    mid_ema: int = 125
    slow_ema: int = 250
    require_stacking: bool = True
    cci_period: int = 20
    cci_zone: float = 100.0
    use_macd_filter: bool = True
    macd_fast: int = 12
    macd_slow: int = 26
    setup_expiry_bars: int = 12
    touch_tolerance_pts: float = 0.0
    sl_buffer_pts: float = 30.0
    take_profit_rr: float = 2.0
    exit_on_opposite: bool = True
    use_break_even: bool = True
    break_even_rr: float = 1.0
    break_even_lock_pts: float = 5.0
    # break-even timing: False = activates the bar AFTER the 1R touch
    # (conservative); True = active within the touch bar (optimistic bound)
    be_intrabar: bool = False


@dataclass
class SymbolSpec:
    point: float
    spread_price: float       # ask - bid, in price units
    stops_level_points: float  # broker min stop distance, in points


@dataclass
class Trade:
    direction: int            # +1 buy, -1 sell
    entry_i: int
    entry_time: object
    entry_px: float
    sl: float
    tp: float
    risk: float               # |entry - initial SL| in price units
    exit_i: int = -1
    exit_time: object = None
    exit_px: float = np.nan
    exit_reason: str = ""
    r_mult: float = np.nan
    be_armed: bool = False    # 1R touched on a previous bar -> SL at BE
    be_touched_bar: int = -1  # bar index where 1R was first touched


# ---------------------------------------------------------------- backtest
def run_backtest(df: pd.DataFrame, spec: SymbolSpec, cfg: Config) -> pd.DataFrame:
    """df: columns time, open, high, low, close (bid OHLC). Returns trades DataFrame."""
    t = df["time"].to_numpy()
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    n = len(df)

    fast = ema(c, cfg.fast_ema)
    mid = ema(c, cfg.mid_ema)
    slow = ema(c, cfg.slow_ema)
    cci_v = cci(h, l, c, cfg.cci_period)
    macd_v = macd_main(c, cfg.macd_fast, cfg.macd_slow)

    point = spec.point
    spread = spec.spread_price
    tol = cfg.touch_tolerance_pts * point
    buffer = cfg.sl_buffer_pts * point
    min_stop = spec.stops_level_points * point
    lock = cfg.break_even_lock_pts * point

    warmup = max(cfg.slow_ema * 4, cfg.cci_period + 2, cfg.macd_slow * 4, 300)

    buy_armed = False
    buy_age = 0
    sell_armed = False
    sell_age = 0
    pos: Optional[Trade] = None
    trades: list[Trade] = []

    def close_position(trade: Trade, i: int, px: float, reason: str):
        trade.exit_i = i
        trade.exit_time = t[i]
        trade.exit_px = px
        trade.exit_reason = reason
        trade.r_mult = trade.direction * (px - trade.entry_px) / trade.risk
        trades.append(trade)

    def open_position(direction: int, i: int, mid_ema_val: float) -> Optional[Trade]:
        if direction > 0:
            price = o[i] + spread          # buy at ask
            sl = mid_ema_val - buffer
            if sl >= price:
                return None                # geometry invalid, EA skips
        else:
            price = o[i]                   # sell at bid
            sl = mid_ema_val + buffer
            if sl <= price:
                return None
        sl_dist = abs(price - sl)
        if sl_dist < min_stop:             # EA widens to broker min stop
            sl_dist = min_stop
            sl = price - sl_dist if direction > 0 else price + sl_dist
        tp = 0.0
        if cfg.take_profit_rr > 0:
            tp = price + direction * sl_dist * cfg.take_profit_rr
        return Trade(direction=direction, entry_i=i, entry_time=t[i],
                     entry_px=price, sl=sl, tp=tp, risk=sl_dist)

    def simulate_bar(trade: Trade, i: int) -> bool:
        """Simulate intrabar SL/TP/BE for bar i. Returns True if closed."""
        # BE activation from a prior-bar 1R touch
        if cfg.use_break_even and trade.be_armed:
            be_sl = trade.entry_px + trade.direction * lock
            if trade.direction > 0:
                trade.sl = max(trade.sl, be_sl)
            else:
                trade.sl = min(trade.sl, be_sl)

        # gap-open fills: a bar that OPENS beyond the stop/target fills at the
        # open — the first available price — matching broker-side stop
        # semantics on weekend/session gaps (not applicable to the entry bar,
        # where the position is opened at this same open)
        if i > trade.entry_i:
            if trade.direction > 0:
                if o[i] <= trade.sl:
                    close_position(trade, i, min(trade.sl, o[i]), "gap_sl")
                    return True
                if trade.tp > 0 and o[i] >= trade.tp:
                    close_position(trade, i, o[i], "gap_tp")
                    return True
            else:
                if o[i] + spread >= trade.sl:
                    close_position(trade, i, max(trade.sl, o[i] + spread), "gap_sl")
                    return True
                if trade.tp > 0 and o[i] + spread <= trade.tp:
                    close_position(trade, i, o[i] + spread, "gap_tp")
                    return True

        if trade.direction > 0:  # exits at bid
            sl_hit = l[i] <= trade.sl
            tp_hit = trade.tp > 0 and h[i] >= trade.tp
            r_touch = h[i] >= trade.entry_px + trade.risk * cfg.break_even_rr
        else:                    # exits at ask = bid + spread
            sl_hit = h[i] + spread >= trade.sl
            tp_hit = trade.tp > 0 and l[i] + spread <= trade.tp
            r_touch = l[i] + spread <= trade.entry_px - trade.risk * cfg.break_even_rr

        # optimistic-bound variant: BE becomes active inside the touch bar
        if cfg.use_break_even and cfg.be_intrabar and r_touch and not trade.be_armed:
            be_sl = trade.entry_px + trade.direction * lock
            if trade.direction > 0 and not tp_hit:
                # after touching 1R the stop sits at BE; original-SL hit no longer possible
                if l[i] <= be_sl and trade.sl < be_sl:
                    sl_hit = True
                    trade.sl = max(trade.sl, be_sl)
                elif l[i] > be_sl:
                    sl_hit = False
                    trade.sl = max(trade.sl, be_sl)
            elif trade.direction < 0 and not tp_hit:
                if h[i] + spread >= be_sl and trade.sl > be_sl:
                    sl_hit = True
                    trade.sl = min(trade.sl, be_sl)
                elif h[i] + spread < be_sl:
                    sl_hit = False
                    trade.sl = min(trade.sl, be_sl)

        if sl_hit:               # pessimistic: SL wins when both hit
            close_position(trade, i, trade.sl, "sl_be" if trade.be_armed else "sl")
            return True
        if tp_hit:
            close_position(trade, i, trade.tp, "tp")
            return True
        if cfg.use_break_even and r_touch and not trade.be_armed:
            trade.be_armed = True
            trade.be_touched_bar = i
        return False

    for i in range(warmup, n):
        i1, i2 = i - 1, i - 2  # EA's rates[1] (last closed) and rates[2]
        if np.isnan(cci_v[i2]):
            continue

        close1 = c[i1]
        bull = close1 > slow[i1]
        bear = close1 < slow[i1]
        if cfg.require_stacking:
            bull = bull and (fast[i1] > mid[i1] > slow[i1])
            bear = bear and (fast[i1] < mid[i1] < slow[i1])

        # age/expire armed setups (same order as the EA)
        if buy_armed:
            buy_age += 1
            if buy_age > cfg.setup_expiry_bars:
                buy_armed = False
        if sell_armed:
            sell_age += 1
            if sell_age > cfg.setup_expiry_bars:
                sell_armed = False
        if not bull:
            buy_armed = False
        if not bear:
            sell_armed = False

        # arm on pullback touch of fast EMA with CCI in the opposite zone
        if bull and l[i1] <= fast[i1] + tol and cci_v[i1] < -cfg.cci_zone:
            buy_armed, buy_age = True, 0
        if bear and h[i1] >= fast[i1] - tol and cci_v[i1] > cfg.cci_zone:
            sell_armed, sell_age = True, 0

        cross_up = cci_v[i2] <= 0.0 < cci_v[i1]
        cross_dn = cci_v[i2] >= 0.0 > cci_v[i1]
        macd_bull_ok = (not cfg.use_macd_filter) or macd_v[i1] > 0.0
        macd_bear_ok = (not cfg.use_macd_filter) or macd_v[i1] < 0.0

        buy_sig = buy_armed and bull and cross_up and macd_bull_ok and close1 > fast[i1]
        sell_sig = sell_armed and bear and cross_dn and macd_bear_ok and close1 < fast[i1]

        # exit on opposite signal at this bar's open (EA closes on the open tick)
        if pos is not None and cfg.exit_on_opposite:
            if (pos.direction > 0 and sell_sig) or (pos.direction < 0 and buy_sig):
                px = o[i] if pos.direction > 0 else o[i] + spread
                close_position(pos, i, px, "opposite")
                pos = None

        # entries (EA: only when flat; armed flag is consumed on entry attempt)
        if pos is None:
            if buy_sig:
                buy_armed = False
                pos = open_position(+1, i, mid[i1])
            elif sell_sig:
                sell_armed = False
                pos = open_position(-1, i, mid[i1])

        # intrabar simulation for whatever position lives during bar i
        if pos is not None:
            if simulate_bar(pos, i):
                pos = None

    if pos is not None:  # mark-to-market close of a still-open position
        close_position(pos, n - 1, c[n - 1] if pos.direction > 0 else c[n - 1] + spread, "eod")

    if not trades:
        return pd.DataFrame(columns=["direction", "entry_time", "entry_px", "sl", "tp",
                                     "risk", "exit_time", "exit_px", "exit_reason", "r_mult"])
    return pd.DataFrame([{
        "direction": tr.direction, "entry_i": tr.entry_i, "entry_time": tr.entry_time,
        "entry_px": tr.entry_px, "sl": tr.sl, "tp": tr.tp, "risk": tr.risk,
        "exit_i": tr.exit_i, "exit_time": tr.exit_time, "exit_px": tr.exit_px,
        "exit_reason": tr.exit_reason, "r_mult": tr.r_mult,
    } for tr in trades])
