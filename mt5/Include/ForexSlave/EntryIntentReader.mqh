#ifndef __FOREXSLAVE_ENTRY_INTENT_READER_MQH__
#define __FOREXSLAVE_ENTRY_INTENT_READER_MQH__

#include <JAson.mqh>

struct EntryIntentRow
{
   string pair;
   bool enabled;
   bool allowFirstEntry;
   string direction;
   double confidence;
   datetime expiresAt;
   string reason;
   bool valid;
};

class EntryIntentReader
{
private:
   string m_filePath;
   EntryIntentRow m_rows[];
   string m_lastError;

public:
   EntryIntentReader(const string filePath = "ForexSlave\\entry_intent.json")
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
         m_lastError = "entry_intent_file_open_failed";
         return false;
      }

      string raw = "";
      while(!FileIsEnding(handle))
         raw += FileReadString(handle);
      FileClose(handle);

      if(StringLen(raw) == 0)
      {
         m_lastError = "entry_intent_empty";
         return false;
      }

      CJAVal root;
      if(!root.Deserialize(raw))
      {
         m_lastError = "entry_intent_json_parse_failed";
         return false;
      }

      if(!root.HasKey("pairs"))
      {
         m_lastError = "entry_intent_missing_pairs";
         return false;
      }

      CJAVal pairs = root["pairs"];
      int count = pairs.Size();
      ArrayResize(m_rows, count);
      for(int i = 0; i < count; i++)
      {
         CJAVal row = pairs[i];
         EntryIntentRow out;
         out.valid = false;
         out.pair = row["pair"].ToStr();
         out.enabled = row["enabled"].ToBool();
         out.allowFirstEntry = row["allow_first_entry"].ToBool();
         out.direction = row["direction"].ToStr();
         out.confidence = row.HasKey("confidence") ? row["confidence"].ToDbl() : 0.0;
         out.expiresAt = StringToTime(row["expires_at_utc"].ToStr());
         out.reason = row["reason"].ToStr();
         if(out.pair == "" || !out.enabled || !out.allowFirstEntry || (out.direction != "buy" && out.direction != "sell" && out.direction != "both") || out.expiresAt <= TimeGMT())
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

   bool HasFreshIntent(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return false;
      return m_rows[idx].valid;
   }

   string GetDirection(const string pair) const
   {
      int idx = FindRow(pair);
      if(idx < 0)
         return "";
      return m_rows[idx].direction;
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
