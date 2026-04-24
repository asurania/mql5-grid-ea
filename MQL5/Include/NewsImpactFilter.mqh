//+------------------------------------------------------------------+
//|                                      NewsImpactFilter.mqh        |
//|                     Enhanced News Impact Filter for Grid EA       |
//|                                                                  |
//|  Integrates with ConvertedGridEA.mq5 to block trading during      |
//|  high-impact economic events based on ML-generated scores.        |
//+------------------------------------------------------------------+

#ifndef NEWS_IMPACT_FILTER_MQH
#define NEWS_IMPACT_FILTER_MQH

//--- Struct to hold event data
struct news_event
{
   datetime   date;
   string     symbol;
   string     event_name;
   double     score;
   string     bucket_class;
};

//--- Global variables
news_event news_events[];
datetime   last_news_load=0;
int        news_event_count=0;

//+------------------------------------------------------------------+
//| Load news impact data from CSV                                   |
//+------------------------------------------------------------------+
bool LoadNewsImpactFile(string filename)
{
   // Check if we need to reload (every hour)
   if(TimeCurrent()-last_news_load < 3600 && news_event_count > 0)
      return true;
   
   // Try multiple paths
   string paths[];
   ArrayResize(paths, 5);
   paths[0] = filename;  // Just the filename (uses MQL5/Files)
   paths[1] = TerminalInfoString(TERMINAL_DATA_PATH)+"\\MQL5\\Files\\"+filename;
   paths[2] = TerminalInfoString(TERMINAL_COMMONDATA_PATH)+"\\MQL5\\Files\\"+filename;
   paths[3] = TerminalInfoString(TERMINAL_DATA_PATH)+"\\"+filename;
   paths[4] = TerminalInfoString(TERMINAL_COMMONDATA_PATH)+"\\"+filename;
   
   int handle = INVALID_HANDLE;
   string used_path = "";
   
   for(int i=0; i<ArraySize(paths); i++)
   {
      if(FileIsExist(paths[i]))
      {
         handle = FileOpen(paths[i], FILE_READ|FILE_TXT|FILE_COMMON);
         if(handle != INVALID_HANDLE)
         {
            used_path = paths[i];
            Print("NewsImpactFilter: Found file at: ", used_path);
            break;
         }
      }
   }
   
   if(handle == INVALID_HANDLE)
   {
      Print("NewsImpactFilter: File not found in any location. Tried:");
      for(int i=0; i<ArraySize(paths); i++)
         Print("  ", i, ": ", paths[i], " Exists=", FileIsExist(paths[i]));
      return false;
   }
   
   // Skip header line
   FileReadString(handle);
   
   // Clear existing events
   ArrayResize(news_events, 0);
   news_event_count=0;
   
   // Read all lines
   while(!FileIsEnding(handle))
   {
      string line=FileReadString(handle);
      if(line=="") continue;
      
      // Parse CSV line: Date,Forex Symbol,Calendar Event,Score,Bucket Class
      string fields[];
      int field_count=StringSplit(line, ',', fields);
      if(field_count < 5) continue;
      
      ArrayResize(news_events, news_event_count+1);
      
      // Parse date: 2026-04-29 18:00:00+00:00 or 2026-04-29 18:00:00
      string date_str=fields[0];
      // Remove timezone offset if present
      StringReplace(date_str, "+00:00", "");
      StringReplace(date_str, "Z", "");
      // Remove any trailing whitespace
      StringTrimLeft(date_str);
      StringTrimRight(date_str);
      news_events[news_event_count].date=StringToTime(date_str);
      
      news_events[news_event_count].symbol=fields[1];
      news_events[news_event_count].event_name=fields[2];
      news_events[news_event_count].score=StringToDouble(fields[3]);
      news_events[news_event_count].bucket_class=fields[4];
      
      news_event_count++;
   }
   
   FileClose(handle);
   last_news_load=TimeCurrent();
   Print("NewsImpactFilter: Loaded ", news_event_count, " events from ", used_path);
   
   return true;
}

