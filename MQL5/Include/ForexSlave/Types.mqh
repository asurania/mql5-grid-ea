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

enum GridMode
  {
   GRID_MODE_BOTH_SIDES = 0,
   GRID_MODE_BUY_ONLY = 1,
   GRID_MODE_SELL_ONLY = 2,
   GRID_MODE_INVALID = 3
  };

enum SeedMode
  {
   SEED_MODE_SINGLE_SIDE = 0,
   SEED_MODE_BOTH_SIDES = 1,
   SEED_MODE_INVALID = 2
  };

struct GridPolicy
  {
   string   pair;
   bool     allowNewBasket;
   string   policyId;
   GridMode gridMode;
   SeedMode seedMode;
   double   stepPips;
   double   initialLot;
   double   multiplier;
   int      maxTradesPerSide;
   double   basketTpCurrency;
   bool     flattenOnStrongAvoid;
   double   confidence;
   string   reason;
   datetime expiresAt;
   bool     valid;
  };
