#ifndef __FOREXSLAVE_BASKET_MANAGER_MQH__
#define __FOREXSLAVE_BASKET_MANAGER_MQH__

#include <ForexSlave/BasketState.mqh>
#include <ForexSlave/CorePortfolioPolicyReader.mqh>
#include <ForexSlave/GridPolicyReader.mqh>

struct BasketManagementDecision
{
   bool   shouldTakeProfit;
   bool   shouldStopOut;
   string pair;
   string closeScope;
   double totalFloatingPnl;
   double buyFloatingPnl;
   double sellFloatingPnl;
   double maxBasketDrawdownCurrency;
   double maxSlotDrawdownCurrency;
   double basketTpPips;
   double buyTargetPrice;
   double sellTargetPrice;
   string reason;
};

class BasketManager
{
private:
   CorePortfolioPolicyReader  *m_policyReader;
   GridPolicyReader            *m_gridPolicyReader;

   double ResolveMaxBasketDD(const string pair)
   {
      if(m_gridPolicyReader != NULL && m_gridPolicyReader.HasFreshRow(pair))
         return m_gridPolicyReader.GetMaxBasketDrawdownCurrency(pair);
      return m_policyReader.GetMaxBasketDrawdownCurrency(pair);
   }

   double ResolveMaxSlotDD(const string pair)
   {
      return m_policyReader.GetMaxSlotDrawdownCurrency(pair);
   }

   double ResolveBasketTpPips(const string pair)
   {
      if(m_gridPolicyReader != NULL && m_gridPolicyReader.HasFreshRow(pair))
         return m_gridPolicyReader.GetBasketTpPips(pair);
      return m_policyReader.GetBasketTpPips(pair);
   }

public:
   BasketManager(CorePortfolioPolicyReader &policyReader, GridPolicyReader *gridPolicyReader = NULL)
   {
      m_policyReader = &policyReader;
      m_gridPolicyReader = gridPolicyReader;
   }

   BasketManagementDecision Evaluate(const string pair)
   {
      BasketManagementDecision d;
      d.shouldTakeProfit = false;
      d.shouldStopOut = false;
      d.pair = pair;
      d.closeScope = "pair";
      d.totalFloatingPnl = 0.0;
      d.buyFloatingPnl = 0.0;
      d.sellFloatingPnl = 0.0;
      d.maxBasketDrawdownCurrency = 0.0;
      d.maxSlotDrawdownCurrency = 0.0;
      d.basketTpPips = 0.0;
      d.buyTargetPrice = 0.0;
      d.sellTargetPrice = 0.0;
      d.reason = "unknown";

      if(m_policyReader == NULL)
      {
         d.reason = "basket_manager_policy_reader_missing";
         return d;
      }

      BasketState state = BasketStateBuilder::Build(pair);
      d.totalFloatingPnl = state.totalFloatingPnl;
      d.buyFloatingPnl = state.buy.floatingPnl;
      d.sellFloatingPnl = state.sell.floatingPnl;
      d.maxBasketDrawdownCurrency = ResolveMaxBasketDD(pair);
      d.maxSlotDrawdownCurrency = ResolveMaxSlotDD(pair);
      d.basketTpPips = ResolveBasketTpPips(pair);

      if(d.maxSlotDrawdownCurrency > 0.0)
      {
         if(state.buy.count > 0 && state.buy.floatingPnl <= -d.maxSlotDrawdownCurrency)
         {
            d.shouldStopOut = true;
            d.closeScope = "buy";
            d.reason = "buy_slot_drawdown_cap_breached";
            return d;
         }
         if(state.sell.count > 0 && state.sell.floatingPnl <= -d.maxSlotDrawdownCurrency)
         {
            d.shouldStopOut = true;
            d.closeScope = "sell";
            d.reason = "sell_slot_drawdown_cap_breached";
            return d;
         }
      }

      if(d.maxBasketDrawdownCurrency > 0.0 && state.totalFloatingPnl <= -d.maxBasketDrawdownCurrency)
      {
         d.shouldStopOut = true;
         d.closeScope = "pair";
         d.reason = "basket_drawdown_cap_breached";
         return d;
      }

      int digits = (int)SymbolInfoInteger(pair, SYMBOL_DIGITS);
      double point = SymbolInfoDouble(pair, SYMBOL_POINT);
      double pipSize = (digits == 3 || digits == 5) ? point * 10.0 : point;
      double bid = SymbolInfoDouble(pair, SYMBOL_BID);
      double ask = SymbolInfoDouble(pair, SYMBOL_ASK);

      if(state.buy.count > 0 && d.basketTpPips > 0.0)
      {
         d.buyTargetPrice = state.buy.weightedOpenPrice + (d.basketTpPips * pipSize);
         if(bid >= d.buyTargetPrice)
         {
            d.shouldTakeProfit = true;
            d.closeScope = "buy";
            d.reason = "basket_buy_tp_hit";
            return d;
         }
      }

      if(state.sell.count > 0 && d.basketTpPips > 0.0)
      {
         d.sellTargetPrice = state.sell.weightedOpenPrice - (d.basketTpPips * pipSize);
         if(ask <= d.sellTargetPrice)
         {
            d.shouldTakeProfit = true;
            d.closeScope = "sell";
            d.reason = "basket_sell_tp_hit";
            return d;
         }
      }

      d.reason = "basket_hold";
      return d;
   }
};

#endif