#ifndef __FOREXSLAVE_GRID_POLICY_READER_MQH__
#define __FOREXSLAVE_GRID_POLICY_READER_MQH__

#include <JAson.mqh>

struct GridPolicyPairRow
{
   string   pair;
   bool     allowNewBasket;
   string   policyId;
   string   gridMode;
   string   seedMode;
   double   stepPips;
   double   initialLot;
   double   multiplier;
   int      maxTradesPerSide;
   double   basketTpCurrency;
   double   basketTpPips;
   double   basketSlPips;
   double   maxGrossLots;
   double   maxBasketDrawdownCurrency;
   double   minStepToSpreadRatio;
   double   minFreeMarginPercent;
   bool     flattenOnStrongAvoid;
   bool     brokerVisibleTpSl;
   double   confidence;
   string   reason;
   string   sessionName;
   double   predictedRangePips;
   datetime expiresAt;
   bool     valid;
};

struct GridPolicyHeader
{
   string   version;
   string   model;
   string   riskMode;
   double   accountEquity;
   double   riskBudgetCurrency;
   double   targetProfitCurrency;
   string   sessionName;
   datetime sessionCloseUtc;
   datetime managedCloseUtc;
   datetime liquidateUtc;
   datetime dailyLiquidateUtc;
   bool     valid;
};

class GridPolicyReader
{
private:
   string              m_filePath;
   GridPolicyHeader    m_header;
   GridPolicyPairRow   m_rows[];
   string              m_lastError;

public:
   GridPolicyReader(const string filePath = "ForexSlave\\grid_policy.json")
   {
      m_filePath = filePath;
      m_header.valid = false;
      ArrayResize(m_rows, 0);
      m_lastError = "";
   }

