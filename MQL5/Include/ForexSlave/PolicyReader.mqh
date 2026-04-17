#ifndef __POLICYREADER_MQH__
#define __POLICYREADER_MQH__


#include <ForexSlave/Types.mqh>
#include <ForexSlave/Config.mqh>

class CPolicyReader
  {
private:
   PairPolicy m_policy;
   string     m_lastError;
   string     m_rawJson;

   void SetDefaultPolicy(PolicyStatus status,string errorText)
     {
      m_policy.pair = _Symbol;
      m_policy.action = POLICY_INVALID;
      m_policy.policyBand = "unknown";
      m_policy.maxScoreAvoidSession = 0.0;
      m_policy.triggerEventId = "";
      m_policy.triggerEventName = "";
      m_policy.triggerEventTime = 0;
      m_policy.generatedAt = 0;
      m_policy.status = status;
      m_lastError = errorText;
     }

   bool LoadFile()
     {
      m_rawJson = "";
      int handle = FileOpen(InpPolicyFilePath, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
      if(handle == INVALID_HANDLE)
        {
         SetDefaultPolicy(POLICY_STATUS_MISSING, "could not open policy file");
         return false;
        }

      while(!FileIsEnding(handle))
         m_rawJson += FileReadString(handle);
      FileClose(handle);

      if(StringLen(m_rawJson) == 0)
        {
         SetDefaultPolicy(POLICY_STATUS_INVALID, "policy file empty");
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

      string probe = StringSubstr(block, pos, 4);
      if(probe == "null")
         return "";

      if(StringSubstr(block, pos, 1) != "\"")
         return "";
      pos++;
      int end = pos;
      while(end < StringLen(block) && StringSubstr(block, end, 1) != "\"")
         end++;
      return StringSubstr(block, pos, end - pos);
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
      string raw = StringSubstr(block, pos, end - pos);
      StringTrimLeft(raw);
      StringTrimRight(raw);
      return StringToDouble(raw);
     }

   PolicyAction ParseAction(string value)
     {
      if(value == "allow_trading")
         return POLICY_ALLOW_TRADING;
      if(value == "soft_halt_new_entries")
         return POLICY_SOFT_HALT_NEW_ENTRIES;
      if(value == "block_new_entries")
         return POLICY_BLOCK_NEW_ENTRIES;
      if(value == "block_new_entries_and_flag_strong_avoid")
         return POLICY_BLOCK_NEW_ENTRIES_STRONG;
      return POLICY_INVALID;
     }

   PolicyStatus ComputeStatus(datetime generatedAt)
     {
      if(generatedAt <= 0)
         return POLICY_STATUS_INVALID;

      int age = (int)(TimeGMT() - generatedAt);
      if(age <= InpFreshnessWarningSeconds)
         return POLICY_STATUS_FRESH;
      if(age <= InpFreshnessFailSafeSeconds)
         return POLICY_STATUS_STALE_WARNING;
      return POLICY_STATUS_STALE_FAIL_SAFE;
     }

public:
   CPolicyReader()
     {
      SetDefaultPolicy(POLICY_STATUS_MISSING, "policy not loaded");
     }

   bool Refresh()
     {
      SetDefaultPolicy(POLICY_STATUS_MISSING, "policy not loaded");
      if(!LoadFile())
         return false;

      string block = FindPairBlock(_Symbol);
      if(block == "")
        {
         SetDefaultPolicy(POLICY_STATUS_INVALID, "pair block not found in policy file");
         return false;
        }

      string actionText = ExtractString(block, "policy_action");
      string bandText = ExtractString(block, "policy_band");
      string eventId = ExtractString(block, "trigger_event_id");
      string eventName = ExtractString(block, "trigger_event_name");
      string eventTimeText = ExtractString(block, "trigger_event_timestamp_utc");
      string generatedText = ExtractString(block, "generated_at_utc");
      double score = ExtractDouble(block, "max_score_avoid_session");

      m_policy.pair = _Symbol;
      m_policy.action = ParseAction(actionText);
      m_policy.policyBand = bandText;
      m_policy.maxScoreAvoidSession = score;
      m_policy.triggerEventId = eventId;
      m_policy.triggerEventName = eventName;
      m_policy.triggerEventTime = StringToTime(eventTimeText);
      m_policy.generatedAt = StringToTime(generatedText);
      m_policy.status = ComputeStatus(m_policy.generatedAt);

      if(m_policy.action == POLICY_INVALID)
        {
         m_policy.status = POLICY_STATUS_INVALID;
         m_lastError = "invalid policy action";
         return false;
        }

      if(m_policy.status == POLICY_STATUS_INVALID)
        {
         m_lastError = "invalid generated_at_utc";
         return false;
        }

      m_lastError = "";
      return true;
     }

   PairPolicy GetPolicy(string pair)
     {
      PairPolicy out = m_policy;
      out.pair = pair;
      return out;
     }

   string GetLastError()
     {
      return m_lastError;
     }
  };

#endif
