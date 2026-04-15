#pragma once

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
      return StringToDouble(StringTrim(StringSubstr(block, pos, end - pos)));
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
      out.stepPips = 0.0;
      out.initialLot = 0.0;
      out.multiplier = 1.0;
      out.maxTradesPerSide = 0;
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
      out.stepPips = ExtractDouble(block, "step_pips");
      out.initialLot = ExtractDouble(block, "initial_lot");
      out.multiplier = ExtractDouble(block, "multiplier");
      out.maxTradesPerSide = ExtractInt(block, "max_trades_per_side");
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

      out.valid = true;
      return out;
     }

   string GetLastError()
     {
      return m_lastError;
     }
  };
