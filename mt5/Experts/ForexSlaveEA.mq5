#property strict

#include <ForexSlave/CorePortfolioTypes.mqh>
#include <ForexSlave/CorePortfolioPolicyReader.mqh>
#include <ForexSlave/CoreExecutionGate.mqh>
#include <ForexSlave/AccountRiskOverlay.mqh>
#include <ForexSlave/TelemetryLogger.mqh>
#include <ForexSlave/SlaveIdentity.mqh>
#include <ForexSlave/TradeExecutor.mqh>
#include <ForexSlave/PositionRegistry.mqh>
#include <ForexSlave/EntryIntentReader.mqh>
#include <ForexSlave/PairRiskPolicyReader.mqh>
#include <ForexSlave/EntryCoordinator.mqh>
#include <ForexSlave/GridManager.mqh>
#include <ForexSlave/BasketManager.mqh>
#include <ForexSlave/TpSlManager.mqh>
#include <ForexSlave/SessionClock.mqh>
#include <ForexSlave/CooldownRegistry.mqh>
#include <ForexSlave/GridPolicyReader.mqh>

input string InpManagedPair = "";           // leave empty for all policy pairs, or set e.g. GBPUSD for single-pair mode
input int    InpTimerSeconds = 15;
input bool   InpDryRunNewBasket = true;
input bool   InpDryRunGridExpansion = true;
input int    InpSideCooldownSeconds = 1800;
input int    InpPairCooldownSeconds = 1800;

CorePortfolioPolicyReader g_policy_reader;
EntryIntentReader g_entry_intent_reader;
PairRiskPolicyReader g_pair_risk_reader;
GridPolicyReader g_grid_policy_reader;
CoreExecutionGate *g_execution_gate = NULL;
AccountRiskOverlay *g_risk_overlay = NULL;
TradeExecutor *g_trade_executor = NULL;
TpSlManager *g_tpsl_manager = NULL;

string g_managedPairs[];

void FlattenOwnedExposure()
{
   if(g_trade_executor == NULL)
   {
      TelemetryLogger::LogError("Flatten", "trade_executor_missing");
      return;
   }
   int closed = g_trade_executor.CloseAllOwnedPositions();
   TelemetryLogger::LogDecision("Flatten", "close_all_owned_positions", "closed=" + IntegerToString(closed) + " detail=" + g_trade_executor.LastError());
}

void BuildManagedPairs()
{
   ArrayResize(g_managedPairs, 0);
   if(InpManagedPair != "")
   {
      ArrayResize(g_managedPairs, 1);
      g_managedPairs[0] = InpManagedPair;
      TelemetryLogger::LogInfo("EA", "single_pair_mode pair=" + InpManagedPair);
      return;
   }
   int rows = g_policy_reader.RowCount();
   for(int i = 0; i < rows; i++)
   {
      CorePortfolioPairPolicy row = g_policy_reader.GetRow(i);
      if(!row.valid || !row.enabled)
         continue;
      if(!g_policy_reader.HasFreshRow(row.pair))
         continue;
      int n = ArraySize(g_managedPairs);
      ArrayResize(g_managedPairs, n + 1);
      g_managedPairs[n] = row.pair;
   }
   TelemetryLogger::LogInfo("EA", "multi_pair_mode pairs=" + IntegerToString(ArraySize(g_managedPairs)));
}

int OnInit()
{
   g_execution_gate = new CoreExecutionGate(g_policy_reader);
   g_risk_overlay = new AccountRiskOverlay(g_policy_reader);
   g_trade_executor = new TradeExecutor();
   g_tpsl_manager = new TpSlManager(g_policy_reader, *g_trade_executor, &g_grid_policy_reader);
   EventSetTimer(InpTimerSeconds);
   TelemetryLogger::LogInfo("EA", "ForexSlaveEA initialized");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(g_execution_gate != NULL) { delete g_execution_gate; g_execution_gate = NULL; }
   if(g_risk_overlay != NULL)   { delete g_risk_overlay;   g_risk_overlay = NULL; }
   if(g_trade_executor != NULL) { delete g_trade_executor;  g_trade_executor = NULL; }
   if(g_tpsl_manager != NULL)  { delete g_tpsl_manager;  g_tpsl_manager = NULL; }
   TelemetryLogger::LogInfo("EA", "ForexSlaveEA deinitialized");
}

