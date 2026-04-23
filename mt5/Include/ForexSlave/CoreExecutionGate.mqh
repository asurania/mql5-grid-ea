#ifndef __FOREXSLAVE_CORE_EXECUTION_GATE_MQH__
#define __FOREXSLAVE_CORE_EXECUTION_GATE_MQH__

#include <ForexSlave/CorePortfolioPolicyReader.mqh>
#include <ForexSlave/PositionRegistry.mqh>

class CoreExecutionGate
{
private:
   CorePortfolioPolicyReader *m_policyReader;
   string m_lastReason;

public:
   CoreExecutionGate(CorePortfolioPolicyReader &policyReader)
   {
      m_policyReader = &policyReader;
      m_lastReason = "";
   }

   string LastReason() const
   {
      return m_lastReason;
   }

   bool CanOpenNewBasket(const string pair)
   {
      m_lastReason = "";

      if(m_policyReader == NULL)
      {
         m_lastReason = "core_policy_reader_missing";
         return false;
      }

      if(!m_policyReader.HasFreshRow(pair))
      {
         m_lastReason = "core_policy_stale_or_missing";
         return false;
      }

      if(!m_policyReader.IsPairEnabled(pair))
      {
         m_lastReason = "pair_disabled_by_core_policy";
         return false;
      }

      if(!m_policyReader.AllowNewBasket(pair))
      {
         m_lastReason = "new_basket_blocked_by_core_policy";
         return false;
      }

      CorePortfolioGuardrails g = m_policyReader.Guardrails();
      if(g.valid)
      {
         int activeSlots = EstimateActiveSlots();
         if(g.maxActiveSlots > 0 && activeSlots >= g.maxActiveSlots)
         {
            m_lastReason = "new_basket_blocked_max_active_slots";
            return false;
         }

         double totalInitialLots = EstimateTotalInitialLots();
         double nextInitialLot = m_policyReader.GetInitialLot(pair);
         if(g.maxTotalInitialLots > 0.0 && (totalInitialLots + nextInitialLot) > g.maxTotalInitialLots)
         {
            m_lastReason = "new_basket_blocked_max_total_initial_lots";
            return false;
         }
      }

      m_lastReason = "allow_new_basket";
      return true;
   }

   bool CanAddGridLeg(const string pair, const int currentTradesPerSide)
   {
      m_lastReason = "";

      if(m_policyReader == NULL)
      {
         m_lastReason = "core_policy_reader_missing";
         return false;
      }

      if(!m_policyReader.HasFreshRow(pair))
      {
         m_lastReason = "core_policy_stale_or_missing";
         return false;
      }

      int maxTrades = m_policyReader.GetMaxTradesPerSide(pair);
      if(maxTrades <= 0)
      {
         m_lastReason = "invalid_max_trades_per_side";
         return false;
      }

      if(currentTradesPerSide >= maxTrades)
      {
         m_lastReason = "grid_expansion_blocked_max_trades_per_side";
         return false;
      }

      m_lastReason = "allow_grid_leg";
      return true;
   }

   bool IsManagedCloseMode(const string pair, const int minutesToSessionClose)
   {
      m_lastReason = "";

      if(m_policyReader == NULL)
      {
         m_lastReason = "core_policy_reader_missing";
         return false;
      }

      if(!m_policyReader.HasFreshRow(pair))
      {
         m_lastReason = "core_policy_stale_or_missing";
         return false;
      }

      int managedCloseMinutes = m_policyReader.GetManagedCloseMinutes(pair);
      if(managedCloseMinutes < 0)
      {
         m_lastReason = "invalid_managed_close_minutes";
         return false;
      }

      if(minutesToSessionClose <= managedCloseMinutes)
      {
         m_lastReason = "managed_close_mode_no_new_entries";
         return true;
      }

      m_lastReason = "not_managed_close_mode";
      return false;
   }
private:
   int EstimateActiveSlots() const
   {
      return PositionRegistry::CountOwnedActiveSlots();
   }

   double EstimateTotalInitialLots() const
   {
      if(m_policyReader == NULL)
         return 0.0;

      double totalLots = 0.0;
      int rows = m_policyReader.RowCount();
      for(int i = 0; i < rows; i++)
      {
         CorePortfolioPairPolicy row = m_policyReader.GetRow(i);
         if(!row.valid)
            continue;
         if(PositionRegistry::CountOwnedPositions(row.pair) > 0)
            totalLots += row.initialLot;
      }
      return totalLots;
   }
};

#endif
