#pragma once

#include <ForexSlave/Types.mqh>
#include <ForexSlave/TelemetryLogger.mqh>
#include <ForexSlave/PositionRegistry.mqh>
#include <ForexSlave/RiskOverlay.mqh>
#include <ForexSlave/EntrySignal.mqh>
#include <ForexSlave/TradeExecutor.mqh>

class CGridManager
  {
private:
   CTelemetryLogger *m_logger;
   CPositionRegistry *m_positions;
   CRiskOverlay *m_risk;
   CEntrySignal *m_entrySignal;
   CTradeExecutor *m_tradeExecutor;

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

      string dir = "none";
      if(decision.direction == ENTRY_BUY)
         dir = "buy";
      else if(decision.direction == ENTRY_SELL)
         dir = "sell";

      m_logger.LogTradeDecision(pair, "GRID_FIRST_ENTRY_SIGNAL", "direction=" + dir + ", lots=" + DoubleToString(decision.lots, 2) + ", reason=" + decision.reason);

      if(m_tradeExecutor == NULL)
        {
         m_logger.LogTradeDecision(pair, "GRID_SKIP_EXECUTION", "trade executor not configured");
         return;
        }

      bool ok = false;
      if(decision.direction == ENTRY_BUY)
         ok = m_tradeExecutor.OpenBuy(pair, decision.lots, 0.0, 0.0, "python_entry_buy");
      else if(decision.direction == ENTRY_SELL)
         ok = m_tradeExecutor.OpenSell(pair, decision.lots, 0.0, 0.0, "python_entry_sell");

      if(!ok)
        {
         m_logger.LogTradeDecision(pair, "GRID_FIRST_ENTRY_EXECUTION_FAILED", m_tradeExecutor.GetLastError());
         return;
        }

      m_logger.LogTradeDecision(pair, "GRID_FIRST_ENTRY_EXECUTED", "direction=" + dir + ", lots=" + DoubleToString(decision.lots, 2));
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
