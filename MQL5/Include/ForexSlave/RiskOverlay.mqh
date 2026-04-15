#pragma once

#include <ForexSlave/PositionRegistry.mqh>

class CRiskOverlay
  {
private:
   CPositionRegistry *m_positions;
   double m_maxSpreadPoints;
   int    m_maxOpenPositionsPerPair;
   double m_maxGrossLotsPerPair;

public:
   CRiskOverlay()
     {
      m_positions = NULL;
      m_maxSpreadPoints = 50.0;
      m_maxOpenPositionsPerPair = 10;
      m_maxGrossLotsPerPair = 5.0;
     }

   void Configure(CPositionRegistry &positions,double maxSpreadPoints=50.0,int maxOpenPositionsPerPair=10,double maxGrossLotsPerPair=5.0)
     {
      m_positions = &positions;
      m_maxSpreadPoints = maxSpreadPoints;
      m_maxOpenPositionsPerPair = maxOpenPositionsPerPair;
      m_maxGrossLotsPerPair = maxGrossLotsPerPair;
     }

   bool PassesSpreadCheck(string pair,string &reason)
     {
      double ask = SymbolInfoDouble(pair, SYMBOL_ASK);
      double bid = SymbolInfoDouble(pair, SYMBOL_BID);
      double point = SymbolInfoDouble(pair, SYMBOL_POINT);
      if(point <= 0.0)
        {
         reason = "invalid point size";
         return false;
        }

      double spreadPoints = (ask - bid) / point;
      if(spreadPoints > m_maxSpreadPoints)
        {
         reason = "spread too high: " + DoubleToString(spreadPoints, 1) + " points";
         return false;
        }

      reason = "spread ok";
      return true;
     }

   bool PassesExposureLimits(string pair,string &reason)
     {
      if(m_positions == NULL)
        {
         reason = "positions registry not configured";
         return false;
        }

      int count = m_positions.CountOpenPositions(pair);
      double grossLots = m_positions.GetGrossLots(pair);

      if(count >= m_maxOpenPositionsPerPair)
        {
         reason = "max open positions reached";
         return false;
        }

      if(grossLots >= m_maxGrossLotsPerPair)
        {
         reason = "max gross lots reached";
         return false;
        }

      reason = "exposure ok";
      return true;
     }

   bool PassesEntryChecks(string pair,string &reason)
     {
      string spreadReason = "";
      if(!PassesSpreadCheck(pair, spreadReason))
        {
         reason = spreadReason;
         return false;
        }

      string exposureReason = "";
      if(!PassesExposureLimits(pair, exposureReason))
        {
         reason = exposureReason;
         return false;
        }

      reason = "risk overlay ok";
      return true;
     }
  };
