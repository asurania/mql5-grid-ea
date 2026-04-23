#ifndef __FOREXSLAVE_PAIR_RISK_POLICY_READER_MQH__
#define __FOREXSLAVE_PAIR_RISK_POLICY_READER_MQH__

#include <JAson.mqh>

struct PairRiskRow
{
   string pair;
   bool enabled;
   bool allowNewEntries;
   string policyAction;
   datetime expiresAt;
   string reason;
   bool valid;
};

class PairRiskPolicyReader
{
private:
   string m_filePath;
   PairRiskRow m_rows[];
   string m_lastError;

public:
   PairRiskPolicyReader(const string filePath = "ForexSlave\\pair_risk_policy.json")
   {
      m_filePath = filePath;
      m_lastError = "";
      ArrayResize(m_rows, 0);
   }

   bool Refresh()
   {
      m_lastError = "";
      ArrayResize(m_rows, 0);

      int handle = FileOpen(m_filePath, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(handle == INVALID_HANDLE)
      {
         m_lastError = "pair_risk_file_open_failed";
         return false;
      }

      string raw = "";
      while(!FileIsEnding(handle))
         raw += FileReadString(handle);
      FileClose(handle);

      if(StringLen(raw) == 0)
      {
         m_lastError = "pair_risk_empty";
         return false;
      }

      CJAVal root;
      if(!root.Deserialize(raw))
      {
         m_lastError = "pair_risk_json_parse_failed";
         return false;
      }

      if(!root.HasKey("pairs"))
      {
         m_lastError = "pair_risk_missing_pairs";
         return false;
      }

      CJAVal pairs = root["pairs"];
      int count = pairs.Size();
      ArrayResize(m_rows, count);
      for(int i = 0; i < count; i++)
      {
         CJAVal row = pairs[i];
         PairRiskRow out;
         out.valid = false;
         out.pair = row["pair"].ToStr();
         out.enabled = row["enabled"].ToBool();
         out.allowNewEntries = row["allow_new_entries"].ToBool();
         out.policyAction = row["policy_action"].ToStr();
         out.expiresAt = StringToTime(row["expires_at_utc"].ToStr());
         out.reason = row["reason"].ToStr();
         if(out.pair == "" || !out.enabled || !out.allowNewEntries || out.policyAction != "allow_trading" || out.expiresAt <= TimeGMT())
         {
            m_rows[i] = out;
            continue;
         }
         out.valid = true;
         m_rows[i] = out;
      }
      return true;
   }

   string LastError() const
   {
      return m_lastError;
   }

   bool HasFreshAllowance(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return false;
      return m_rows[idx].valid;
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
