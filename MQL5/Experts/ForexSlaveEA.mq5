#property strict

#include <ForexSlave/Config.mqh>
#include <ForexSlave/Types.mqh>
#include <ForexSlave/TelemetryLogger.mqh>
#include <ForexSlave/PolicyReader.mqh>
#include <ForexSlave/ExecutionGate.mqh>
#include <ForexSlave/TradeExecutor.mqh>

CTelemetryLogger g_logger;
CPolicyReader    g_policyReader;
CExecutionGate   g_gate;
CTradeExecutor   g_tradeExecutor;

int OnInit()
  {
   EventSetTimer(InpPolicyRefreshSeconds);
   g_logger.Info("ForexSlaveEA initialized");
   if(!g_policyReader.Refresh())
      g_logger.Warn("Initial policy refresh failed: " + g_policyReader.GetLastError());
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   g_logger.Info("ForexSlaveEA deinitialized");
  }

void OnTimer()
  {
   if(!g_policyReader.Refresh())
      g_logger.Warn("Policy refresh failed: " + g_policyReader.GetLastError());
   else
      g_logger.Info("Policy refresh ok");
  }

void OnTick()
  {
   PairPolicy policy = g_policyReader.GetPolicy(_Symbol);
   string reason = "";
   bool canOpen = g_gate.CanOpenNewTrade(policy, reason);

   g_logger.LogPolicyState(_Symbol, "band=" + policy.policyBand + ", status=" + IntegerToString((int)policy.status));

   if(!canOpen)
     {
      g_logger.LogTradeDecision(_Symbol, "BLOCK_NEW_TRADE", reason);
      return;
     }

   g_logger.LogTradeDecision(_Symbol, "ALLOW_NEW_TRADE", reason);

   // Stub only. Real strategy/grid logic will be attached later.
   // Example future call:
   // g_tradeExecutor.OpenBuy(_Symbol, 0.01, 0.0, 0.0, "stub");
  }
