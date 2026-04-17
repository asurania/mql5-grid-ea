#ifndef __EXECUTIONGATE_MQH__
#define __EXECUTIONGATE_MQH__


#include <ForexSlave/Types.mqh>
#include <ForexSlave/Config.mqh>

class CExecutionGate
  {
public:
   bool CanOpenNewTrade(const PairPolicy &policy,string &reason)
     {
      if(policy.status == POLICY_STATUS_MISSING)
        {
         if(InpFailClosedOnMissingPolicy)
           {
            reason = "missing policy file, fail-closed";
            return false;
           }
         reason = "missing policy file, fail-open override";
         return true;
        }

      if(policy.status == POLICY_STATUS_INVALID)
        {
         if(InpFailClosedOnInvalidPolicy)
           {
            reason = "invalid policy file, fail-closed";
            return false;
           }
         reason = "invalid policy file, fail-open override";
         return true;
        }

      if(policy.status == POLICY_STATUS_STALE_FAIL_SAFE)
        {
         reason = "stale policy exceeded fail-safe threshold";
         return false;
        }

      if(policy.action == POLICY_SOFT_HALT_NEW_ENTRIES)
        {
         reason = "soft halt new entries";
         return false;
        }

      if(policy.action == POLICY_BLOCK_NEW_ENTRIES)
        {
         reason = "block new entries";
         return false;
        }

      if(policy.action == POLICY_BLOCK_NEW_ENTRIES_STRONG)
        {
         reason = "strong avoid session";
         return false;
        }

      if(policy.status == POLICY_STATUS_STALE_WARNING)
        {
         reason = "allowed with stale-warning policy";
         return true;
        }

      reason = "allowed with fresh policy";
      return true;
     }

   bool IsStrongAvoid(const PairPolicy &policy)
     {
      return policy.action == POLICY_BLOCK_NEW_ENTRIES_STRONG;
     }

   string DescribePolicyStatus(const PairPolicy &policy)
     {
      switch(policy.status)
        {
         case POLICY_STATUS_FRESH:
            return "fresh";
         case POLICY_STATUS_STALE_WARNING:
            return "stale_warning";
         case POLICY_STATUS_STALE_FAIL_SAFE:
            return "stale_fail_safe";
         case POLICY_STATUS_MISSING:
            return "missing";
         case POLICY_STATUS_INVALID:
            return "invalid";
        }
      return "unknown";
     }
  };

#endif
