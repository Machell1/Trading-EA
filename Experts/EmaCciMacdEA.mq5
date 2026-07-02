//+------------------------------------------------------------------+
//|                                                 EmaCciMacdEA.mq5 |
//|      Triple-EMA + CCI + MACD Histogram pullback Expert Advisor   |
//|                                                                  |
//|  Strategy (from Trader DNA, "The Most Accurate EMA Settings      |
//|  Ever" - youtu.be/_Wr57vS9ADM):                                  |
//|                                                                  |
//|  BUY setup                                                       |
//|   1. Trend is bullish: price trades above the slow EMA           |
//|      (optionally the EMAs must be stacked fast > mid > slow).    |
//|   2. Price pulls back and touches the fast EMA while CCI dips    |
//|      into the oversold zone (below -100). The setup is "armed".  |
//|   3. Entry trigger: CCI crosses back above the zero line on a    |
//|      closed bar, price closes back above the fast EMA, and the   |
//|      MACD histogram is above zero (bulls still in control).      |
//|   4. Stop loss: just below the mid EMA. Take profit: R-multiple  |
//|      of the stop distance.                                       |
//|                                                                  |
//|  SELL setup is the exact mirror: pullback up to the fast EMA     |
//|  with CCI above +100, entry when CCI crosses below zero with     |
//|  the MACD histogram below zero, stop just above the mid EMA.     |
//|                                                                  |
//|  The video stresses that EMA periods are NOT universal: they     |
//|  must be tuned per symbol/timeframe by checking which periods    |
//|  price cleanly bounces off. All periods are inputs - use the     |
//|  MT5 Strategy Tester optimizer to find the ones your market      |
//|  respects (video examples: 60/125/250, 50/110/250, 40/120/350).  |
//+------------------------------------------------------------------+
#property copyright   "Cursor Agent"
#property link        "https://youtu.be/_Wr57vS9ADM"
#property version     "1.00"
#property description "Triple-EMA trend + CCI zero-line trigger + MACD histogram filter."
#property description "Pullback-continuation EA based on the Trader DNA EMA/CCI/MACD system."

#include <Trade\Trade.mqh>

//--- lot sizing modes
enum ENUM_LOT_MODE
  {
   LOT_FIXED = 0,     // Fixed lot size
   LOT_RISK_PERCENT   // Risk % of balance per trade
  };

//+------------------------------------------------------------------+
//| Inputs                                                           |
//+------------------------------------------------------------------+
input group "=== EMA settings (tune per symbol/timeframe!) ==="
input int      InpFastEmaPeriod    = 60;          // Fast EMA period (bounce line)
input int      InpMidEmaPeriod     = 125;         // Mid EMA period (stop-loss line)
input int      InpSlowEmaPeriod    = 250;         // Slow EMA period (trend line)
input bool     InpRequireStacking  = true;        // Require EMAs stacked in trend order

input group "=== CCI settings ==="
input int      InpCciPeriod        = 20;          // CCI period
input double   InpCciZone          = 100.0;       // CCI overbought/oversold level (+/-)

input group "=== MACD histogram filter ==="
input bool     InpUseMacdFilter    = true;        // Use MACD histogram confirmation
input int      InpMacdFast         = 12;          // MACD fast EMA
input int      InpMacdSlow         = 26;          // MACD slow EMA
input int      InpMacdSignal       = 9;           // MACD signal period

input group "=== Setup logic ==="
input int      InpSetupExpiryBars  = 12;          // Bars a pullback setup stays armed
input double   InpTouchTolerancePts= 0.0;         // Extra tolerance around fast EMA (points)

input group "=== Risk management ==="
input ENUM_LOT_MODE InpLotMode     = LOT_RISK_PERCENT; // Lot sizing mode
input double   InpFixedLot         = 0.10;        // Fixed lot size
input double   InpRiskPercent      = 1.0;         // Risk % of balance per trade
input double   InpSlBufferPts      = 30.0;        // SL buffer beyond mid EMA (points)
input double   InpTakeProfitRR     = 2.0;         // Take profit (R multiple, 0 = none)
input bool     InpExitOnOpposite   = true;        // Close position on opposite signal
input bool     InpUseBreakEven     = true;        // Move SL to break-even
input double   InpBreakEvenRR      = 1.0;         // Break-even trigger (R multiple)
input double   InpBreakEvenLockPts = 5.0;         // Points locked in at break-even

