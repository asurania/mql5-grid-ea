#ifndef __CONFIG_MQH__
#define __CONFIG_MQH__


input string InpPolicyFilePath = "ForexSlave\\pair_risk_policy.json";
input bool   InpEnableLiveTrading = false;
input int    InpPolicyRefreshSeconds = 30;
input int    InpFreshnessWarningSeconds = 600;
input int    InpFreshnessFailSafeSeconds = 1800;
input bool   InpFailClosedOnMissingPolicy = true;
input bool   InpFailClosedOnInvalidPolicy = true;

// --- Session management ---
input bool   InpSessionManagedClose = true;               // Enable session-end managed close
input int    InpManagedCloseMinutesBeforeEnd = 30;       // Stop new baskets N min before session end
input int    InpLiquidateMinutesBeforeEnd = 10;           // Force liquidate N min before session end
input int    InpNyCloseHourUTC = 21;                      // NY session close hour (UTC, default 21=17:00 EST)
input int    InpNyCloseMinuteUTC = 0;                     // NY session close minute (UTC)

#endif
