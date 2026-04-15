#pragma once

#include <ForexSlave/Types.mqh>

class CExecutionGate
  {
public:
   bool CanOpenNewTrade(const PairPolicy &policy,string &reason)
     {
      if(policy.status == POLICY_STATUS_STALE_FAIL_SAFE ||
         policy.status == POLICY_STATUS_MISSING ||
         policy.status == POLICY_STATUS_INVALID)
        {
         reason = "policy unavailable or stale fail-safe";
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

      reason = "allowed";
      return true;
     }

   bool IsStrongAvoid(const PairPolicy &policy)
     {
      return policy.action == POLICY_BLOCK_NEW_ENTRIES_STRONG;
     }
  };