input group "=== Trade management ==="
input long     InpMagicNumber      = 57120250;    // Magic number
input int      InpMaxSpreadPts     = 50;          // Max spread to trade (points, 0 = ignore)
input string   InpTradeComment     = "EmaCciMacd";// Order comment

input group "=== Trading hours (server time, 0-24 = always) ==="
input int      InpStartHour        = 0;           // Trading start hour
input int      InpEndHour          = 24;          // Trading end hour

//+------------------------------------------------------------------+
//| Globals                                                          |
//+------------------------------------------------------------------+
CTrade   g_trade;
int      g_hFastEma  = INVALID_HANDLE;
int      g_hMidEma   = INVALID_HANDLE;
int      g_hSlowEma  = INVALID_HANDLE;
int      g_hCci      = INVALID_HANDLE;
int      g_hMacd     = INVALID_HANDLE;
datetime g_lastBarTime = 0;

// Pullback state machine: setup gets "armed" when price touches the
// fast EMA while CCI is in the opposite-extreme zone, then fires on
// the CCI zero-line cross (or expires after InpSetupExpiryBars bars).
bool g_buyArmed        = false;
int  g_buyArmedBarsAgo = 0;
bool g_sellArmed        = false;
int  g_sellArmedBarsAgo = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpFastEmaPeriod >= InpMidEmaPeriod || InpMidEmaPeriod >= InpSlowEmaPeriod)
     {
      Print("Invalid EMA periods: require fast < mid < slow.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpCciPeriod < 2 || InpCciZone <= 0.0)
     {
      Print("Invalid CCI settings.");
      return(INIT_PARAMETERS_INCORRECT);
     }

   g_hFastEma = iMA(_Symbol, _Period, InpFastEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_hMidEma  = iMA(_Symbol, _Period, InpMidEmaPeriod,  0, MODE_EMA, PRICE_CLOSE);
   g_hSlowEma = iMA(_Symbol, _Period, InpSlowEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_hCci     = iCCI(_Symbol, _Period, InpCciPeriod, PRICE_TYPICAL);
   g_hMacd    = iMACD(_Symbol, _Period, InpMacdFast, InpMacdSlow, InpMacdSignal, PRICE_CLOSE);

   if(g_hFastEma == INVALID_HANDLE || g_hMidEma == INVALID_HANDLE ||
      g_hSlowEma == INVALID_HANDLE || g_hCci == INVALID_HANDLE ||
      g_hMacd == INVALID_HANDLE)
     {
      Print("Failed to create indicator handles.");
      return(INIT_FAILED);
     }

   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_trade.SetDeviationInPoints(20);

   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_hFastEma != INVALID_HANDLE) IndicatorRelease(g_hFastEma);
   if(g_hMidEma  != INVALID_HANDLE) IndicatorRelease(g_hMidEma);
   if(g_hSlowEma != INVALID_HANDLE) IndicatorRelease(g_hSlowEma);
   if(g_hCci     != INVALID_HANDLE) IndicatorRelease(g_hCci);
   if(g_hMacd    != INVALID_HANDLE) IndicatorRelease(g_hMacd);
  }

//+------------------------------------------------------------------+
//| Expert tick handler                                              |
//+------------------------------------------------------------------+
void OnTick()
  {
   ManageOpenPosition();

   if(!IsNewBar())
      return;

   //--- indicator values on the two most recent CLOSED bars
   double fast[], mid[], slow[], cci[], macdHist[];
   if(!CopyIndicator(g_hFastEma, 0, fast) ||
      !CopyIndicator(g_hMidEma,  0, mid)  ||
      !CopyIndicator(g_hSlowEma, 0, slow) ||
      !CopyIndicator(g_hCci,     0, cci)  ||
      !CopyIndicator(g_hMacd,    0, macdHist))
      return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, 4, rates) < 4)
      return;

   // index 1 = last closed bar, index 2 = the bar before it
   const double close1 = rates[1].close;
   const double low1   = rates[1].low;
   const double high1  = rates[1].high;
   const double tol    = InpTouchTolerancePts * _Point;

   //--- trend direction
   bool bullTrend = close1 > slow[1];
   bool bearTrend = close1 < slow[1];
   if(InpRequireStacking)
     {
      bullTrend = bullTrend && (fast[1] > mid[1] && mid[1] > slow[1]);
      bearTrend = bearTrend && (fast[1] < mid[1] && mid[1] < slow[1]);
     }

   //--- age / expire armed setups
   if(g_buyArmed  && ++g_buyArmedBarsAgo  > InpSetupExpiryBars) g_buyArmed  = false;
   if(g_sellArmed && ++g_sellArmedBarsAgo > InpSetupExpiryBars) g_sellArmed = false;
   if(!bullTrend) g_buyArmed  = false;
   if(!bearTrend) g_sellArmed = false;

   //--- arm setups: pullback touches the fast EMA while CCI is in the zone
   if(bullTrend && low1 <= fast[1] + tol && cci[1] < -InpCciZone)
     {
      g_buyArmed        = true;
      g_buyArmedBarsAgo = 0;
     }
   if(bearTrend && high1 >= fast[1] - tol && cci[1] > InpCciZone)
     {
      g_sellArmed        = true;
      g_sellArmedBarsAgo = 0;
     }

   //--- entry triggers: CCI zero-line cross on the closed bar
   bool cciCrossUp   = (cci[2] <= 0.0 && cci[1] > 0.0);
   bool cciCrossDown = (cci[2] >= 0.0 && cci[1] < 0.0);
   bool macdBullOk = !InpUseMacdFilter || macdHist[1] > 0.0;
   bool macdBearOk = !InpUseMacdFilter || macdHist[1] < 0.0;

   bool buySignal  = g_buyArmed  && bullTrend && cciCrossUp   && macdBullOk && close1 > fast[1];
   bool sellSignal = g_sellArmed && bearTrend && cciCrossDown && macdBearOk && close1 < fast[1];

   //--- optional exit on opposite signal
   if(InpExitOnOpposite && PositionSelectByMagic())
     {
      long posType = PositionGetInteger(POSITION_TYPE);
      if((posType == POSITION_TYPE_BUY && sellSignal) ||
         (posType == POSITION_TYPE_SELL && buySignal))
         g_trade.PositionClose(_Symbol);
     }

   if(!TradingAllowedNow())
      return;
   if(PositionSelectByMagic())   // one position at a time
      return;

   if(buySignal)
     {
      g_buyArmed = false;
      OpenTrade(ORDER_TYPE_BUY, mid[1]);
     }
   else if(sellSignal)
     {
      g_sellArmed = false;
      OpenTrade(ORDER_TYPE_SELL, mid[1]);
     }
  }