   bool Refresh()
   {
      m_lastError = "";
      m_header.valid = false;
      ArrayResize(m_rows, 0);

      int handle = FileOpen(m_filePath, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(handle == INVALID_HANDLE)
      {
         m_lastError = "grid_policy_file_open_failed";
         return false;
      }

      string raw = "";
      while(!FileIsEnding(handle))
         raw += FileReadString(handle);
      FileClose(handle);

      if(StringLen(raw) == 0)
      {
         m_lastError = "grid_policy_empty";
         return false;
      }

      CJAVal root;
      if(!root.Deserialize(raw))
      {
         m_lastError = "grid_policy_json_parse_failed";
         return false;
      }

      // Parse header
      m_header.version = root["version"].ToStr();
      m_header.model = root["model"].ToStr();
      m_header.riskMode = root["risk_mode"].ToStr();
      m_header.accountEquity = root["account_equity"].ToDbl();
      m_header.riskBudgetCurrency = root["risk_budget_currency"].ToDbl();
      m_header.targetProfitCurrency = root["target_profit_currency"].ToDbl();
      m_header.sessionName = root["session_name"].ToStr();
      m_header.sessionCloseUtc = StringToTime(root["session_close_utc"].ToStr());
      m_header.managedCloseUtc = StringToTime(root["managed_close_utc"].ToStr());
      m_header.liquidateUtc = StringToTime(root["liquidate_utc"].ToStr());
      m_header.dailyLiquidateUtc = StringToTime(root["daily_liquidate_utc"].ToStr());
      m_header.valid = true;

      // Parse pairs
      CJAVal *pairs = root["pairs"];
      if(pairs == NULL || pairs.Size() <= 0)
      {
         m_lastError = "grid_policy_no_pairs";
         return false;
      }

      int count = pairs.Size();
      ArrayResize(m_rows, count);
      for(int i = 0; i < count; i++)
      {
         CJAVal *row = pairs[i];
         GridPolicyPairRow r;
         r.valid = false;

         r.pair = row["pair"].ToStr();
         r.allowNewBasket = row["allow_new_basket"].ToBool();
         r.policyId = row["policy_id"].ToStr();
         r.gridMode = row["grid_mode"].ToStr();
         r.seedMode = row["seed_mode"].ToStr();
         r.stepPips = row["step_pips"].ToDbl();
         r.initialLot = row["initial_lot"].ToDbl();
         r.multiplier = row["multiplier"].ToDbl();
         r.maxTradesPerSide = (int)row["max_trades_per_side"].ToInt();
         r.basketTpCurrency = row["basket_tp_currency"].ToDbl();
         r.basketTpPips = row["basket_tp_pips"].ToDbl();
         r.basketSlPips = row["basket_sl_pips"].ToDbl();
         r.maxGrossLots = row["max_gross_lots"].ToDbl();
         r.maxBasketDrawdownCurrency = row["max_basket_drawdown_currency"].ToDbl();
         r.minStepToSpreadRatio = row["min_step_to_spread_ratio"].ToDbl();
         r.minFreeMarginPercent = row["min_free_margin_percent"].ToDbl();
         r.flattenOnStrongAvoid = row["flatten_on_strong_avoid"].ToBool();
         r.brokerVisibleTpSl = row["broker_visible_tp_sl"].ToBool();
         r.confidence = row["confidence"].ToDbl();
         r.reason = row["reason"].ToStr();
         r.sessionName = row["session_name"].ToStr();
         r.predictedRangePips = row["predicted_range_pips"].ToDbl();
         r.expiresAt = StringToTime(row["expires_at_utc"].ToStr());

         if(r.pair == "" || r.stepPips <= 0.0 || r.initialLot <= 0.0 || r.multiplier < 1.0)
         {
            m_lastError = "grid_policy_invalid_pair_row pair=" + r.pair;
            return false;
         }

         r.valid = true;
         m_rows[i] = r;
      }

      return true;
   }

   string LastError() { return m_lastError; }

   GridPolicyHeader GetHeader() { return m_header; }

   int RowCount() { return ArraySize(m_rows); }

   bool HasFreshRow(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return false;
      if(!m_rows[idx].valid) return false;
      if(m_rows[idx].expiresAt <= TimeGMT()) return false;
      return true;
   }

   // Convenience accessors (non-const for MQL5 compatibility)
   double GetStepPips(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return 0.0;
      return m_rows[idx].stepPips;
   }

   double GetInitialLot(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return 0.0;
      return m_rows[idx].initialLot;
   }

   double GetMultiplier(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return 0.0;
      return m_rows[idx].multiplier;
   }

   int GetMaxTradesPerSide(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return 0;
      return m_rows[idx].maxTradesPerSide;
   }

   double GetBasketTpCurrency(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return 0.0;
      return m_rows[idx].basketTpCurrency;
   }

   double GetBasketTpPips(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return 0.0;
      return m_rows[idx].basketTpPips;
   }

   double GetMaxGrossLots(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return 0.0;
      return m_rows[idx].maxGrossLots;
   }

   double GetMaxBasketDrawdownCurrency(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return 0.0;
      return m_rows[idx].maxBasketDrawdownCurrency;
   }

   double GetMinStepToSpreadRatio(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return 0.0;
      return m_rows[idx].minStepToSpreadRatio;
   }

   double GetMinFreeMarginPercent(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return 0.0;
      return m_rows[idx].minFreeMarginPercent;
   }

   bool GetFlattenOnStrongAvoid(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return false;
      return m_rows[idx].flattenOnStrongAvoid;
   }

   bool GetBrokerVisibleTpSl(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return true;
      return m_rows[idx].brokerVisibleTpSl;
   }

   string GetGridMode(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return "";
      return m_rows[idx].gridMode;
   }

   string GetSeedMode(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return "";
      return m_rows[idx].seedMode;
   }

   bool AllowNewBasket(const string pair)
   {
      int idx = FindRow(pair);
      if(idx < 0) return false;
      return m_rows[idx].valid && m_rows[idx].allowNewBasket;
   }

private:
   int FindRow(const string pair)
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