#pragma once

#include <ForexSlave/Types.mqh>
#include <ForexSlave/TelemetryLogger.mqh>
#include <ForexSlave/PositionRegistry.mqh>
#include <ForexSlave/RiskOverlay.mqh>
#include <ForexSlave/EntrySignal.mqh>

class CGridManager
  {
private:
   CTelemetryLogger *m_logger;
   CPositionRegistry *m_positions;
   CRiskOverlay *m_risk;
   CEntrySignal *m_entrySignal;

public:
   CGridManager()
     {
      m_logger = NULL;
      m_positions = NULL;
      m_risk = NULL;
      m_entrySignal = NULL;
     }

   void Configure(CTelemetryLogger &logger,CPositionRegistry &positions,CRiskOverlay &risk,CEntrySignal &entrySignal)
     {
      m_logger = &logger;
      m_positions = &positions;
      m_risk = &risk;
      m_entrySignal = &entrySignal;
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
