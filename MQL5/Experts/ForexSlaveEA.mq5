#property strict

#include <ForexSlave/Config.mqh>
#include <ForexSlave/Types.mqh>
#include <ForexSlave/TelemetryLogger.mqh>
#include <ForexSlave/PolicyReader.mqh>
#include <ForexSlave/ExecutionGate.mqh>
#include <ForexSlave/TradeExecutor.mqh>
#include <ForexSlave/PositionRegistry.mqh>
#include <ForexSlave/GridManager.mqh>
#include <ForexSlave/RiskOverlay.mqh>
#include <ForexSlave/EntrySignal.mqh>
#include <ForexSlave/EntryIntentReader.mqh>
#include <ForexSlave/SessionManager.mqh>

CTelemetryLogger   g_logger;
CPolicyReader      g_policyReader;
CExecutionGate     g_gate;
CTradeExecutor     g_tradeExecutor;
CPositionRegistry  g_positions;
CRiskOverlay       g_risk;
CEntryIntentReader g_entryIntentReader;
CEntrySignal       g_entrySignal;
CGridManager       g_grid;
CSessionManager    g_session;
CGridPolicyReader  g_gridPolicyReader;

int OnInit()
  {
   EventSetTimer(InpPolicyRefreshSeconds);
   g_risk.Configure(g_positions);
   g_entrySignal.Configure(g_entryIntentReader, 0.01);
   g_grid.Configure(g_logger, g_positions, g_risk, g_entrySignal, g_tradeExecutor);
   g_session.Configure(g_logger);
   g_logger.Info("ForexSlaveEA initialized (session-managed-close="
      + (InpSessionManagedClose ? "ON" : "OFF")
      + ", managed_close_min=" + IntegerToString(InpManagedCloseMinutesBeforeEnd)
      + ", liquidate_min=" + IntegerToString(InpLiquidateMinutesBeforeEnd)
      + ", ny_close_utc=" + IntegerToString(InpNyCloseHourUTC) + ":" + IntegerToString(InpNyCloseMinuteUTC, 2) + ")");
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

   // Read Python-provided session timings from grid policy
   datetime managedCloseUTC = 0;
   datetime liquidateUTC = 0;
   datetime sessionCloseUTC = 0;
   if(g_gridPolicyReader.ExtractSessionTimings(managedCloseUTC, liquidateUTC, sessionCloseUTC))
     {
      g_session.UpdatePythonTimings(managedCloseUTC, liquidateUTC, sessionCloseUTC);
      g_logger.Info("Session timings updated from grid policy: managed_close="
         + TimeToString(managedCloseUTC, TIME_DATE|TIME_MINUTES)
         + ", liquidate=" + TimeToString(liquidateUTC, TIME_DATE|TIME_MINUTES)
         + ", session_close=" + TimeToString(sessionCloseUTC, TIME_DATE|TIME_MINUTES));
     }
  }

void OnTick()
  {
   PairPolicy policy = g_policyReader.GetPolicy(_Symbol);
   string reason = "";
   bool canOpen = g_gate.CanOpenNewTrade(policy, reason);
   string statusText = g_gate.DescribePolicyStatus(policy);
   int openCount = g_positions.CountOpenPositions(_Symbol);
   double netLots = g_positions.GetNetLots(_Symbol);
   double floatingPnl = g_positions.GetFloatingPnL(_Symbol);

   // Evaluate session state
   SessionState sessionState = g_session.EvaluateSessionState();
   g_session.LogStateChange(sessionState, _Symbol);

   g_logger.LogPolicyState(
      _Symbol,
      "action=" + IntegerToString((int)policy.action)
      + ", band=" + policy.policyBand
      + ", status=" + statusText
      + ", score=" + DoubleToString(policy.maxScoreAvoidSession, 4)
      + ", trigger=" + policy.triggerEventName
      + ", open_count=" + IntegerToString(openCount)
      + ", net_lots=" + DoubleToString(netLots, 2)
      + ", floating_pnl=" + DoubleToString(floatingPnl, 2)
      + ", session_state=" + IntegerToString((int)sessionState)
   );

   // --- Forced liquidation: close everything ---
   if(g_session.ShouldForceCloseAll(sessionState) && openCount > 0)
     {
      g_logger.LogTradeDecision(_Symbol, "SESSION_FORCE_CLOSE",
         "session_state=" + IntegerToString((int)sessionState)
         + ", positions=" + IntegerToString(openCount)
         + ", reason=liquidate_before_session_end");
      if(InpEnableLiveTrading)
        {
         g_grid.CloseAllPositionsForPair(_Symbol, "session_force_liquidation");
         g_session.SetLiquidated();
        }
      else
        {
         g_logger.LogTradeDecision(_Symbol, "SESSION_DRY_RUN_FORCE_CLOSE",
            "would liquidate all positions for session end");
        }
      return;  // no further action after force close
     }

   // --- Session closed: no trading at all ---
   if(sessionState == SESSION_CLOSED)
     {
      if(!g_session.ShouldAllowNewBasket(sessionState))
         g_logger.LogTradeDecision(_Symbol, "SESSION_CLOSED_NO_TRADING",
            "session closed, no action until next session");
      return;
     }

   // --- Managed close: no new baskets, but allow expansion and TP management ---
   bool sessionAllowsNewBasket = g_session.ShouldAllowNewBasket(sessionState);
   bool sessionAllowsExpansion = g_session.ShouldAllowExpansion(sessionState);

   // Combine policy gate + session gate for new entries
   bool effectiveCanOpen = canOpen && sessionAllowsNewBasket;

   if(!canOpen)
      g_logger.LogTradeDecision(_Symbol, "BLOCK_NEW_TRADE", reason);
   else if(!sessionAllowsNewBasket)
      g_logger.LogTradeDecision(_Symbol, "SESSION_MANAGED_CLOSE_BLOCK", "session in managed-close state, no new baskets");
   else
      g_logger.LogTradeDecision(_Symbol, "ALLOW_NEW_TRADE", reason);

   // New entries: only if both policy and session allow
   g_grid.EvaluateNewEntries(_Symbol, policy, effectiveCanOpen);

   // Basket management (expansion + TP): allowed in active and managed-close
   if(sessionAllowsExpansion)
      g_grid.EvaluateBasketManagement(_Symbol, policy);
   else
      g_logger.LogTradeDecision(_Symbol, "SESSION_SKIP_MANAGEMENT", "session state blocks expansion");
  }