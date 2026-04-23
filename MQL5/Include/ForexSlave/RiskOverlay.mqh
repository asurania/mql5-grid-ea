#ifndef __RISKOVERLAY_MQH__
#define __RISKOVERLAY_MQH__


#include <ForexSlave/PositionRegistry.mqh>

class CRiskOverlay
  {
private:
   CPositionRegistry *m_positions;
   double m_maxSpreadPoints;
   int    m_maxOpenPositionsPerPair;
   double m_maxGrossLotsPerPair;

   double CurrentSpreadPoints(string pair)
     {
      double ask = SymbolInfoDouble(pair, SYMBOL_ASK);
      double bid = SymbolInfoDouble(pair, SYMBOL_BID);
      double point = SymbolInfoDouble(pair, SYMBOL_POINT);
      if(point <= 0.0)
         return 0.0;
      return (ask - bid) / point;
     }

   double FreeMarginPercent()
     {
      double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(equity <= 0.0)
         return 0.0;
      return (AccountInfoDouble(ACCOUNT_MARGIN_FREE) / equity) * 100.0;
     }

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
      double spreadPoints = CurrentSpreadPoints(pair);
      if(spreadPoints <= 0.0)
        {
         reason = "invalid point size";
         return false;
        }
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

   bool PassesGridPolicyHardCaps(string pair,const GridPolicy &policy,string &reason)
     {
      if(m_positions == NULL)
        {
         reason = "positions registry not configured";
         return false;
        }

      if(policy.maxGrossLots > 0.0)
        {
         double grossLots = m_positions.GetGrossLots(pair);
         if(grossLots >= policy.maxGrossLots)
           {
            reason = "grid policy max gross lots reached";
            return false;
           }
        }

      if(policy.maxBasketDrawdownCurrency > 0.0)
        {
         double floatingPnl = m_positions.GetFloatingPnL(pair);
         if(floatingPnl <= -policy.maxBasketDrawdownCurrency)
           {
            reason = "grid policy max basket drawdown reached";
            return false;
           }
        }

      if(policy.minStepToSpreadRatio > 0.0)
        {
         double spreadPoints = CurrentSpreadPoints(pair);
         double stepPoints = policy.stepPips * 10.0;
         if(spreadPoints <= 0.0)
           {
            reason = "invalid spread for step ratio";
            return false;
           }
         double ratio = stepPoints / spreadPoints;
         if(ratio < policy.minStepToSpreadRatio)
           {
            reason = "step/spread ratio too low: " + DoubleToString(ratio, 2);
            return false;
           }
        }

      if(policy.minFreeMarginPercent > 0.0)
        {
         double freeMarginPct = FreeMarginPercent();
         if(freeMarginPct < policy.minFreeMarginPercent)
           {
            reason = "free margin percent too low: " + DoubleToString(freeMarginPct, 1);
            return false;
           }
        }

      reason = "grid policy hard caps ok";
      return true;
     }

   bool PassesEntryChecks(string pair,const GridPolicy &policy,string &reason)
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

      string policyReason = "";
      if(!PassesGridPolicyHardCaps(pair, policy, policyReason))
        {
         reason = policyReason;
         return false;
        }

      reason = "risk overlay ok";
      return true;
     }
  };

#endif