void OnTimer()
{
   bool ok = g_policy_reader.Refresh();
   if(!ok)
   {
      TelemetryLogger::LogError("CorePolicy", g_policy_reader.LastError());
      return;
   }
   g_entry_intent_reader.Refresh();
   g_pair_risk_reader.Refresh();
   g_grid_policy_reader.Refresh();
   BuildManagedPairs();

   bool accountAllows = (g_risk_overlay != NULL && g_risk_overlay.AllowNewEntries());
   TelemetryLogger::LogDecision("Risk", "AllowNewEntries=" + (accountAllows ? "true" : "false"), g_risk_overlay != NULL ? g_risk_overlay.LastReason() : "risk_overlay_missing");

   if(g_risk_overlay != NULL && g_risk_overlay.ShouldFlatten())
   {
      TelemetryLogger::LogDecision("Risk", "FlattenOwnedExposure=true", g_risk_overlay.LastReason());
      FlattenOwnedExposure();
   }

   for(int i = 0; i < ArraySize(g_managedPairs); i++)
   {
      string pair = g_managedPairs[i];
      bool sessionAllows = (g_risk_overlay != NULL && g_risk_overlay.AllowSessionEntries(pair));
      bool canOpen = accountAllows && sessionAllows && g_execution_gate.CanOpenNewBasket(pair);
      int currentTrades = PositionRegistry::CountOwnedPositions(pair);
      bool canAdd = g_execution_gate.CanAddGridLeg(pair, currentTrades);
      int minutesToClose = SessionClock::MinutesToSessionClose(g_policy_reader.GetSessionName(pair));
      bool managedClose = g_execution_gate.IsManagedCloseMode(pair, minutesToClose);
      TelemetryLogger::LogDecision("Gate", pair + " CanOpen=" + (canOpen ? "1" : "0") + " CanAdd=" + (canAdd ? "1" : "0") + " ManagedClose=" + (managedClose ? "1" : "0"), g_execution_gate.LastReason());
   }
}

void ManagePair(const string pair)
{
   int ownedPositions = PositionRegistry::CountOwnedPositions(pair);

   if(ownedPositions == 0)
   {
      CooldownRegistry::ClearCooldown(pair, "pair");
      CooldownRegistry::ClearCooldown(pair, "buy");
      CooldownRegistry::ClearCooldown(pair, "sell");
   }
   else
   {
      int buyPositions = PositionRegistry::CountOwnedPositionsByType(pair, POSITION_TYPE_BUY);
      int sellPositions = PositionRegistry::CountOwnedPositionsByType(pair, POSITION_TYPE_SELL);
      if(buyPositions == 0) CooldownRegistry::ClearCooldown(pair, "buy");
      if(sellPositions == 0) CooldownRegistry::ClearCooldown(pair, "sell");
   }

   if(ownedPositions > 0)
   {
      ManageExistingBasket(pair);
      return;
   }

   ManageNewEntry(pair);
}

void ManageExistingBasket(const string pair)
{
   string sessionName = g_policy_reader.GetSessionName(pair);
   bool sessionOpen = SessionClock::IsSessionOpen(sessionName);
   int minutesToClose = SessionClock::MinutesToSessionClose(sessionName);
   bool managedCloseMode = sessionOpen && g_execution_gate.IsManagedCloseMode(pair, minutesToClose);
   string sessionCloseBehavior = g_policy_reader.GetSessionCloseBehavior(pair);

   if(g_tpsl_manager != NULL)
   {
      int modified = g_tpsl_manager.RefreshOwnedPositionTpSl(pair);
      TelemetryLogger::LogDecision("TpSl", pair, "modified=" + IntegerToString(modified) + " session_open=" + (sessionOpen ? "1" : "0") + " managed_close=" + (managedCloseMode ? "1" : "0"));
   }

   if(managedCloseMode && sessionCloseBehavior == "close_all_trades")
   {
      TelemetryLogger::LogDecision("Session", pair, "close_all_trades minutes_to_close=" + IntegerToString(minutesToClose));
      int closed = g_trade_executor.CloseAllOwnedPositions(pair);
      TelemetryLogger::LogDecision("Session", pair, "close_all_trades_done closed=" + IntegerToString(closed));
      return;
   }

   if(managedCloseMode && sessionCloseBehavior == "managed_closing_of_trades")
   {
      TelemetryLogger::LogDecision("Session", pair, "managed_close_active minutes_to_close=" + IntegerToString(minutesToClose));
   }

   BasketManager basket_mgr(g_policy_reader, &g_grid_policy_reader);
   BasketManagementDecision basket = basket_mgr.Evaluate(pair);
   if(basket.shouldStopOut || basket.shouldTakeProfit)
   {
      string action = basket.shouldStopOut ? "stop_out" : "take_profit";
      TelemetryLogger::LogDecision("Basket", pair, action + " scope=" + basket.closeScope + " floating=" + DoubleToString(basket.totalFloatingPnl, 2) + " reason=" + basket.reason);

      int closed = (basket.closeScope == "buy" || basket.closeScope == "sell")
         ? g_trade_executor.CloseOwnedPositionsBySide(pair, basket.closeScope)
         : g_trade_executor.CloseAllOwnedPositions(pair);
      if(closed > 0)
      {
         int cooldown = (basket.closeScope == "buy" || basket.closeScope == "sell") ? InpSideCooldownSeconds : InpPairCooldownSeconds;
         CooldownRegistry::SetCooldown(pair, basket.closeScope, cooldown);
      }
      TelemetryLogger::LogDecision("Basket", pair, "closed scope=" + basket.closeScope + " count=" + IntegerToString(closed));
      return;
   }

   if(managedCloseMode)
   {
      TelemetryLogger::LogDecision("Grid", pair, "blocked_managed_close");
      return;
   }

   if(g_risk_overlay != NULL && !g_risk_overlay.AllowSessionEntries(pair))
   {
      TelemetryLogger::LogDecision("Grid", pair, "blocked_session_loss_cap " + g_risk_overlay.LastReason());
      return;
   }

   GridManager grid_mgr(*g_execution_gate, g_policy_reader, &g_grid_policy_reader);
   GridDecision grid = grid_mgr.EvaluateExpansion(pair);
   if(CooldownRegistry::IsBlocked(pair, "pair") || CooldownRegistry::IsBlocked(pair, grid.side))
   {
      TelemetryLogger::LogDecision("Grid", pair, "blocked_cooldown side=" + grid.side + " pair_rem=" + IntegerToString(CooldownRegistry::RemainingSeconds(pair, "pair")) + " side_rem=" + IntegerToString(CooldownRegistry::RemainingSeconds(pair, grid.side)));
      return;
   }
   if(!grid.allowExpansion)
   {
      TelemetryLogger::LogDecision("Grid", pair, "blocked reason=" + grid.reason);
      return;
   }

   if(InpDryRunGridExpansion)
   {
      TelemetryLogger::LogDecision("Grid", pair, "dry_run side=" + grid.side + " next_lot=" + DoubleToString(grid.nextLot, 2));
      return;
   }

   bool expandOk = false;
   if(grid.side == "sell")
      expandOk = g_trade_executor.OpenSell(pair, grid.nextLot);
   else
      expandOk = g_trade_executor.OpenBuy(pair, grid.nextLot);
   TelemetryLogger::LogDecision("Grid", pair, expandOk ? "expansion_ok" : "expansion_fail side=" + grid.side);
}

