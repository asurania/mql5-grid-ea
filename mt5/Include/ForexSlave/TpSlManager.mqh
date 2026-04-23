#ifndef __FOREXSLAVE_TPSL_MANAGER_MQH__
#define __FOREXSLAVE_TPSL_MANAGER_MQH__

#include <ForexSlave/BasketState.mqh>
#include <ForexSlave/CorePortfolioPolicyReader.mqh>
#include <ForexSlave/GridPolicyReader.mqh>
#include <ForexSlave/TradeExecutor.mqh>

class TpSlManager
{
private:
   CorePortfolioPolicyReader  *m_policyReader;
   GridPolicyReader            *m_gridPolicyReader;
   TradeExecutor               *m_tradeExecutor;

   double ResolveTpPips(const string pair)
   {
      if(m_gridPolicyReader != NULL && m_gridPolicyReader.HasFreshRow(pair))
         return m_gridPolicyReader.GetBasketTpPips(pair);
      return m_policyReader.GetBasketTpPips(pair);
   }

   double ResolveSlPips(const string pair)
   {
      // grid_policy has basket_tp_pips but reuses basket_sl_pips from core policy
      return m_policyReader.GetBasketSlPips(pair);
   }

public:
   TpSlManager(CorePortfolioPolicyReader &policyReader, TradeExecutor &tradeExecutor, GridPolicyReader *gridPolicyReader = NULL)
   {
      m_policyReader = &policyReader;
      m_tradeExecutor = &tradeExecutor;
      m_gridPolicyReader = gridPolicyReader;
   }

   int RefreshOwnedPositionTpSl(const string pair)
   {
      if(m_policyReader == NULL || m_tradeExecutor == NULL)
         return 0;

      BasketState state = BasketStateBuilder::Build(pair);
      double tpPips = ResolveTpPips(pair);
      double slPips = ResolveSlPips(pair);
      int digits = (int)SymbolInfoInteger(pair, SYMBOL_DIGITS);
      double point = SymbolInfoDouble(pair, SYMBOL_POINT);
      double pipSize = (digits == 3 || digits == 5) ? point * 10.0 : point;

      double buyTp = (state.buy.count > 0 && tpPips > 0.0) ? state.buy.weightedOpenPrice + tpPips * pipSize : 0.0;
      double buySl = (state.buy.count > 0 && slPips > 0.0) ? state.buy.weightedOpenPrice - slPips * pipSize : 0.0;
      double sellTp = (state.sell.count > 0 && tpPips > 0.0) ? state.sell.weightedOpenPrice - tpPips * pipSize : 0.0;
      double sellSl = (state.sell.count > 0 && slPips > 0.0) ? state.sell.weightedOpenPrice + slPips * pipSize : 0.0;

      int modified = 0;
      int total = PositionsTotal();
      for(int i = 0; i < total; i++)
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

         double tp = (type == POSITION_TYPE_BUY) ? buyTp : sellTp;
         double sl = (type == POSITION_TYPE_BUY) ? buySl : sellSl;
         if(tp <= 0.0 && sl <= 0.0)
            continue;
         double currentTp = PositionGetDouble(POSITION_TP);
         double currentSl = PositionGetDouble(POSITION_SL);
         if(MathAbs(tp - currentTp) < point && MathAbs(sl - currentSl) < point)
            continue;
         if(m_tradeExecutor.ModifyPositionTpSl(ticket, sl, tp))
            modified++;
      }
      return modified;
   }
};

#endif