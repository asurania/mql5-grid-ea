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
  };
