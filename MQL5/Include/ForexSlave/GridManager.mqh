#pragma once

#include <ForexSlave/Types.mqh>
#include <ForexSlave/TelemetryLogger.mqh>
#include <ForexSlave/PositionRegistry.mqh>

class CGridManager
  {
private:
   CTelemetryLogger *m_logger;
   CPositionRegistry *m_positions;

public:
   CGridManager()
     {
      m_logger = NULL;
      m_positions = NULL;
     }

   void Configure(CTelemetryLogger &logger,CPositionRegistry &positions)
     {
      m_logger = &logger;
      m_positions = &positions;
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
