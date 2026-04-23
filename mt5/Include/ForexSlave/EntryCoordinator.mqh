#ifndef __FOREXSLAVE_ENTRY_COORDINATOR_MQH__
#define __FOREXSLAVE_ENTRY_COORDINATOR_MQH__

#include <ForexSlave/CoreExecutionGate.mqh>
#include <ForexSlave/EntryIntentReader.mqh>
#include <ForexSlave/PairRiskPolicyReader.mqh>
#include <ForexSlave/CorePortfolioPolicyReader.mqh>

struct EntryDecision
{
   bool allowed;
   string pair;
   string direction;
   double initialLot;
   string reason;
};

class EntryCoordinator
{
private:
   CoreExecutionGate *m_gate;
   EntryIntentReader *m_entryIntent;
   PairRiskPolicyReader *m_pairRisk;
   CorePortfolioPolicyReader *m_corePolicy;

public:
   EntryCoordinator(CoreExecutionGate &gate,
                    EntryIntentReader &entryIntent,
                    PairRiskPolicyReader &pairRisk,
                    CorePortfolioPolicyReader &corePolicy)
   {
      m_gate = &gate;
      m_entryIntent = &entryIntent;
      m_pairRisk = &pairRisk;
      m_corePolicy = &corePolicy;
   }

   EntryDecision EvaluateFirstEntry(const string pair)
   {
      EntryDecision d;
      d.allowed = false;
      d.pair = pair;
      d.direction = "";
      d.initialLot = 0.0;
      d.reason = "unknown";

      if(m_gate == NULL || m_entryIntent == NULL || m_pairRisk == NULL || m_corePolicy == NULL)
      {
         d.reason = "entry_coordinator_dependency_missing";
         return d;
      }

      if(!m_pairRisk.HasFreshAllowance(pair))
      {
         d.reason = "pair_risk_blocks_new_entries";
         return d;
      }

      if(!m_entryIntent.HasFreshIntent(pair))
      {
         d.reason = "missing_fresh_entry_intent";
         return d;
      }

      if(!m_gate.CanOpenNewBasket(pair))
      {
         d.reason = m_gate.LastReason();
         return d;
      }

      string direction = m_entryIntent.GetDirection(pair);
      if(direction != "buy" && direction != "sell" && direction != "both")
      {
         d.reason = "invalid_entry_intent_direction";
         return d;
      }
      if(direction == "both")
      {
         double bid = SymbolInfoDouble(pair, SYMBOL_BID);
         double ask = SymbolInfoDouble(pair, SYMBOL_ASK);
         if(bid <= 0.0 || ask <= 0.0)
         {
            d.reason = "invalid_bid_ask_for_both_direction";
            return d;
         }
         direction = (bid <= ask) ? "sell" : "buy";
      }

      double initialLot = m_corePolicy.GetInitialLot(pair);
      if(initialLot <= 0.0)
      {
         d.reason = "invalid_initial_lot";
         return d;
      }

      d.allowed = true;
      d.direction = direction;
      d.initialLot = initialLot;
      d.reason = "allow_first_entry";
      return d;
   }
};

#endif