void ManageNewEntry(const string pair)
{
   if(g_risk_overlay != NULL && !g_risk_overlay.AllowSessionEntries(pair))
   {
      TelemetryLogger::LogDecision("Entry", pair, "blocked_session_loss_cap " + g_risk_overlay.LastReason());
      return;
   }

   if(CooldownRegistry::IsBlocked(pair, "pair"))
   {
      TelemetryLogger::LogDecision("Entry", pair, "blocked_pair_cooldown rem=" + IntegerToString(CooldownRegistry::RemainingSeconds(pair, "pair")));
      return;
   }

   EntryCoordinator coord(*g_execution_gate, g_entry_intent_reader, g_pair_risk_reader, g_policy_reader);
   EntryDecision decision = coord.EvaluateFirstEntry(pair);
   if(!decision.allowed)
   {
      TelemetryLogger::LogDecision("Entry", pair, "blocked reason=" + decision.reason);
      return;
   }

   if(InpDryRunNewBasket)
   {
      TelemetryLogger::LogDecision("Entry", pair, "dry_run side=" + decision.direction + " lot=" + DoubleToString(decision.initialLot, 2));
      return;
   }

   // For both_sides grid mode, seed both buy and sell simultaneously
   string intentDir = g_entry_intent_reader.GetDirection(pair);
   bool seedBoth = (intentDir == "both");

   bool ok = false;
   if(seedBoth)
   {
      bool buyOk = g_trade_executor.OpenBuy(pair, decision.initialLot);
      bool sellOk = g_trade_executor.OpenSell(pair, decision.initialLot);
      ok = buyOk || sellOk;
      TelemetryLogger::LogDecision("Entry", pair, (ok ? "both_ok" : "both_fail") + " buy=" + (buyOk ? "1" : "0") + " sell=" + (sellOk ? "1" : "0"));
      return;
   }

   if(decision.direction == "sell")
      ok = g_trade_executor.OpenSell(pair, decision.initialLot);
   else
      ok = g_trade_executor.OpenBuy(pair, decision.initialLot);
   TelemetryLogger::LogDecision("Entry", pair, ok ? "open_ok" : "open_fail side=" + decision.direction);
}

void OnTick()
{
   if(g_execution_gate == NULL || g_trade_executor == NULL)
      return;

   bool policyOk = g_policy_reader.Refresh();
   if(!policyOk)
   {
      TelemetryLogger::LogError("CorePolicy", g_policy_reader.LastError());
      return;
   }
   g_entry_intent_reader.Refresh();
   g_pair_risk_reader.Refresh();
   g_grid_policy_reader.Refresh();
   BuildManagedPairs();

   for(int i = 0; i < ArraySize(g_managedPairs); i++)
      ManagePair(g_managedPairs[i]);
}