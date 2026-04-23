#ifndef __FOREXSLAVE_COOLDOWN_REGISTRY_MQH__
#define __FOREXSLAVE_COOLDOWN_REGISTRY_MQH__

struct CooldownEntry
{
   string key;
   datetime until;
};

class CooldownRegistry
{
private:
   static CooldownEntry m_entries[];
   static string m_filePath;
   static bool m_loaded;

   static int FindIndex(const string key)
   {
      int n = ArraySize(m_entries);
      for(int i = 0; i < n; i++)
      {
         if(m_entries[i].key == key)
            return i;
      }
      return -1;
   }

public:
   static void EnsureLoaded()
   {
      if(m_loaded)
         return;
      m_loaded = true;

      int handle = FileOpen(m_filePath, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(handle == INVALID_HANDLE)
         return;

      while(!FileIsEnding(handle))
      {
         string line = FileReadString(handle);
         if(line == "")
            continue;

         string parts[];
         int n = StringSplit(line, '|', parts);
         if(n != 2)
            continue;

         datetime until = (datetime)StringToInteger(parts[1]);
         if(until <= TimeCurrent())
            continue;

         int idx = ArraySize(m_entries);
         ArrayResize(m_entries, idx + 1);
         m_entries[idx].key = parts[0];
         m_entries[idx].until = until;
      }
      FileClose(handle);
   }

   static void Save()
   {
      int handle = FileOpen(m_filePath, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(handle == INVALID_HANDLE)
         return;

      int n = ArraySize(m_entries);
      for(int i = 0; i < n; i++)
      {
         if(m_entries[i].until <= TimeCurrent())
            continue;
         FileWrite(handle, m_entries[i].key + "|" + IntegerToString((int)m_entries[i].until));
      }
      FileClose(handle);
   }

   static void PruneExpired()
   {
      EnsureLoaded();

      CooldownEntry kept[];
      int count = 0;
      int n = ArraySize(m_entries);
      datetime now = TimeCurrent();
      for(int i = 0; i < n; i++)
      {
         if(m_entries[i].until <= now)
            continue;
         ArrayResize(kept, count + 1);
         kept[count] = m_entries[i];
         count++;
      }

      ArrayResize(m_entries, count);
      for(int j = 0; j < count; j++)
         m_entries[j] = kept[j];
      Save();
   }

   static string MakeKey(const string pair, const string scope)
   {
      return pair + ":" + scope;
   }

   static void SetCooldown(const string pair, const string scope, const int seconds)
   {
      EnsureLoaded();
      PruneExpired();

      string key = MakeKey(pair, scope);
      datetime until = TimeCurrent() + seconds;
      int idx = FindIndex(key);
      if(idx < 0)
      {
         int n = ArraySize(m_entries);
         ArrayResize(m_entries, n + 1);
         m_entries[n].key = key;
         m_entries[n].until = until;
      }
      else
      {
         m_entries[idx].until = until;
      }
      Save();
   }

   static bool IsBlocked(const string pair, const string scope)
   {
      EnsureLoaded();
      PruneExpired();

      string key = MakeKey(pair, scope);
      int idx = FindIndex(key);
      if(idx < 0)
         return false;
      return TimeCurrent() < m_entries[idx].until;
   }

   static int RemainingSeconds(const string pair, const string scope)
   {
      EnsureLoaded();
      PruneExpired();

      string key = MakeKey(pair, scope);
      int idx = FindIndex(key);
      if(idx < 0)
         return 0;

      int remaining = (int)(m_entries[idx].until - TimeCurrent());
      return remaining > 0 ? remaining : 0;
   }

   static void ClearCooldown(const string pair, const string scope)
   {
      EnsureLoaded();
      PruneExpired();

      string key = MakeKey(pair, scope);
      int idx = FindIndex(key);
      if(idx < 0)
         return;

      int n = ArraySize(m_entries);
      for(int i = idx; i < n - 1; i++)
         m_entries[i] = m_entries[i + 1];
      ArrayResize(m_entries, n - 1);
      Save();
   }
};

CooldownEntry CooldownRegistry::m_entries[];
string CooldownRegistry::m_filePath = "ForexSlave\\cooldowns.txt";
bool CooldownRegistry::m_loaded = false;

#endif
