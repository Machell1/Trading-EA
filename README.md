# Trading-EA

MetaTrader 5 Expert Advisor implementing the **Triple-EMA + CCI + MACD Histogram** pullback strategy from the Trader DNA video ["The Most Accurate EMA Settings Ever"](https://youtu.be/_Wr57vS9ADM).

- MT5 EA source: [`Experts/EmaCciMacdEA.mq5`](Experts/EmaCciMacdEA.mq5)
- TradingView backtest version: [`TradingView/EmaCciMacdStrategy.pine`](TradingView/EmaCciMacdStrategy.pine)

## Strategy rules (as taught in the video)

The system stacks three confirmations: **trend** (EMAs), **momentum trigger** (CCI), and **trend-strength filter** (MACD histogram).

### Buy setup

1. **Trend filter** – price is above the slow EMA (and optionally the EMAs are stacked bullish: fast > mid > slow).
2. **Pullback (arming)** – price pulls back and touches the **fast EMA** while the **CCI drops below −100** (oversold). The setup is now "armed" for a limited number of bars.
3. **Entry trigger** – on a closed bar, the **CCI crosses back above the zero line**, price closes back above the fast EMA, and the **MACD histogram is above zero** (bulls still in control). → Open a buy.
4. **Stop loss** – just **below the mid EMA** (plus a buffer). **Take profit** – an R-multiple of the stop distance (default 2R).

### Sell setup

Exact mirror: downtrend below the slow EMA, pullback up to the fast EMA with CCI above +100, entry when CCI crosses below zero with the MACD histogram below zero, stop just above the mid EMA.

### The "secret" the video is really about: tuning the EMA periods

The video's core message is that **there is no universal EMA setting**. You must find the periods that *your* symbol and timeframe actually respect (clean, repeated bounces off the line). The video's own examples use different sets on different charts:

| Example from the video | Fast | Mid | Slow |
|---|---|---|---|
| Buy case study | 60 | 125 | 250 |
| Multi-EMA chart | 50 | 110 | 250 |
| Sell case study | 40 | 120 | 350 |

All periods are EA inputs, so use the MT5 **Strategy Tester optimizer** to find the combination your market respects before trading it.

### How to find your own EMA periods (the video's method)

1. Open your symbol on the timeframe you plan to trade and add a single EMA.
2. Test periods one by one — the video walks through **20 → 34 → 50 → 75 → 100 → 150 → 200** (and beyond, e.g. 250, 350).
3. For each period, look at how price behaves at the line: you want **clean, repeated bounces** — price touching the EMA and rejecting like it hit a wall, in both recent and older data.
4. Keep the period that gets respected most consistently. That becomes your **fast EMA** (the bounce/entry line).
5. Repeat to find a deeper level that catches price when the fast EMA breaks — that's your **mid EMA** (also your stop-loss line).
6. Find the deepest level that defines the overall trend (the video uses 250 or 350 instead of the usual 200) — that's your **slow EMA**. A break of this line means the trend itself may be flipping.
7. Re-do this per symbol **and** per timeframe — a set that works on EURUSD H1 will not automatically work on GBPUSD M15.

With the EA/Pine script you can automate this instead of eyeballing: optimize `InpFastEmaPeriod`, `InpMidEmaPeriod`, `InpSlowEmaPeriod` in the Strategy Tester and pick the region of settings (not a single lucky value) that performs consistently.

### Indicator settings used by the strategy (defaults)

| Indicator | Setting | Value | Where it's used |
|---|---|---|---|
| Fast EMA | period / price | 60, close | Pullback bounce line, entry confirmation |
| Mid EMA | period / price | 125, close | Stop-loss line |
| Slow EMA | period / price | 250, close | Trend filter |
| CCI | period / price | 20, typical (HLC/3) | ±100 zones arm the setup, zero-line cross triggers entry |
| MACD | fast / slow / signal | 12 / 26 / 9, close | Histogram above/below zero confirms trend strength |

The CCI ±100 zones and the standard 12/26/9 MACD are used exactly as shown in the video; only the EMA periods are meant to be re-tuned per chart.

## Installation

1. Open MetaTrader 5 and go to **File → Open Data Folder**.
2. Copy `Experts/EmaCciMacdEA.mq5` into `MQL5/Experts/`.
3. Open MetaEditor (F4), locate the file in the Navigator, and press **F7** to compile (or just restart MT5 — it compiles `.mq5` files in `Experts` automatically).
4. In MT5, enable **Algo Trading**, then drag **EmaCciMacdEA** from the Navigator onto a chart and allow live trading in the dialog.

## Inputs

### EMA settings
| Input | Default | Description |
|---|---|---|
| `InpFastEmaPeriod` | 60 | Fast EMA — the bounce/pullback line |
| `InpMidEmaPeriod` | 125 | Mid EMA — the stop-loss line |
| `InpSlowEmaPeriod` | 250 | Slow EMA — the trend filter |
| `InpRequireStacking` | true | Require EMAs ordered fast>mid>slow (bull) / fast<mid<slow (bear) |

### CCI / MACD
| Input | Default | Description |
|---|---|---|
| `InpCciPeriod` | 20 | CCI period |
| `InpCciZone` | 100 | Overbought/oversold level (±) |
| `InpUseMacdFilter` | true | Require MACD histogram on the trend side of zero |
| `InpMacdFast/Slow/Signal` | 12/26/9 | Standard MACD parameters |

### Setup logic
| Input | Default | Description |
|---|---|---|
| `InpSetupExpiryBars` | 12 | How many bars an armed pullback setup stays valid |
| `InpTouchTolerancePts` | 0 | Extra tolerance (points) for the fast-EMA touch |

### Risk management
| Input | Default | Description |
|---|---|---|
| `InpLotMode` | Risk % | Fixed lots or risk-% position sizing |
| `InpFixedLot` | 0.10 | Lot size in fixed mode |
| `InpRiskPercent` | 1.0 | % of balance risked per trade in risk mode |
| `InpSlBufferPts` | 30 | SL buffer beyond the mid EMA (points) |
| `InpTakeProfitRR` | 2.0 | TP as an R-multiple of the SL distance (0 = no TP) |
| `InpExitOnOpposite` | true | Close an open position when the opposite signal fires |
| `InpUseBreakEven` | true | Move SL to break-even after `InpBreakEvenRR` × risk in profit |
| `InpBreakEvenRR` / `InpBreakEvenLockPts` | 1.0 / 5 | Break-even trigger and locked-in points |

### Trade management
| Input | Default | Description |
|---|---|---|
| `InpMagicNumber` | 57120250 | Magic number identifying this EA's trades |
| `InpMaxSpreadPts` | 50 | Skip signals when spread exceeds this (0 = ignore) |
| `InpStartHour` / `InpEndHour` | 0 / 24 | Server-time trading window (supports overnight windows) |

## Behaviour notes

- Signals are evaluated **once per bar, on closed bars only** — no repainting, no intra-bar flip-flopping.
- The EA holds **one position per symbol at a time**.
- Lot size is normalized to the broker's min/max/step volume, and the stop respects the broker's minimum stop level.
- Works on any symbol/timeframe; the strategy was demonstrated on forex but the video claims it applies to stocks and crypto as well.

## TradingView backtesting (Pine Script)

`TradingView/EmaCciMacdStrategy.pine` is a Pine Script v6 port of the EA with identical logic (same arming state machine, CCI zero-line trigger, MACD filter, mid-EMA stop, R-multiple TP, break-even, session filter). To use it:

1. Open TradingView, open the **Pine Editor**, paste the file contents, and click **Add to chart**.
2. Open the **Strategy Tester** tab to see the equity curve, trade list, and performance stats.
3. Tune the EMA periods per symbol/timeframe exactly as with the EA (the inputs mirror the EA inputs one-to-one).

Two intentional differences from TradingView defaults, to match MT5 behaviour:

- **Histogram definition** – MT5 draws the MACD *main line* as the histogram, while TradingView's classic histogram is MACD − signal. The script defaults to MT5-style; you can switch in the inputs.
- **Sizing** – "Risk % of equity" mode assumes your account currency is the quote currency of the symbol (e.g. USD account on EURUSD), which is how most forex backtests are set up.

### Commission percentage to simulate MT5 costs

The script sets `commission_type = percent` with a default of **0.005% per side**, which approximates a typical MT5 forex account:

| MT5 cost component | Typical value | As % of notional per side |
|---|---|---|
| ECN/raw commission | $6–7 per standard lot ($100k) round turn | ~0.003–0.0035% |
| Raw spread (EURUSD) | 0.1–0.3 pips | ~0.001–0.003% |
| **Total (raw/ECN account)** | | **~0.004–0.005%** |
| Standard (spread-only) account | 1.0–1.5 pip spread, no commission | ~0.005–0.0075% |

Adjust it under **Settings → Properties → Commission** for your broker:

- Raw/ECN account: 0.004–0.005%
- Standard spread-only account: 0.005–0.0075%
- Indices/metals/crypto CFDs: convert your broker's typical spread to a percentage of price (spread ÷ price × 100) and add any per-trade commission.

The script also applies 2 ticks of slippage per fill by default.

## MT5 backtesting / optimization

1. Open the Strategy Tester (Ctrl+R), select **EmaCciMacdEA**, your symbol and timeframe, and "Every tick based on real ticks" for realistic results.
2. Optimize the three EMA periods first (e.g. fast 20–80, mid 90–150, slow 200–350), then fine-tune `InpSetupExpiryBars` and `InpTakeProfitRR`.
3. Forward-test on a **demo account** before risking real money.

## Disclaimer

This EA is provided for educational purposes. The video's claims ("almost always wins") are marketing — no strategy wins consistently without proper testing and risk management. Trading leveraged products involves substantial risk of loss. Always backtest and demo-trade first.
