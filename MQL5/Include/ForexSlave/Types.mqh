#pragma once

enum PolicyAction
  {
   POLICY_ALLOW_TRADING = 0,
   POLICY_SOFT_HALT_NEW_ENTRIES = 1,
   POLICY_BLOCK_NEW_ENTRIES = 2,
   POLICY_BLOCK_NEW_ENTRIES_STRONG = 3,
   POLICY_INVALID = 4
  };

enum PolicyStatus
  {
   POLICY_STATUS_FRESH = 0,
   POLICY_STATUS_STALE_WARNING = 1,
   POLICY_STATUS_STALE_FAIL_SAFE = 2,
   POLICY_STATUS_MISSING = 3,
   POLICY_STATUS_INVALID = 4
  };

struct PairPolicy
  {
   string       pair;
   PolicyAction action;
   string       policyBand;
   double       maxScoreAvoidSession;
   string       triggerEventId;
   string       triggerEventName;
   datetime     triggerEventTime;
   datetime     generatedAt;
   PolicyStatus status;
  };
