#ifndef __TPADJUSTER_MQH__
#define __TPADJUSTER_MQH__


#include <ForexSlave/Types.mqh>
#include <ForexSlave/TelemetryLogger.mqh>
#include <ForexSlave/PositionRegistry.mqh>
#include <ForexSlave/TradeExecutor.mqh>

class CTpAdjuster
  {
private:
   CTelemetryLogger   *m_logger;
   CPositionRegistry  *m_positions;
   CTradeExecutor      *m_tradeExecutor;
   datetime             m_lastAdjustTime[];
   string               m_lastAdjustPair[];
   int                  m_adjustCount[];

   // Track last known TP/SL per pair to avoid redundant modifications
   double               m_lastTpPrice[];
   double               m_lastSlPrice[];
   string               m_lastPolicyId[];

   int FindPairIndex(string pair)
     {
      for(int i = 0; i < ArraySize(m_lastAdjustPair); i++)
        {
         if(m_lastAdjustPair[i] == pair)
            return i;
        }
      return -1;
     }

   int EnsurePairIndex(string pair)
     {
      int idx = FindPairIndex(pair);
      if(idx >= 0)
         return idx;

      int size = ArraySize(m_lastAdjustPair);
      ArrayResize(m_lastAdjustPair, size + 1);
      ArrayResize(m_lastTpPrice, size + 1);
      ArrayResize(m_lastSlPrice, size + 1);
      ArrayResize(m_lastPolicyId, size + 1);
      ArrayResize(m_lastAdjustTime, size + 1);
      ArrayResize(m_adjustCount, size + 1);

      m_lastAdjustPair[size] = pair;
      m_lastTpPrice[size] = 0.0;
      m_lastSlPrice[size] = 0.0;
      m_lastPolicyId[size] = "";
      m_lastAdjustTime[size] = 0;
      m_adjustCount[size] = 0;
      return size;
     }

   double PointsPerPip(string pair)
     {
      int digits = (int)SymbolInfoInteger(pair, SYMBOL_DIGITS);
      double point = SymbolInfoDouble(pair, SYMBOL_POINT);
      if(digits == 3 || digits == 5)
         return point * 10.0;
      return point;
     }

public:
   CTpAdjuster() : m_logger(NULL), m_positions(NULL), m_tradeExecutor(NULL)
     {
     }

   void Configure(CTelemetryLogger &logger, CPositionRegistry &positions, CTradeExecutor &tradeExecutor)
     {
      m_logger = &logger;
      m_positions = &positions;
      m_tradeExecutor = &tradeExecutor;
     }

   // Core TP adjust — runs every tick for each pair with open positions
   // Calculates weighted-average entry, then sets broker-visible TP and SL
   // on all positions for that pair.
   // This mirrors the old EA's tp_adjust() behavior.
   void AdjustBasketTpSl(string pair, const GridPolicy &gridPolicy)
     {
      if(m_positions == NULL || m_tradeExecutor == NULL || m_logger == NULL)
         return;

      int total = m_positions->CountOpenPositions(pair);
      if(total <= 0)
         return;

      // Calculate weighted-average entry price
      double weightedOpen = m_positions->GetWeightedOpenPrice(pair);
      if(weightedOpen <= 0.0)
        {
         m_logger->LogTradeDecision(pair, "TP_ADJUST_SKIP", "weighted open price is zero");
         return;
        }

      double floatingPnl = m_positions->GetFloatingPnL(pair);
      double slope = m_positions->GetDirectionalPnlSlopePerPriceUnit(pair);
      int digits = (int)SymbolInfoInteger(pair, SYMBOL_DIGITS);
      double point = SymbolInfoDouble(pair, SYMBOL_POINT);
      double pipSize = PointsPerPip(pair);

      // --- Calculate TP price ---
      double tpPrice = 0.0;

      // Method 1: Use basket_tp_pips from grid policy (variable by session)
      // This is the weighted-average entry + N pips
      if(gridPolicy.basketTpPips > 0.0)
        {
         // Determine direction: net position direction
         double netLots = m_positions->GetNetLots(pair);
         double tpOffsetPips = gridPolicy.basketTpPips;

         // For both-sides baskets, use the floating PnL slope to determine direction
         // If net long, TP is above weighted average; if net short, below
         if(MathAbs(netLots) > 1e-9)
           {
            // Net directional position: TP is on the profitable side
            if(netLots > 0)
               tpPrice = weightedOpen + tpOffsetPips * pipSize;
            else
               tpPrice = weightedOpen - tpOffsetPips * pipSize;
           }
         else
           {
            // Balanced both-sides basket: use currency-based TP
            // Fall through to currency method
            tpPrice = 0.0;
           }
        }

      // Method 2: Use basket_tp_currency (currency-based TP) if pip-based not applicable
      if(tpPrice <= 0.0 && gridPolicy.basketTpCurrency > 0.0 && MathAbs(slope) > 1e-9)
        {
         tpPrice = weightedOpen + ((gridPolicy.basketTpCurrency - floatingPnl) / slope);
        }

      // --- Calculate SL price ---
      double slPrice = 0.0;

      // Method 1: Use basket_sl_pips from grid policy
      if(gridPolicy.basketSlPips > 0.0)
        {
         double netLots = m_positions->GetNetLots(pair);
         double slOffsetPips = gridPolicy.basketSlPips;

         if(MathAbs(netLots) > 1e-9)
           {
            if(netLots > 0)
               slPrice = weightedOpen - slOffsetPips * pipSize;
            else
               slPrice = weightedOpen + slOffsetPips * pipSize;
           }
        }

      // Method 2: Use max_basket_drawdown_currency
      if(slPrice <= 0.0 && gridPolicy.maxBasketDrawdownCurrency > 0.0 && MathAbs(slope) > 1e-9)
        {
         slPrice = weightedOpen + ((-gridPolicy.maxBasketDrawdownCurrency - floatingPnl) / slope);
        }

      // Normalize prices
      if(tpPrice > 0.0)
         tpPrice = NormalizeDouble(tpPrice, digits);
      if(slPrice > 0.0)
         slPrice = NormalizeDouble(slPrice, digits);

      // --- Validate TP/SL ---
      double bid = SymbolInfoDouble(pair, SYMBOL_BID);
      double ask = SymbolInfoDouble(pair, SYMBOL_ASK);

      // Skip modification if TP and SL haven't changed (avoid spamming broker)
      int idx = EnsurePairIndex(pair);
      bool tpChanged = (MathAbs(tpPrice - m_lastTpPrice[idx]) > point * 5.0);  // 5 points tolerance
      bool slChanged = (MathAbs(slPrice - m_lastSlPrice[idx]) > point * 5.0);
      bool policyChanged = (m_lastPolicyId[idx] != gridPolicy.policyId);

      if(!tpChanged && !slChanged && !policyChanged)
        {
         // No meaningful change since last adjustment — skip
         return;
        }

      // --- Modify all positions ---
      int modifyCount = 0;
      int failCount = 0;
      for(int i = PositionsTotal() - 1; i >= 0; --i)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != pair)
            continue;

         long posType = PositionGetInteger(POSITION_TYPE);
         double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         double currentSl = PositionGetDouble(POSITION_SL);
         double currentTp = PositionGetDouble(POSITION_TP);

         // Compute position-specific TP/SL with safety checks
         double posSl = slPrice;
         double posTp = tpPrice;

         // Validate: buy SL must be below bid, sell SL must be above ask
         if(posSl > 0.0)
           {
            if(posType == POSITION_TYPE_BUY && posSl >= bid)
               posSl = NormalizeDouble(MathMin(openPrice, bid) - point * 10.0, digits);
            if(posType == POSITION_TYPE_SELL && posSl <= ask)
               posSl = NormalizeDouble(MathMax(openPrice, ask) + point * 10.0, digits);
           }

         // Validate: buy TP must be above ask, sell TP must be below bid
         if(posTp > 0.0)
           {
            if(posType == POSITION_TYPE_BUY && posTp <= ask)
               posTp = NormalizeDouble(MathMax(openPrice, ask) + point * 10.0, digits);
            if(posType == POSITION_TYPE_SELL && posTp >= bid)
               posTp = NormalizeDouble(MathMin(openPrice, bid) - point * 10.0, digits);
           }

         // Skip if already set to same values (within tolerance)
         bool currentSlClose = (MathAbs(currentSl - posSl) < point * 2.0);
         bool currentTpClose = (MathAbs(currentTp - posTp) < point * 2.0);
         if(currentSlClose && currentTpClose)
            continue;

         if(!m_tradeExecutor->ModifyPosition(ticket, posSl, posTp))
           {
            failCount++;
            m_logger->LogTradeDecision(pair, "TP_ADJUST_MODIFY_FAILED",
               "ticket=" + IntegerToString((int)ticket)
               + ", sl=" + DoubleToString(posSl, digits)
               + ", tp=" + DoubleToString(posTp, digits)
               + ", err=" + m_tradeExecutor->GetLastError());
           }
         else
           {
            modifyCount++;
           }
        }

      // Update tracking
      m_lastTpPrice[idx] = tpPrice;
      m_lastSlPrice[idx] = tpPrice > 0.0 ? tpPrice : 0.0;  // store actual
      m_lastSlPrice[idx] = slPrice;
      m_lastPolicyId[idx] = gridPolicy.policyId;
      m_lastAdjustTime[idx] = TimeCurrent();
      m_adjustCount[idx]++;

      if(modifyCount > 0 || failCount > 0)
        {
         string source = "";
         if(gridPolicy.basketTpPips > 0.0)
            source = "pip_based_tp=" + DoubleToString(gridPolicy.basketTpPips, 1);
         else if(gridPolicy.basketTpCurrency > 0.0)
            source = "currency_tp=" + DoubleToString(gridPolicy.basketTpCurrency, 2);
         else
            source = "no_tp_target";

         m_logger->LogTradeDecision(pair, "TP_ADJUST",
            "weighted_open=" + DoubleToString(weightedOpen, digits)
            + ", floating_pnl=" + DoubleToString(floatingPnl, 2)
            + ", basket_tp_pips=" + DoubleToString(gridPolicy.basketTpPips, 1)
            + ", basket_tp_currency=" + DoubleToString(gridPolicy.basketTpCurrency, 2)
            + ", basket_sl_pips=" + DoubleToString(gridPolicy.basketSlPips, 1)
            + ", tp_price=" + DoubleToString(tpPrice, digits)
            + ", sl_price=" + DoubleToString(slPrice, digits)
            + ", modified=" + IntegerToString(modifyCount)
            + ", failed=" + IntegerToString(failCount)
            + ", source=" + source);
        }
     }

   // Reset tracking for a pair (call after basket close)
   void ResetPair(string pair)
     {
      int idx = FindPairIndex(pair);
      if(idx >= 0)
        {
         m_lastTpPrice[idx] = 0.0;
         m_lastSlPrice[idx] = 0.0;
         m_lastPolicyId[idx] = "";
         m_lastAdjustTime[idx] = 0;
         m_adjustCount[idx] = 0;
        }
     }
  };

#endif