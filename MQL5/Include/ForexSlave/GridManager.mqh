#pragma once

#include <ForexSlave/Types.mqh>
#include <ForexSlave/TelemetryLogger.mqh>
#include <ForexSlave/PositionRegistry.mqh>
#include <ForexSlave/RiskOverlay.mqh>

class CGridManager
  {
private:
   CTelemetryLogger *m_logger;
   CPositionRegistry *m_positions;
   CRiskOverlay *m_risk;

public:
   CGridManager()
     {
      m_logger = NULL;
      m_positions = NULL;
      m_risk = NULL;
     }

   void Configure(CTelemetryLogger &logger,CPositionRegistry &positions,CRiskOverlay &risk)
     {
      m_logger = &logger;
      m_positions = &positions;
      m_risk = &risk;
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

      m_logger.LogTradeDecision(pair, "GRID_READY_FOR_FIRST_ENTRY", "no open basket, entry conditions not implemented yet");
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
