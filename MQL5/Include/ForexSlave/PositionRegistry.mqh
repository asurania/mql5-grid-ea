#pragma once

class CPositionRegistry
  {
public:
   int CountOpenPositions(string pair)
     {
      int count = 0;
      for(int i = PositionsTotal() - 1; i >= 0; --i)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) == pair)
            count++;
        }
      return count;
     }

   double GetNetLots(string pair)
     {
      double net = 0.0;
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
         double vol = PositionGetDouble(POSITION_VOLUME);
         if(posType == POSITION_TYPE_BUY)
            net += vol;
         else if(posType == POSITION_TYPE_SELL)
            net -= vol;
        }
      return net;
     }

   double GetGrossLots(string pair)
     {
      double gross = 0.0;
      for(int i = PositionsTotal() - 1; i >= 0; --i)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) == pair)
            gross += PositionGetDouble(POSITION_VOLUME);
        }
      return gross;
     }

   double GetFloatingPnL(string pair)
     {
      double pnl = 0.0;
      for(int i = PositionsTotal() - 1; i >= 0; --i)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) == pair)
            pnl += PositionGetDouble(POSITION_PROFIT);
        }
      return pnl;
     }

   bool HasOpenExposure(string pair)
     {
      return CountOpenPositions(pair) > 0;
     }

   int CountOpenPositionsByType(string pair,ENUM_POSITION_TYPE targetType)
     {
      int count = 0;
      for(int i = PositionsTotal() - 1; i >= 0; --i)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != pair)
            continue;
         if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == targetType)
            count++;
        }
      return count;
     }

   double GetLotsByType(string pair,ENUM_POSITION_TYPE targetType)
     {
      double total = 0.0;
      for(int i = PositionsTotal() - 1; i >= 0; --i)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != pair)
            continue;
         if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == targetType)
            total += PositionGetDouble(POSITION_VOLUME);
        }
      return total;
     }

   double GetLastOpenPriceByType(string pair,ENUM_POSITION_TYPE targetType)
     {
      datetime lastTime = 0;
      double lastPrice = 0.0;
      for(int i = PositionsTotal() - 1; i >= 0; --i)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != pair)
            continue;
         if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != targetType)
            continue;

         datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
         if(openTime >= lastTime)
           {
            lastTime = openTime;
            lastPrice = PositionGetDouble(POSITION_PRICE_OPEN);
           }
        }
      return lastPrice;
     }

   ulong GetTicketByIndex(string pair,int matchIndex)
     {
      int seen = 0;
      for(int i = PositionsTotal() - 1; i >= 0; --i)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(!PositionSelectByTicket(ticket))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != pair)
            continue;
         if(seen == matchIndex)
            return ticket;
         seen++;
        }
      return 0;
     }
  };