//+------------------------------------------------------------------+
//| Open a market order with SL beyond the mid EMA                   |
//+------------------------------------------------------------------+
void OpenTrade(const ENUM_ORDER_TYPE type, const double midEma)
  {
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;

   if(InpMaxSpreadPts > 0)
     {
      double spreadPts = (tick.ask - tick.bid) / _Point;
      if(spreadPts > InpMaxSpreadPts)
        {
         PrintFormat("Signal skipped: spread %.1f pts exceeds limit %d.", spreadPts, InpMaxSpreadPts);
         return;
        }
     }

   const double buffer = InpSlBufferPts * _Point;
   double price, sl;
   if(type == ORDER_TYPE_BUY)
     {
      price = tick.ask;
      sl    = midEma - buffer;
      if(sl >= price) return;   // mid EMA above price - geometry invalid
     }
   else
     {
      price = tick.bid;
      sl    = midEma + buffer;
      if(sl <= price) return;
     }

   //--- respect broker minimum stop distance
   double minStop = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double slDist  = MathAbs(price - sl);
   if(slDist < minStop)
     {
      slDist = minStop;
      sl = (type == ORDER_TYPE_BUY) ? price - slDist : price + slDist;
     }

   double tp = 0.0;
   if(InpTakeProfitRR > 0.0)
      tp = (type == ORDER_TYPE_BUY) ? price + slDist * InpTakeProfitRR
                                    : price - slDist * InpTakeProfitRR;

   sl = NormalizeDouble(sl, _Digits);
   tp = NormalizeDouble(tp, _Digits);

   double lots = CalcLots(slDist);
   if(lots <= 0.0)
      return;

   bool ok = (type == ORDER_TYPE_BUY)
             ? g_trade.Buy(lots, _Symbol, 0.0, sl, tp, InpTradeComment)
             : g_trade.Sell(lots, _Symbol, 0.0, sl, tp, InpTradeComment);

   if(!ok)
      PrintFormat("OrderSend failed: %d / %s", g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
   else
      PrintFormat("%s %.2f lots @ %.5f  SL %.5f  TP %.5f",
                  type == ORDER_TYPE_BUY ? "BUY" : "SELL", lots, price, sl, tp);
  }

//+------------------------------------------------------------------+
//| Position size from risk settings                                 |
//+------------------------------------------------------------------+
double CalcLots(const double slDistance)
  {
   double lots = InpFixedLot;

   if(InpLotMode == LOT_RISK_PERCENT)
     {
      double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      if(tickValue <= 0.0 || tickSize <= 0.0 || slDistance <= 0.0)
         return(0.0);

      double riskMoney    = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
      double lossPerLot   = slDistance / tickSize * tickValue;
      if(lossPerLot <= 0.0)
         return(0.0);
      lots = riskMoney / lossPerLot;
     }

   //--- normalize to symbol volume constraints
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(lotStep > 0.0)
      lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(minLot, MathMin(maxLot, lots));
   return(NormalizeDouble(lots, 2));
  }

//+------------------------------------------------------------------+
//| Break-even management for the open position                      |
//+------------------------------------------------------------------+
void ManageOpenPosition()
  {
   if(!InpUseBreakEven || !PositionSelectByMagic())
      return;

   double open = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl   = PositionGetDouble(POSITION_SL);
   double tp   = PositionGetDouble(POSITION_TP);
   long   type = PositionGetInteger(POSITION_TYPE);

   double risk = MathAbs(open - sl);
   if(risk <= 0.0)
      return;

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;

   double lock = InpBreakEvenLockPts * _Point;
   if(type == POSITION_TYPE_BUY)
     {
      double newSl = NormalizeDouble(open + lock, _Digits);
      if(sl < newSl && tick.bid - open >= risk * InpBreakEvenRR)
         g_trade.PositionModify(_Symbol, newSl, tp);
     }
   else
     {
      double newSl = NormalizeDouble(open - lock, _Digits);
      if((sl > newSl || sl == 0.0) && open - tick.ask >= risk * InpBreakEvenRR)
         g_trade.PositionModify(_Symbol, newSl, tp);
     }
  }

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
bool IsNewBar()
  {
   datetime barTime = iTime(_Symbol, _Period, 0);
   if(barTime == g_lastBarTime)
      return(false);
   g_lastBarTime = barTime;
   return(true);
  }

// Copies bars 0..3 of the given buffer as a series (index 1 = last closed bar)
bool CopyIndicator(const int handle, const int bufferIndex, double &dst[])
  {
   ArraySetAsSeries(dst, true);
   return(CopyBuffer(handle, bufferIndex, 0, 4, dst) == 4);
  }

bool PositionSelectByMagic()
  {
   if(!PositionSelect(_Symbol))
      return(false);
   return(PositionGetInteger(POSITION_MAGIC) == InpMagicNumber);
  }

bool TradingAllowedNow()
  {
   if(InpStartHour <= 0 && InpEndHour >= 24)
      return(true);
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(InpStartHour <= InpEndHour)
      return(dt.hour >= InpStartHour && dt.hour < InpEndHour);
   return(dt.hour >= InpStartHour || dt.hour < InpEndHour);   // overnight window
  }
//+------------------------------------------------------------------+
