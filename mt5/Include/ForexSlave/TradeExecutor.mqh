#ifndef __FOREXSLAVE_TRADE_EXECUTOR_MQH__
#define __FOREXSLAVE_TRADE_EXECUTOR_MQH__

#include <Trade/Trade.mqh>
#include <ForexSlave/SlaveIdentity.mqh>

#define FOREXSLAVE_DEFAULT_DEVIATION 20

class TradeExecutor
{
private:
   CTrade m_trade;
   string m_lastError;

   string BuildComment(const string pair, const string side)
   {
      return FOREXSLAVE_COMMENT_PREFIX + ":" + pair + ":" + side;
   }

public:
   TradeExecutor()
   {
      m_lastError = "";
      m_trade.SetDeviationInPoints(FOREXSLAVE_DEFAULT_DEVIATION);
   }

   string LastError() const
   {
      return m_lastError;
   }

   bool ClosePositionByTicket(const ulong ticket)
   {
      m_lastError = "";
      if(ticket == 0)
      {
         m_lastError = "invalid_ticket";
         return false;
      }

      if(!PositionSelectByTicket(ticket))
      {
         m_lastError = "position_not_found";
         return false;
      }

      if(!m_trade.PositionClose(ticket))
      {
         m_lastError = "position_close_failed_retcode_" + IntegerToString((int)m_trade.ResultRetcode());
         return false;
      }

      m_lastError = "close_ok";
      return true;
   }

   int CloseAllOwnedPositions(const string pair = "")
   {
      int closed = 0;
      int total = PositionsTotal();
      for(int i = total - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         string symbol = PositionGetString(POSITION_SYMBOL);
         long magic = PositionGetInteger(POSITION_MAGIC);
         string comment = PositionGetString(POSITION_COMMENT);
         if(pair != "" && symbol != pair)
            continue;
         if(magic != FOREXSLAVE_MAGIC)
            continue;
         if(StringFind(comment, FOREXSLAVE_COMMENT_PREFIX, 0) != 0)
            continue;
         if(ClosePositionByTicket(ticket))
            closed++;
      }
      return closed;
   }

   int CloseOwnedPositionsBySide(const string pair, const string side)
   {
      int closed = 0;
      long targetType = -1;
      if(side == "buy")
         targetType = POSITION_TYPE_BUY;
      else if(side == "sell")
         targetType = POSITION_TYPE_SELL;
      else
         return CloseAllOwnedPositions(pair);

      int total = PositionsTotal();
      for(int i = total - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         string symbol = PositionGetString(POSITION_SYMBOL);
         long magic = PositionGetInteger(POSITION_MAGIC);
         string comment = PositionGetString(POSITION_COMMENT);
         long type = PositionGetInteger(POSITION_TYPE);
         if(symbol != pair)
            continue;
         if(magic != FOREXSLAVE_MAGIC)
            continue;
         if(StringFind(comment, FOREXSLAVE_COMMENT_PREFIX, 0) != 0)
            continue;
         if(type != targetType)
            continue;
         if(ClosePositionByTicket(ticket))
            closed++;
      }
      return closed;
   }

   bool ModifyPositionTpSl(const ulong ticket, const double sl, const double tp)
   {
      m_lastError = "";
      if(ticket == 0)
      {
         m_lastError = "invalid_ticket";
         return false;
      }
      if(!PositionSelectByTicket(ticket))
      {
         m_lastError = "position_not_found";
         return false;
      }
      if(!m_trade.PositionModify(ticket, sl, tp))
      {
         m_lastError = "position_modify_failed_retcode_" + IntegerToString((int)m_trade.ResultRetcode());
         return false;
      }
      m_lastError = "modify_ok";
      return true;
   }

   bool OpenBuy(const string pair, const double lots)
   {
      m_lastError = "";
      m_trade.SetExpertMagicNumber(FOREXSLAVE_MAGIC);
      if(!m_trade.Buy(lots, pair, 0.0, 0.0, 0.0, BuildComment(pair, "buy")))
      {
         m_lastError = "buy_failed_retcode_" + IntegerToString((int)m_trade.ResultRetcode());
         return false;
      }
      m_lastError = "buy_ok";
      return true;
   }

   bool OpenSell(const string pair, const double lots)
   {
      m_lastError = "";
      m_trade.SetExpertMagicNumber(FOREXSLAVE_MAGIC);
      if(!m_trade.Sell(lots, pair, 0.0, 0.0, 0.0, BuildComment(pair, "sell")))
      {
         m_lastError = "sell_failed_retcode_" + IntegerToString((int)m_trade.ResultRetcode());
         return false;
      }
      m_lastError = "sell_ok";
      return true;
   }
};

#endif
