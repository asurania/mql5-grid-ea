#pragma once

#include <Trade/Trade.mqh>

class CTradeExecutor
  {
private:
   CTrade m_trade;
   string m_lastError;

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
     }

   string GetLastError()
     {
      return m_lastError;
     }

   bool OpenBuy(string pair,double lots,double sl,double tp,string comment)
     {
      string reason = "";
      if(!ValidateInputs(pair, lots, reason))
        {
         m_lastError = "OpenBuy validation failed: " + reason;
         return false;
        }

      bool ok = m_trade.Buy(lots, pair, 0.0, sl, tp, comment);
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

      bool ok = m_trade.Sell(lots, pair, 0.0, sl, tp, comment);
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
  };
