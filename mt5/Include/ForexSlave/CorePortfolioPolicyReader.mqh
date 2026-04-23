#ifndef __FOREXSLAVE_CORE_PORTFOLIO_POLICY_READER_MQH__
#define __FOREXSLAVE_CORE_PORTFOLIO_POLICY_READER_MQH__

#include <ForexSlave/CorePortfolioTypes.mqh>
#include <JAson.mqh>

class CorePortfolioPolicyReader
{
private:
   string m_filePath;
   datetime m_generatedAt;
   CorePortfolioGuardrails m_guardrails;
   CorePortfolioPairPolicy m_rows[];
   string m_lastError;

public:
   CorePortfolioPolicyReader(const string filePath = "ForexSlave\\core_portfolio_policy.json")
   {
      m_filePath = filePath;
      m_generatedAt = 0;
      m_lastError = "";
      m_guardrails.valid = false;
      ArrayResize(m_rows, 0);
   }

   bool Refresh()
   {
      m_lastError = "";
      m_generatedAt = 0;
      m_guardrails.valid = false;
      ArrayResize(m_rows, 0);

      int handle = FileOpen(m_filePath, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(handle == INVALID_HANDLE)
      {
         m_lastError = "file_open_failed";
         return false;
      }

      string raw = "";
      while(!FileIsEnding(handle))
         raw += FileReadString(handle);
      FileClose(handle);

      if(StringLen(raw) == 0)
      {
         m_lastError = "empty_policy_file";
         return false;
      }

      CJAVal root;
      if(!root.Deserialize(raw))
      {
         m_lastError = "json_parse_failed";
         return false;
      }

      if(!root.HasKey("generated_at_utc") || !root.HasKey("guardrails") || !root.HasKey("pairs"))
      {
         m_lastError = "missing_required_top_level_keys";
         return false;
      }

      string generatedAtText = root["generated_at_utc"].ToStr();
      m_generatedAt = StringToTime(generatedAtText);
      if(m_generatedAt <= 0)
      {
         m_lastError = "invalid_generated_at_utc";
         return false;
      }

      CJAVal g = root["guardrails"];
      m_guardrails.maxActiveSlots = (int)g["max_active_slots"].ToInt();
      m_guardrails.maxTotalInitialLots = g["max_total_initial_lots"].ToDbl();
      m_guardrails.maxTotalDrawdownCurrency = g["max_total_drawdown_currency"].ToDbl();
      m_guardrails.dailyLossCapCurrency = g["daily_loss_cap_currency"].ToDbl();
      m_guardrails.sessionLossCapCurrency = g["session_loss_cap_currency"].ToDbl();
      m_guardrails.flattenOnAccountBreach = g["flatten_on_account_breach"].ToBool();
      m_guardrails.blockNewEntriesAfterDailyCap = g["block_new_entries_after_daily_cap"].ToBool();
      m_guardrails.valid = true;

      CJAVal pairs = root["pairs"];
      int count = pairs.Size();
      if(count <= 0)
      {
         m_lastError = "no_pair_rows";
         return false;
      }

      ArrayResize(m_rows, count);
      for(int i = 0; i < count; i++)
      {
         CJAVal row = pairs[i];
         CorePortfolioPairPolicy policy;
         policy.valid = false;
         policy.pair = row["pair"].ToStr();
         policy.sessionName = row["session_name"].ToStr();
         policy.enabled = row["enabled"].ToBool();
         policy.allowNewBasket = row["allow_new_basket"].ToBool();
         policy.gridMode = row["grid_mode"].ToStr();
         policy.seedMode = row["seed_mode"].ToStr();
         policy.stepPips = row["step_pips"].ToDbl();
         policy.initialLot = row["initial_lot"].ToDbl();
         policy.initialLotMode = row["initial_lot_mode"].ToStr();
         policy.baseEquity = row["base_equity"].ToDbl();
         policy.multiplier = row["multiplier"].ToDbl();
         policy.maxTradesPerSide = (int)row["max_trades_per_side"].ToInt();
         policy.basketTpPips = row["basket_tp_pips"].ToDbl();
         policy.basketSlPips = row["basket_sl_pips"].ToDbl();
         policy.maxBasketDrawdownCurrency = row["max_basket_drawdown_currency"].ToDbl();
         policy.maxSlotDrawdownCurrency = row["max_slot_drawdown_currency"].ToDbl();
         policy.managedCloseMinutes = (int)row["managed_close_minutes"].ToInt();
         policy.sessionCloseBehavior = row["session_close_behavior"].ToStr();
         policy.flattenOnAccountBreach = row["flatten_on_account_breach"].ToBool();
         policy.tailLossGuardCurrency = row.HasKey("tail_loss_guard_currency") ? row["tail_loss_guard_currency"].ToDbl() : 0.0;
         policy.forcedCloseRateWarn = row.HasKey("forced_close_rate_warn") ? row["forced_close_rate_warn"].ToDbl() : 0.0;
         policy.expiresAt = StringToTime(row["expires_at_utc"].ToStr());
         policy.reason = row["reason"].ToStr();
         // Optional grid-policy-v2 fields (may be absent in static core policy)
         policy.predictedRangePips = row.HasKey("predicted_range_pips") ? row["predicted_range_pips"].ToDbl() : 0.0;
         policy.basketTpCurrency = row.HasKey("basket_tp_currency") ? row["basket_tp_currency"].ToDbl() : 0.0;
         policy.maxGrossLots = row.HasKey("max_gross_lots") ? row["max_gross_lots"].ToDbl() : 0.0;
         policy.minStepToSpreadRatio = row.HasKey("min_step_to_spread_ratio") ? row["min_step_to_spread_ratio"].ToDbl() : 0.0;
         policy.minFreeMarginPercent = row.HasKey("min_free_margin_percent") ? row["min_free_margin_percent"].ToDbl() : 0.0;
         policy.flattenOnStrongAvoid = row.HasKey("flatten_on_strong_avoid") ? row["flatten_on_strong_avoid"].ToBool() : false;
         policy.brokerVisibleTpSl = row.HasKey("broker_visible_tp_sl") ? row["broker_visible_tp_sl"].ToBool() : true;

         if(policy.pair == "" || policy.stepPips <= 0.0 || policy.initialLot <= 0.0 || policy.multiplier < 1.0 || policy.maxTradesPerSide < 1 || policy.maxBasketDrawdownCurrency <= 0.0 || policy.maxSlotDrawdownCurrency <= 0.0 || policy.managedCloseMinutes < 0 || policy.expiresAt <= 0)
         {
            m_lastError = "invalid_pair_row";
            return false;
         }

         policy.valid = true;
         m_rows[i] = policy;
      }

      return true;
   }

   string LastError() const
   {
      return m_lastError;
   }

   bool HasFreshRow(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return false;
      if(!m_rows[idx].valid)
         return false;
      if(m_rows[idx].expiresAt <= TimeGMT())
         return false;
      return true;
   }

   bool IsPairEnabled(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return false;
      return m_rows[idx].valid && m_rows[idx].enabled;
   }

   bool AllowNewBasket(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return false;
      return m_rows[idx].valid && m_rows[idx].allowNewBasket;
   }

   int GetMaxTradesPerSide(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return 0;
      return m_rows[idx].maxTradesPerSide;
   }

   double GetStepPips(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return 0.0;
      return m_rows[idx].stepPips;
   }

   double GetInitialLot(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return 0.0;
      double baseLot = m_rows[idx].initialLot;
      if(m_rows[idx].initialLotMode != "equity_scaled" || m_rows[idx].baseEquity <= 0.0)
         return baseLot;
      double accountEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(accountEquity <= 0.0)
         return baseLot;
      double scaled = baseLot * (accountEquity / m_rows[idx].baseEquity);
      double lotStep = 0.01;
      double minLot = 0.01;
      double maxLot = 100.0;
      // Round to nearest lot step
      double rounded = MathRound(scaled / lotStep) * lotStep;
      if(rounded < minLot)
         rounded = minLot;
      if(rounded > maxLot)
         rounded = maxLot;
      return rounded;
   }

   double GetMultiplier(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return 0.0;
      return m_rows[idx].multiplier;
   }

   double GetBasketTpPips(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return 0.0;
      return m_rows[idx].basketTpPips;
   }

   double GetBasketSlPips(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return 0.0;
      return m_rows[idx].basketSlPips;
   }

   double GetMaxBasketDrawdownCurrency(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return 0.0;
      return m_rows[idx].maxBasketDrawdownCurrency;
   }

   double GetMaxSlotDrawdownCurrency(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return 0.0;
      return m_rows[idx].maxSlotDrawdownCurrency;
   }

   int GetManagedCloseMinutes(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return 0;
      return m_rows[idx].managedCloseMinutes;
   }

   string GetSessionName(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return "";
      return m_rows[idx].sessionName;
   }

   bool FlattenOnAccountBreach(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return false;
      return m_rows[idx].flattenOnAccountBreach;
   }

   string GetReason(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return "";
      return m_rows[idx].reason;
   }

   string GetSessionCloseBehavior(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return "";
      return m_rows[idx].sessionCloseBehavior;
   }

   CorePortfolioGuardrails Guardrails() const
   {
      return m_guardrails;
   }

   int RowCount() const
   {
      return ArraySize(m_rows);
   }

   CorePortfolioPairPolicy GetRow(const int index) const
   {
      CorePortfolioPairPolicy empty;
      empty.valid = false;
      if(index < 0 || index >= ArraySize(m_rows))
         return empty;
      return m_rows[index];
   }

private:
   int FindRow(const string pair) const
   {
      int n = ArraySize(m_rows);
      for(int i = 0; i < n; i++)
      {
         if(m_rows[i].pair == pair)
            return i;
      }
      return -1;
   }
};

#endif
