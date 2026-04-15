#pragma once

#include <ForexSlave/Types.mqh>
#include <ForexSlave/TelemetryLogger.mqh>
#include <ForexSlave/PositionRegistry.mqh>
#include <ForexSlave/RiskOverlay.mqh>
#include <ForexSlave/EntrySignal.mqh>
#include <ForexSlave/TradeExecutor.mqh>
#include <ForexSlave/GridPolicyReader.mqh>

class CGridManager
  {
private:
   CTelemetryLogger *m_logger;
   CPositionRegistry *m_positions;
   CRiskOverlay *m_risk;
   CEntrySignal *m_entrySignal;
   CTradeExecutor *m_tradeExecutor;
   CGridPolicyReader m_gridPolicyReader;

public:
   CGridManager()
     {
      m_logger = NULL;
      m_positions = NULL;
      m_risk = NULL;
      m_entrySignal = NULL;
      m_tradeExecutor = NULL;
     }

   void Configure(CTelemetryLogger &logger,CPositionRegistry &positions,CRiskOverlay &risk,CEntrySignal &entrySignal,CTradeExecutor &tradeExecutor)
     {
      m_logger = &logger;
      m_positions = &positions;
      m_risk = &risk;
      m_entrySignal = &entrySignal;
      m_tradeExecutor = &tradeExecutor;
     }

   void EvaluateNewEntries(string pair,const PairPolicy &policy,bool canOpenNewTrade)
     {
      if(m_logger == NULL || m_positions == NULL)
         return;

      int openCount = m_positions.CountOpenPositions(pair);
      if(!canOpenNewTrade)
        {
         m_logger.LogTradeDecision(pair, "GRID_SKIP_NEW_ENTRY", "policy gate blocked new entries");
         return;
        }

      if(m_risk != NULL)
        {
         string riskReason = "";
         if(!m_risk.PassesEntryChecks(pair, riskReason))
           {
            m_logger.LogTradeDecision(pair, "GRID_SKIP_NEW_ENTRY", "risk overlay blocked entry: " + riskReason);
            return;
           }
        }

      if(openCount > 0)
        {
         m_logger.LogTradeDecision(pair, "GRID_DEFER_NEW_ENTRY", "existing basket present, spacing logic not implemented yet");
         return;
        }

      if(m_entrySignal == NULL)
        {
         m_logger.LogTradeDecision(pair, "GRID_SKIP_NEW_ENTRY", "entry signal module not configured");
         return;
        }

      EntryDecision decision = m_entrySignal.EvaluateFirstEntry(pair);
      if(!decision.shouldEnter)
        {
         m_logger.LogTradeDecision(pair, "GRID_SKIP_NEW_ENTRY", decision.reason);
         return;
        }

      GridPolicy gridPolicy = m_gridPolicyReader.Evaluate(pair);
      if(!gridPolicy.valid)
        {
         m_logger.LogTradeDecision(pair, "GRID_SKIP_NEW_ENTRY", "grid policy invalid: " + gridPolicy.reason);
         return;
        }

      if(!gridPolicy.allowNewBasket)
        {
         m_logger.LogTradeDecision(pair, "GRID_SKIP_NEW_ENTRY", "grid policy disallows basket: " + gridPolicy.reason);
         return;
        }

      if(gridPolicy.gridMode == GRID_MODE_BUY_ONLY && decision.direction != ENTRY_BUY)
        {
         m_logger.LogTradeDecision(pair, "GRID_SKIP_NEW_ENTRY", "grid policy buy_only but entry signal is not buy");
         return;
        }
      if(gridPolicy.gridMode == GRID_MODE_SELL_ONLY && decision.direction != ENTRY_SELL)
        {
         m_logger.LogTradeDecision(pair, "GRID_SKIP_NEW_ENTRY", "grid policy sell_only but entry signal is not sell");
         return;
        }

      string dir = "none";
      if(decision.direction == ENTRY_BUY)
         dir = "buy";
      else if(decision.direction == ENTRY_SELL)
         dir = "sell";

      double lots = gridPolicy.initialLot > 0.0 ? gridPolicy.initialLot : decision.lots;

      string gridModeText = "both_sides";
      if(gridPolicy.gridMode == GRID_MODE_BUY_ONLY)
         gridModeText = "buy_only";
      else if(gridPolicy.gridMode == GRID_MODE_SELL_ONLY)
         gridModeText = "sell_only";

      m_logger.LogTradeDecision(pair, "GRID_FIRST_ENTRY_SIGNAL", "direction=" + dir
         + ", lots=" + DoubleToString(lots, 2)
         + ", policy_id=" + gridPolicy.policyId
         + ", grid_mode=" + gridModeText
         + ", step_pips=" + DoubleToString(gridPolicy.stepPips, 1)
         + ", multiplier=" + DoubleToString(gridPolicy.multiplier, 2)
         + ", max_trades_per_side=" + IntegerToString(gridPolicy.maxTradesPerSide)
         + ", reason=" + decision.reason);

      if(m_tradeExecutor == NULL)
        {
         m_logger.LogTradeDecision(pair, "GRID_SKIP_EXECUTION", "trade executor not configured");
         return;
        }

      if(!InpEnableLiveTrading)
        {
         m_logger.LogTradeDecision(pair, "GRID_DRY_RUN_ENTRY", "live trading disabled, would execute direction=" + dir + ", lots=" + DoubleToString(lots, 2) + ", policy_id=" + gridPolicy.policyId);
         return;
        }

      bool ok = false;
      if(decision.direction == ENTRY_BUY)
         ok = m_tradeExecutor.OpenBuy(pair, lots, 0.0, 0.0, "python_entry_buy");
      else if(decision.direction == ENTRY_SELL)
         ok = m_tradeExecutor.OpenSell(pair, lots, 0.0, 0.0, "python_entry_sell");

      if(!ok)
        {
         m_logger.LogTradeDecision(pair, "GRID_FIRST_ENTRY_EXECUTION_FAILED", m_tradeExecutor.GetLastError());
         return;
        }

      m_logger.LogTradeDecision(pair, "GRID_FIRST_ENTRY_EXECUTED", "direction=" + dir + ", lots=" + DoubleToString(lots, 2) + ", policy_id=" + gridPolicy.policyId);
     }

   void EvaluateBasketManagement(string pair,const PairPolicy &policy)
     {
      if(m_logger == NULL || m_positions == NULL)
         return;

      if(!m_positions.HasOpenExposure(pair))
        {
         m_logger.LogTradeDecision(pair, "GRID_SKIP_MANAGEMENT", "no open exposure");
         return;
        }

      m_logger.LogTradeDecision(pair, "GRID_MANAGE_BASKET", "basket management hooks not implemented yet");
     }
  };
