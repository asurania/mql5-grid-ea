#pragma once

#include <ForexSlave/Config.mqh>
#include <ForexSlave/EntrySignal.mqh>

class CEntryIntentReader
  {
private:
   string m_rawJson;
   string m_lastError;
   datetime m_generatedAt;
   datetime m_expiresAt;

   bool LoadFile()
     {
      m_rawJson = "";
      int handle = FileOpen("ForexSlave\\entry_intent.json", FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
      if(handle == INVALID_HANDLE)
        {
         m_lastError = "could not open entry intent file";
         return false;
        }

      while(!FileIsEnding(handle))
         m_rawJson += FileReadString(handle);
      FileClose(handle);

      if(StringLen(m_rawJson) == 0)
        {
         m_lastError = "entry intent file empty";
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

public:
   CEntryIntentReader()
     {
      m_lastError = "not loaded";
      m_generatedAt = 0;
      m_expiresAt = 0;
     }

   EntryDecision Evaluate(string pair)
     {
      EntryDecision out;
      out.shouldEnter = false;
      out.direction = ENTRY_NONE;
      out.lots = 0.0;
      out.reason = "entry intent unavailable";

      m_lastError = "";
      m_generatedAt = 0;
      m_expiresAt = 0;

      if(!LoadFile())
        {
         out.reason = m_lastError;
         return out;
        }

      string block = FindPairBlock(pair);
      if(block == "")
        {
         m_lastError = "pair block not found in entry intent";
         out.reason = m_lastError;
         return out;
        }

      bool shouldEnter = ExtractBool(block, "should_enter", false);
      string direction = ExtractString(block, "direction");
      string reason = ExtractString(block, "reason");
      double lots = ExtractDouble(block, "suggested_lots");
      string expiresText = ExtractString(block, "expires_at_utc");

      m_expiresAt = StringToTime(expiresText);
      if(m_expiresAt <= 0)
        {
         out.reason = "invalid expires_at_utc";
         return out;
        }

      if(TimeGMT() > m_expiresAt)
        {
         out.reason = "entry intent expired";
         return out;
        }

      out.shouldEnter = shouldEnter;
      out.lots = lots;
      out.reason = reason;

      if(!shouldEnter)
        {
         out.direction = ENTRY_NONE;
         return out;
        }

      if(direction == "buy")
         out.direction = ENTRY_BUY;
      else if(direction == "sell")
         out.direction = ENTRY_SELL;
      else
        {
         out.direction = ENTRY_NONE;
         out.shouldEnter = false;
         out.reason = "direction missing or none";
         return out;
        }

      return out;
     }

   string GetLastError()
     {
      return m_lastError;
     }
  };
