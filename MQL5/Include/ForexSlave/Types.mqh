#ifndef __TYPES_MQH__
#define __TYPES_MQH__


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
   double   maxGrossLots;
   double   maxBasketDrawdownCurrency;
   double   minStepToSpreadRatio;
   double   minFreeMarginPercent;
   bool     flattenOnStrongAvoid;
   double   confidence;
   string   reason;
   datetime expiresAt;
   bool     valid;
  };

enum EntryDirection
  {
   ENTRY_NONE = 0,
   ENTRY_BUY = 1,
   ENTRY_SELL = 2
  };

enum SessionState
  {
   SESSION_ACTIVE = 0,          // Normal trading
   SESSION_MANAGED_CLOSE = 1,   // No new baskets, let existing TP/expand
   SESSION_LIQUIDATE = 2,       // Force close everything
   SESSION_CLOSED = 3           // After NY close, no trading at all
  };

struct EntryDecision
  {
   bool           shouldEnter;
   EntryDirection direction;
   double         lots;
   string         reason;
  };

#endif
