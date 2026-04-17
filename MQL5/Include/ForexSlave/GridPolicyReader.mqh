#ifndef __GRIDPOLICYREADER_MQH__
#define __GRIDPOLICYREADER_MQH__


#include <ForexSlave/Types.mqh>

class CGridPolicyReader
  {
private:
   string m_rawJson;
   string m_lastError;

   bool LoadFile()
     {
      m_rawJson = "";
      int handle = FileOpen("ForexSlave\\grid_policy.json", FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
      if(handle == INVALID_HANDLE)
        {
         m_lastError = "could not open grid policy file";
         return false;
        }

      while(!FileIsEnding(handle))
         m_rawJson += FileReadString(handle);
      FileClose(handle);

      if(StringLen(m_rawJson) == 0)
        {
         m_lastError = "grid policy file empty";
         return false;
        }
      return true;
     }

   string FindPairBlock(string pair)
     {
      string key = "\"pair\": \"" + pair + "\"";
      int pairPos = StringFind(m_rawJson, key);
      if(pairPos < 0)
         return "";

      int start = pairPos;
      while(start > 0 && StringSubstr(m_rawJson, start, 1) != "{")
         start--;

      int end = pairPos;
      while(end < StringLen(m_rawJson) && StringSubstr(m_rawJson, end, 1) != "}")
         end++;

      if(end <= start)
         return "";
      return StringSubstr(m_rawJson, start, end - start + 1);
     }

   string ExtractString(string block,string field)
     {
      string needle = "\"" + field + "\": ";
      int pos = StringFind(block, needle);
      if(pos < 0)
         return "";
      pos += StringLen(needle);

      if(StringSubstr(block, pos, 1) != "\"")
         return "";
      pos++;
      int end = pos;
      while(end < StringLen(block) && StringSubstr(block, end, 1) != "\"")
         end++;
      return StringSubstr(block, pos, end - pos);
     }

   bool ExtractBool(string block,string field,bool defaultValue=false)
     {
      string needle = "\"" + field + "\": ";
      int pos = StringFind(block, needle);
      if(pos < 0)
         return defaultValue;
      pos += StringLen(needle);
      string probe = StringSubstr(block, pos, 5);
      if(StringFind(probe, "true") == 0)
         return true;
      if(StringFind(probe, "false") == 0)
         return false;
      return defaultValue;
     }

   double ExtractDouble(string block,string field)
     {
      string needle = "\"" + field + "\": ";
      int pos = StringFind(block, needle);
      if(pos < 0)
         return 0.0;
      pos += StringLen(needle);
      int end = pos;
      while(end < StringLen(block))
        {
         string ch = StringSubstr(block, end, 1);
         if(ch == "," || ch == "}" || ch == "\n" || ch == "\r")
            break;
         end++;
        }
      string value = StringSubstr(block, pos, end - pos);
      StringTrimLeft(value);
      StringTrimRight(value);
      return StringToDouble(value);
     }

   int ExtractInt(string block,string field)
     {
      return (int)ExtractDouble(block, field);
     }

   GridMode ParseGridMode(string value)
     {
      if(value == "both_sides")
         return GRID_MODE_BOTH_SIDES;
      if(value == "buy_only")
         return GRID_MODE_BUY_ONLY;
      if(value == "sell_only")
         return GRID_MODE_SELL_ONLY;
      return GRID_MODE_INVALID;
     }

   SeedMode ParseSeedMode(string value)
     {
      if(value == "single_side" || value == "")
         return SEED_MODE_SINGLE_SIDE;
      if(value == "both_sides")
         return SEED_MODE_BOTH_SIDES;
      return SEED_MODE_INVALID;
     }

public:
   CGridPolicyReader()
     {
      m_lastError = "not loaded";
     }

   GridPolicy Evaluate(string pair)
     {
      GridPolicy out;
      out.pair = pair;
      out.allowNewBasket = false;
      out.policyId = "";
      out.gridMode = GRID_MODE_INVALID;
      out.seedMode = SEED_MODE_SINGLE_SIDE;
      out.stepPips = 0.0;
      out.initialLot = 0.0;
      out.multiplier = 1.0;
      out.maxTradesPerSide = 0;
      out.basketTpCurrency = 0.0;
      out.maxGrossLots = 0.0;
      out.maxBasketDrawdownCurrency = 0.0;
      out.minStepToSpreadRatio = 0.0;
      out.minFreeMarginPercent = 0.0;
      out.flattenOnStrongAvoid = true;
      out.confidence = 0.0;
      out.reason = "grid policy unavailable";
      out.expiresAt = 0;
      out.valid = false;

      m_lastError = "";

      if(!LoadFile())
        {
         out.reason = m_lastError;
         return out;
        }

      string block = FindPairBlock(pair);
      if(block == "")
        {
         m_lastError = "pair block not found in grid policy";
         out.reason = m_lastError;
         return out;
        }

      out.allowNewBasket = ExtractBool(block, "allow_new_basket", false);
      out.policyId = ExtractString(block, "policy_id");
      out.gridMode = ParseGridMode(ExtractString(block, "grid_mode"));
      out.seedMode = ParseSeedMode(ExtractString(block, "seed_mode"));
      out.stepPips = ExtractDouble(block, "step_pips");
      out.initialLot = ExtractDouble(block, "initial_lot");
      out.multiplier = ExtractDouble(block, "multiplier");
      out.maxTradesPerSide = ExtractInt(block, "max_trades_per_side");
      out.basketTpCurrency = ExtractDouble(block, "basket_tp_currency");
      out.basketTpPips = ExtractDouble(block, "basket_tp_pips");
      out.basketSlPips = ExtractDouble(block, "basket_sl_pips");
      out.maxGrossLots = ExtractDouble(block, "max_gross_lots");
      out.maxBasketDrawdownCurrency = ExtractDouble(block, "max_basket_drawdown_currency");
      out.minStepToSpreadRatio = ExtractDouble(block, "min_step_to_spread_ratio");
      out.minFreeMarginPercent = ExtractDouble(block, "min_free_margin_percent");
      out.flattenOnStrongAvoid = ExtractBool(block, "flatten_on_strong_avoid", true);
      out.brokerVisibleTpSl = ExtractBool(block, "broker_visible_tp_sl", true);
      out.confidence = ExtractDouble(block, "confidence");
      out.reason = ExtractString(block, "reason");
      out.expiresAt = StringToTime(ExtractString(block, "expires_at_utc"));

      if(out.expiresAt <= 0)
        {
         out.reason = "invalid expires_at_utc";
         return out;
        }

      if(TimeGMT() > out.expiresAt)
        {
         out.reason = "grid policy expired";
         return out;
        }

      if(!out.allowNewBasket)
        {
         out.reason = out.reason == "" ? "grid policy disallows basket" : out.reason;
         out.valid = true;
         return out;
        }

      if(out.gridMode == GRID_MODE_INVALID)
        {
         out.reason = "invalid grid mode";
         return out;
        }
      if(out.seedMode == SEED_MODE_INVALID)
        {
         out.reason = "invalid seed mode";
         return out;
        }
      if(out.stepPips <= 0.0)
        {
         out.reason = "invalid step pips";
         return out;
        }
      if(out.initialLot <= 0.0)
        {
         out.reason = "invalid initial lot";
         return out;
        }
      if(out.multiplier < 1.0)
        {
         out.reason = "invalid multiplier";
         return out;
        }
      if(out.maxTradesPerSide < 1)
        {
         out.reason = "invalid max trades per side";
         return out;
        }
      if(out.basketTpCurrency < 0.0)
        {
         out.reason = "invalid basket tp currency";
         return out;
        }
      if(out.maxGrossLots < 0.0)
        {
         out.reason = "invalid max gross lots";
         return out;
        }
      if(out.maxBasketDrawdownCurrency < 0.0)
        {
         out.reason = "invalid max basket drawdown currency";
         return out;
        }
      if(out.minStepToSpreadRatio < 0.0)
        {
         out.reason = "invalid min step to spread ratio";
         return out;
        }
      if(out.minFreeMarginPercent < 0.0)
        {
         out.reason = "invalid min free margin percent";
         return out;
        }

      out.valid = true;
      return out;
     }

   string GetLastError()
     {
      return m_lastError;
     }

   // Extract top-level session timing fields from grid policy JSON
   // Returns true if all required timestamps were found and parsed
   bool ExtractSessionTimings(datetime &managedCloseUTC, datetime &dailyLiquidateUTC, datetime &sessionCloseUTC)
     {
      if(m_rawJson == "")
        {
         if(!LoadFile())
            return false;
        }

      string mcStr = ExtractStringTopLevel("managed_close_utc");
      string dlStr = ExtractStringTopLevel("daily_liquidate_utc");
      string scStr = ExtractStringTopLevel("session_close_utc");

      managedCloseUTC = StringToTime(mcStr);
      dailyLiquidateUTC = StringToTime(dlStr);
      sessionCloseUTC = StringToTime(scStr);

      return (managedCloseUTC > 0 && dailyLiquidateUTC > 0 && sessionCloseUTC > 0);
     }

   // Extract a string value from the top-level JSON (not per-pair)
   string ExtractStringTopLevel(string field)
     {
      string needle = "\"" + field + "\": ";
      int pos = StringFind(m_rawJson, needle);
      if(pos < 0)
         return "";
      pos += StringLen(needle);

      if(StringSubstr(m_rawJson, pos, 1) != "\"")
         return "";
      pos++;
      int end = pos;
      while(end < StringLen(m_rawJson) && StringSubstr(m_rawJson, end, 1) != "\"")
         end++;
      return StringSubstr(m_rawJson, pos, end - pos);
     }
  };

#endif
