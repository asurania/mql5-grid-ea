#ifndef __FOREXSLAVE_GRID_MANAGER_MQH__
#define __FOREXSLAVE_GRID_MANAGER_MQH__

#include <ForexSlave/CoreExecutionGate.mqh>
#include <ForexSlave/CorePortfolioPolicyReader.mqh>
#include <ForexSlave/GridPolicyReader.mqh>
#include <ForexSlave/PositionRegistry.mqh>
#include <ForexSlave/BasketState.mqh>

struct GridDecision
{
   bool   allowExpansion;
   string pair;
   string side;
   int    currentTradesPerSide;
   int    maxTradesPerSide;
   double stepPips;
   double multiplier;
   double nextLot;
   double lastOpenPrice;
   double currentPrice;
   double stepDistancePrice;
   string reason;
};

class GridManager
{
private:
   CoreExecutionGate          *m_gate;
   CorePortfolioPolicyReader  *m_policyReader;
   GridPolicyReader           *m_gridPolicyReader;

   double ResolveStepPips(const string pair)
   {
      if(m_gridPolicyReader != NULL && m_gridPolicyReader.HasFreshRow(pair))
         return m_gridPolicyReader.GetStepPips(pair);
      return m_policyReader.GetStepPips(pair);
   }

   double ResolveMultiplier(const string pair)
   {
      if(m_gridPolicyReader != NULL && m_gridPolicyReader.HasFreshRow(pair))
         return m_gridPolicyReader.GetMultiplier(pair);
      return m_policyReader.GetMultiplier(pair);
   }

   double ResolveInitialLot(const string pair)
   {
      if(m_gridPolicyReader != NULL && m_gridPolicyReader.HasFreshRow(pair))
         return m_gridPolicyReader.GetInitialLot(pair);
      return m_policyReader.GetInitialLot(pair);
   }

   int ResolveMaxTradesPerSide(const string pair)
   {
      if(m_gridPolicyReader != NULL && m_gridPolicyReader.HasFreshRow(pair))
         return m_gridPolicyReader.GetMaxTradesPerSide(pair);
      return m_policyReader.GetMaxTradesPerSide(pair);
   }

public:
   GridManager(CoreExecutionGate &gate, CorePortfolioPolicyReader &policyReader, GridPolicyReader *gridPolicyReader = NULL)
   {
      m_gate = &gate;
      m_policyReader = &policyReader;
      m_gridPolicyReader = gridPolicyReader;
   }

   GridDecision EvaluateExpansion(const string pair)
   {
      GridDecision d;
      d.allowExpansion = false;
      d.pair = pair;
      d.side = "";
      d.currentTradesPerSide = 0;
      d.maxTradesPerSide = 0;
      d.stepPips = 0.0;
      d.multiplier = 0.0;
      d.nextLot = 0.0;
      d.lastOpenPrice = 0.0;
      d.currentPrice = 0.0;
      d.stepDistancePrice = 0.0;
      d.reason = "unknown";

      if(m_gate == NULL || m_policyReader == NULL)
      {
         d.reason = "grid_manager_dependency_missing";
         return d;
      }

      BasketState state = BasketStateBuilder::Build(pair);
      int buyTrades = state.buy.count;
      int sellTrades = state.sell.count;
      bool useBuy = (buyTrades <= sellTrades);
      d.side = useBuy ? "buy" : "sell";
      d.currentTradesPerSide = useBuy ? buyTrades : sellTrades;
      d.maxTradesPerSide = ResolveMaxTradesPerSide(pair);
      d.stepPips = ResolveStepPips(pair);
      d.multiplier = ResolveMultiplier(pair);

      if(!m_gate.CanAddGridLeg(pair, d.currentTradesPerSide))
      {
         d.reason = m_gate.LastReason();
         return d;
      }

      double avgLots = useBuy ? state.buy.avgLot : state.sell.avgLot;
      if(avgLots <= 0.0)
         avgLots = ResolveInitialLot(pair);
      d.nextLot = avgLots * d.multiplier;

      int digits = (int)SymbolInfoInteger(pair, SYMBOL_DIGITS);
      double point = SymbolInfoDouble(pair, SYMBOL_POINT);
      double pipSize = (digits == 3 || digits == 5) ? point * 10.0 : point;
      d.stepDistancePrice = d.stepPips * pipSize;

      // If this side has zero positions, use current market price as the
      // conceptual "last open" so the distance check can trigger the first
      // expansion leg on the opposite side.
      d.lastOpenPrice = useBuy ? state.buy.lastOpenPrice : state.sell.lastOpenPrice;
      if(d.lastOpenPrice <= 0.0)
      {
         d.lastOpenPrice = useBuy ? SymbolInfoDouble(pair, SYMBOL_ASK) : SymbolInfoDouble(pair, SYMBOL_BID);
      }
      d.currentPrice = useBuy ? SymbolInfoDouble(pair, SYMBOL_BID) : SymbolInfoDouble(pair, SYMBOL_ASK);

      if(d.lastOpenPrice <= 0.0 || d.currentPrice <= 0.0)
      {
         d.reason = "invalid_price_state";
         return d;
      }

      bool distanceOk = false;
      if(useBuy)
         distanceOk = (d.currentPrice <= (d.lastOpenPrice - d.stepDistancePrice));
      else
         distanceOk = (d.currentPrice >= (d.lastOpenPrice + d.stepDistancePrice));

      if(!distanceOk)
      {
         d.reason = "grid_expansion_blocked_step_distance";
         return d;
      }

      d.allowExpansion = true;
      d.reason = "allow_grid_expansion";
      return d;
   }
};

#endif