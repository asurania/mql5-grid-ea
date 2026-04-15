#pragma once

input string InpPolicyFilePath = "pair_risk_policy.json";
input int    InpPolicyRefreshSeconds = 30;
input int    InpFreshnessWarningSeconds = 600;
input int    InpFreshnessFailSafeSeconds = 1800;
input bool   InpFailClosedOnMissingPolicy = true;
input bool   InpFailClosedOnInvalidPolicy = true;