//+------------------------------------------------------------------+
//| Check if symbol matches current chart                             |
//+------------------------------------------------------------------+
bool SymbolMatches(string event_symbol, string chart_symbol)
{
   // Direct match
   if(event_symbol==chart_symbol) return true;
   
   // Handle different naming conventions (EURUSD vs EUR/USD)
   string normalized_event=event_symbol;
   string normalized_chart=chart_symbol;
   
   StringReplace(normalized_event, "/", "");
   StringReplace(normalized_chart, "/", "");
   StringReplace(normalized_event, " ", "");
   StringReplace(normalized_chart, " ", "");
   
   return (normalized_event==normalized_chart);
}

//+------------------------------------------------------------------+
//| Check if trading should be blocked due to news impact             |
//+------------------------------------------------------------------+
bool IsNewsBlockingTrade(string symbol, double score_threshold, int pre_minutes, int post_minutes)
{
   datetime now=TimeCurrent();
   
   for(int i=0; i<news_event_count; i++)
   {
      // Check symbol match
      if(!SymbolMatches(news_events[i].symbol, symbol))
         continue;
      
      // Check if score meets threshold
      if(news_events[i].score < score_threshold)
         continue;
      
      // Calculate blocking window
      datetime block_start=news_events[i].date - pre_minutes * 60;
      datetime block_end=news_events[i].date + post_minutes * 60;
      
      // Check if we're in the blocking window
      if(now >= block_start && now <= block_end)
      {
         // Debug output (throttled)
         static datetime last_alert=0;
         if(now-last_alert > 300)  // Alert every 5 minutes
         {
            Print("NewsImpactFilter: BLOCKING trade for ", symbol, 
                  " | Event: ", news_events[i].event_name,
                  " | Score: ", news_events[i].score,
                  " | Class: ", news_events[i].bucket_class,
                  " | Window: ", TimeToString(block_start), " - ", TimeToString(block_end));
            last_alert=now;
         }
         return true;
      }
   }
   
   return false;
}

//+------------------------------------------------------------------+
//| Get current active news events for display                        |
//+------------------------------------------------------------------+
string GetActiveNewsEvents(string symbol, double score_threshold, int pre_minutes, int post_minutes)
{
   string result="";
   datetime now=TimeCurrent();
   
   for(int i=0; i<news_event_count; i++)
   {
      if(!SymbolMatches(news_events[i].symbol, symbol))
         continue;
      
      if(news_events[i].score < score_threshold)
         continue;
      
      datetime block_start=news_events[i].date - pre_minutes * 60;
      datetime block_end=news_events[i].date + post_minutes * 60;
      
      if(now >= block_start && now <= block_end)
      {
         if(result!="") result+="\n";
         result+=TimeToString(news_events[i].date, TIME_MINUTES)+" "+
                  news_events[i].event_name+" ("+
                  DoubleToString(news_events[i].score, 1)+")";
      }
   }
   
   return result;
}

//+------------------------------------------------------------------+
//| Get next upcoming event for symbol                                |
//+------------------------------------------------------------------+
string GetNextNewsEvent(string symbol, double score_threshold)
{
   string result="";
   datetime now=TimeCurrent();
   datetime next_time=0;
   
   for(int i=0; i<news_event_count; i++)
   {
      if(!SymbolMatches(news_events[i].symbol, symbol))
         continue;
      
      if(news_events[i].score < score_threshold)
         continue;
      
      if(news_events[i].date > now && (next_time==0 || news_events[i].date < next_time))
      {
         next_time=news_events[i].date;
         result=TimeToString(news_events[i].date)+" "+
                news_events[i].event_name+" (Score: "+
                DoubleToString(news_events[i].score, 1)+", Class: "+
                news_events[i].bucket_class+")";
      }
   }
   
   return result;
}

//+------------------------------------------------------------------+
//| Clean up resources                                               |
//+------------------------------------------------------------------+
void CleanupNewsFilter()
{
   ArrayResize(news_events, 0);
   news_event_count=0;
   last_news_load=0;
}

#endif // NEWS_IMPACT_FILTER_MQH
