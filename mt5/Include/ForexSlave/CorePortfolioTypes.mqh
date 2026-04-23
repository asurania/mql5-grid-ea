#ifndef __FOREXSLAVE_CORE_PORTFOLIO_TYPES_MQH__
#define __FOREXSLAVE_CORE_PORTFOLIO_TYPES_MQH__

struct CorePortfolioGuardrails
{
   int    maxActiveSlots;
   double maxTotalInitialLots;
   double maxTotalDrawdownCurrency;
   double dailyLossCapCurrency;
   double sessionLossCapCurrency;
   bool   flattenOnAccountBreach;
   bool   blockNewEntriesAfterDailyCap;
   bool   valid;
};

struct CorePortfolioPairPolicy
{
   string   pair;
   string   sessionName;
   bool     enabled;
   bool     allowNewBasket;
   string   gridMode;
   string   seedMode;
   double   stepPips;
   double   initialLot;
   string   initialLotMode;
   double   baseEquity;
   double   multiplier;
   int      maxTradesPerSide;
   double   basketTpPips;
   double   basketSlPips;
   double   maxBasketDrawdownCurrency;
   double   maxSlotDrawdownCurrency;
   int      managedCloseMinutes;
   string   sessionCloseBehavior;
   bool     flattenOnAccountBreach;
   double   tailLossGuardCurrency;
   double   forcedCloseRateWarn;
   datetime expiresAt;
   string   reason;
   // Grid policy v2 fields (optional, sourced from grid_policy.json)
   double   predictedRangePips;
   double   basketTpCurrency;
   double   maxGrossLots;
   double   minStepToSpreadRatio;
   double   minFreeMarginPercent;
   bool     flattenOnStrongAvoid;
   bool     brokerVisibleTpSl;
   bool     valid;
};

#endif
