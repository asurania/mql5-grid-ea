#ifndef __TRADEEXECUTOR_MQH__
#define __TRADEEXECUTOR_MQH__


#include <Trade/Trade.mqh>

class CTradeExecutor
  {
private:
   CTrade m_trade;
   string m_lastError;
   double m_lastRequestedLots;
   double m_lastNormalizedLots;

   bool ValidateInputs(string pair,double lots,string &reason)
     {
      if(pair == "")
        {
         reason = "empty symbol";
         return false;
        }
      if(lots <= 0.0)
        {
         reason = "lots must be positive";
         return false;
        }
      if(!SymbolSelect(pair, true))
        {
         reason = "failed to select symbol";
         return false;
        }
      reason = "";
      return true;
     }

   double NormalizeLots(string pair,double requestedLots,string &reason)
     {
      double minLot = SymbolInfoDouble(pair, SYMBOL_VOLUME_MIN);
      double maxLot = SymbolInfoDouble(pair, SYMBOL_VOLUME_MAX);
      double stepLot = SymbolInfoDouble(pair, SYMBOL_VOLUME_STEP);
      if(minLot <= 0.0 || maxLot <= 0.0 || stepLot <= 0.0)
        {
         reason = "invalid broker volume constraints";
         return 0.0;
        }

      double clamped = requestedLots;
      if(clamped > maxLot)
         clamped = maxLot;

      if(clamped < minLot)
        {
         reason = "requested lots below broker minimum: req=" + DoubleToString(requestedLots, 3)
            + ", min=" + DoubleToString(minLot, 2);
         return 0.0;
        }

      double steps = MathFloor((clamped - minLot) / stepLot + 1e-9);
      double normalized = minLot + steps * stepLot;
      if(normalized < minLot)
         normalized = minLot;
      if(normalized > maxLot)
         normalized = maxLot;

      int volumeDigits = 2;
      if(stepLot < 0.1)
         volumeDigits = 3;
      if(stepLot < 0.01)
         volumeDigits = 4;
      normalized = NormalizeDouble(normalized, volumeDigits);

      reason = "";
      return normalized;
     }

   void CaptureTradeError(string prefix)
     {
      m_lastError = prefix
         + " retcode=" + IntegerToString((int)m_trade.ResultRetcode())
         + " desc=" + m_trade.ResultRetcodeDescription();
     }

public:
   CTradeExecutor()
     {
      m_lastError = "";
      m_lastRequestedLots = 0.0;
      m_lastNormalizedLots = 0.0;
     }

   string GetLastError()
     {
      return m_lastError;
     }

   double GetLastRequestedLots()
     {
      return m_lastRequestedLots;
     }

   double GetLastNormalizedLots()
     {
      return m_lastNormalizedLots;
     }

   bool OpenBuy(string pair,double lots,double sl,double tp,string comment)
     {
      string reason = "";
      if(!ValidateInputs(pair, lots, reason))
        {
         m_lastError = "OpenBuy validation failed: " + reason;
         return false;
        }

      m_lastRequestedLots = lots;
      string normalizeReason = "";
      double normalizedLots = NormalizeLots(pair, lots, normalizeReason);
      m_lastNormalizedLots = normalizedLots;
      if(normalizedLots <= 0.0)
        {
         m_lastError = "OpenBuy normalization failed: " + normalizeReason;
         return false;
        }

      bool ok = m_trade.Buy(normalizedLots, pair, 0.0, sl, tp, comment);
      if(!ok)
        {
         CaptureTradeError("OpenBuy failed:");
         return false;
        }

      m_lastError = "";
      return true;
     }

   bool OpenSell(string pair,double lots,double sl,double tp,string comment)
     {
      string reason = "";
      if(!ValidateInputs(pair, lots, reason))
        {
         m_lastError = "OpenSell validation failed: " + reason;
         return false;
        }

      m_lastRequestedLots = lots;
      string normalizeReason = "";
      double normalizedLots = NormalizeLots(pair, lots, normalizeReason);
      m_lastNormalizedLots = normalizedLots;
      if(normalizedLots <= 0.0)
        {
         m_lastError = "OpenSell normalization failed: " + normalizeReason;
         return false;
        }

      bool ok = m_trade.Sell(normalizedLots, pair, 0.0, sl, tp, comment);
      if(!ok)
        {
         CaptureTradeError("OpenSell failed:");
         return false;
        }

      m_lastError = "";
      return true;
     }

   bool ClosePosition(ulong ticket)
     {
      if(ticket == 0)
        {
         m_lastError = "ClosePosition validation failed: zero ticket";
         return false;
        }

      bool ok = m_trade.PositionClose(ticket);
      if(!ok)
        {
         CaptureTradeError("ClosePosition failed:");
         return false;
        }

      m_lastError = "";
      return true;
     }

   bool ModifyPosition(ulong ticket,double sl,double tp)
     {
      if(ticket == 0)
        {
         m_lastError = "ModifyPosition validation failed: zero ticket";
         return false;
        }
      if(!PositionSelectByTicket(ticket))
        {
         m_lastError = "ModifyPosition validation failed: ticket not found";
         return false;
        }

      bool ok = m_trade.PositionModify(ticket, sl, tp);
      if(!ok)
        {
         CaptureTradeError("ModifyPosition failed:");
         return false;
        }

      m_lastError = "";
      return true;
     }
  };

#endif
