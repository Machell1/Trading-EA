# EmaCciMacdEA Backtest Report — 2026-07-01

**Verdict: NO TRADABLE EDGE. Do not fund. Do not attach to the live account.**

The Triple-EMA + CCI + MACD pullback strategy (Trader DNA, "The Most Accurate
EMA Settings Ever") was backtested on **real Deriv MT5 candle data** across 16
instruments × 2 timeframes with a verified, line-faithful Python port of
`Experts/EmaCciMacdEA.mq5`. All three EMA sets shown in the video lose money
out-of-sample at real spreads. The gross (frictionless) edge is ≈ zero
out-of-sample, so there is nothing for execution improvements to rescue.

## Method

- Data: pulled 2026-07-01 from the live Deriv terminal (login 62158975).
  50,000 H1 bars per symbol (≈8y FX/metals, ≈5.7y crypto/synthetics, ≈2.5y
  real indices) + ≈2y of M15. Bid OHLC; ask = bid + current live spread.
- Engine: bar-close port of the EA — identical arming state machine, CCI
  zero-cross trigger, MACD main-line filter (what the EA's
  `CopyBuffer(hMacd, 0, …)` actually reads), mid-EMA stop + 30pt buffer,
  min-stop widening, 2R TP, 1R break-even (activates the bar after the touch —
  conservative), exit-on-opposite with same-bar reversal, one position at a
  time. Pessimistic same-bar rule (SL and TP in one bar → SL). Gap opens fill
  at the open, not the stop level.
- Verification: 22-agent adversarial audit — line-by-line port fidelity,
  look-ahead hunt, MT5 indicator-math check, and an independent from-scratch
  replication that matched the engine's XAUUSD trade list exactly. 6 findings
  filed, 5 refuted, 1 confirmed (gap-through-SL fills, fixed before the final
  run; it had been flattering results by ~22R on the headline config).
- Split: 70/30 chronological in-sample / out-of-sample per symbol-timeframe.
  Results in R multiples (risk-normalized).

## Pooled results (32 symbol-timeframe datasets)

| Config | IS trades | IS total R | OOS trades | OOS total R | OOS avg R |
|---|---|---|---|---|---|
| Set A 60/125/250 (EA default) | 2,737 | +4.4 | 1,217 | **−49.4** | −0.041 |
| Set B 50/110/250 | 3,425 | −1.0 | 1,519 | **−51.2** | −0.034 |
| Set C 40/120/350 | 3,636 | −17.6 | 1,588 | **−19.5** | −0.012 |
| A + MACD filter off | 7,215 | −276.1 | 3,236 | −215.8 | −0.067 |
| A + break-even off | 2,596 | +29.8 | 1,158 | −47.0 | −0.041 |
| A + stacking off | 3,184 | −57.5 | 1,422 | −28.1 | −0.020 |
| A + TP 3R | 2,645 | +23.7 | 1,187 | −3.3 | −0.003 |
| A + per-tick-BE bound | 2,742 | −93.3 | 1,221 | −81.9 | −0.067 |
| A + zero spread | 2,736 | +122.1 | 1,221 | +5.5 | +0.005 |
| A + double spread | 2,736 | −97.8 | 1,215 | −103.1 | −0.085 |

Key readings:

1. **No net edge.** Every realistic config is negative out-of-sample. The
   best OOS pockets (BTCUSD M15 +14.8R t=1.9, Germany 40 H1 +8.3R on 15
   trades) all had **negative in-sample results** — noise, not signal.
2. **Cost-fragile gross edge.** Frictionless set A earns +0.045R/trade IS but
   only +0.005R/trade OOS. Even with zero spread the strategy is
   approximately break-even on unseen data; at real Deriv spreads it loses,
   and at 2× spread it loses heavily.
3. **The break-even "protection" hurts.** Removing BE improves IS by ~25R.
   The per-tick BE bound (closest to how the live EA actually behaves)
   is the *worst* realistic variant (OOS −81.9R): after 1R, any pullback
   scratches the trade and forfeits the 2R winners that pay for the losers.
4. **The MACD filter is the only component doing real work** (removing it
   roughly quadruples losses), but it only lifts the system from very
   negative to slightly negative.

## Live-deployment defects found in the EA (independent of the edge question)

- **`InpMaxSpreadPts = 50` is a raw-points gate and silently disables the EA
  on most Deriv symbols.** Current spreads: BTCUSD ≈18,600 pts, ETHUSD
  ≈158,000 pts, SOLUSD 140, Volatility 75 ≈1,349, US Tech 100 140,
  Wall Street 30 180, Germany 40 ≈990. Attached to any of those charts with
  defaults, the EA never trades and only logs skipped signals. It would only
  trade FX majors, XAUUSD/XAGUSD, US SP 500, Volatility 100, and Step Index.
- `InpSlBufferPts`/`InpBreakEvenLockPts` are also point-denominated, so their
  economic size varies by orders of magnitude across symbols.
- Risk-% sizing at the current $719 balance would floor at min-lot on most
  symbols, risking more than the configured 1% per trade (same class of bug
  as the min-lot issue fixed in the SMC EA on 2026-06-27).

## Bottom line

Same story as the previous YouTube-strategy audits (NASDAQ ORB, SMC, scalper
bots): the entry logic is not differentiated enough to overcome spread. If
you want to keep experimenting with it, the only leads the data even weakly
supports are (a) dropping break-even entirely and (b) crypto/M15 — but
neither showed IS/OOS consistency, so treat them as research directions, not
tradable signals.

*Harness: `backtest/` — `pull_data.py`, `engine.py`, `run_matrix.py`,
results in `backtest/results/`. Reproduce with
`python backtest/pull_data.py && python backtest/run_matrix.py`.*
