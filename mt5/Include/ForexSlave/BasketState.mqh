#ifndef __FOREXSLAVE_BASKET_STATE_MQH__
#define __FOREXSLAVE_BASKET_STATE_MQH__

#include <ForexSlave/SlaveIdentity.mqh>

struct BasketSideState
{
   int count;
   double avgLot;
   double totalLots;
   double weightedOpenPrice;
   double lastOpenPrice;
   double floatingPnl;
};

struct BasketState
{
   string pair;
   BasketSideState buy;
   BasketSideState sell;
   double totalFloatingPnl;
};

class BasketStateBuilder
{
public:
   static BasketState Build(const string pair)
   {
      BasketState state;
      state.pair = pair;
      state.buy.count = 0;
      state.buy.avgLot = 0.0;
      state.buy.totalLots = 0.0;
      state.buy.weightedOpenPrice = 0.0;
      state.buy.lastOpenPrice = 0.0;
      state.buy.floatingPnl = 0.0;
      state.sell.count = 0;
      state.sell.avgLot = 0.0;
      state.sell.totalLots = 0.0;
      state.sell.weightedOpenPrice = 0.0;
      state.sell.lastOpenPrice = 0.0;
      state.sell.floatingPnl = 0.0;
      state.totalFloatingPnl = 0.0;

      double buyLots = 0.0;
      double sellLots = 0.0;
      double buyWeighted = 0.0;
      double sellWeighted = 0.0;
      datetime buyLastTime = 0;
      datetime sellLastTime = 0;

      int total = PositionsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;

         string symbol = PositionGetString(POSITION_SYMBOL);
         long magic = PositionGetInteger(POSITION_MAGIC);
         string comment = PositionGetString(POSITION_COMMENT);
         if(symbol != pair)
            continue;
         if(magic != FOREXSLAVE_MAGIC)
            continue;
         if(StringFind(comment, FOREXSLAVE_COMMENT_PREFIX, 0) != 0)
            continue;

         long type = PositionGetInteger(POSITION_TYPE);
         double volume = PositionGetDouble(POSITION_VOLUME);
         double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         double pnl = PositionGetDouble(POSITION_PROFIT);
         datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);

         state.totalFloatingPnl += pnl;

         if(type == POSITION_TYPE_BUY)
         {
            state.buy.count++;
            buyLots += volume;
            buyWeighted += openPrice * volume;
            state.buy.floatingPnl += pnl;
            if(openTime >= buyLastTime)
            {
               buyLastTime = openTime;
               state.buy.lastOpenPrice = openPrice;
            }
         }
         else if(type == POSITION_TYPE_SELL)
         {
            state.sell.count++;
            sellLots += volume;
            sellWeighted += openPrice * volume;
            state.sell.floatingPnl += pnl;
            if(openTime >= sellLastTime)
            {
               sellLastTime = openTime;
               state.sell.lastOpenPrice = openPrice;
            }
         }
      }

      if(state.buy.count > 0)
      {
         state.buy.avgLot = buyLots / state.buy.count;
         state.buy.totalLots = buyLots;
         if(buyLots > 0.0)
            state.buy.weightedOpenPrice = buyWeighted / buyLots;
      }
      if(state.sell.count > 0)
      {
         state.sell.avgLot = sellLots / state.sell.count;
         state.sell.totalLots = sellLots;
         if(sellLots > 0.0)
            state.sell.weightedOpenPrice = sellWeighted / sellLots;
      }

      return state;
   }
};

#endif
