#ifndef __FOREXSLAVE_TELEMETRY_LOGGER_MQH__
#define __FOREXSLAVE_TELEMETRY_LOGGER_MQH__

#include <ForexSlave/SlaveIdentity.mqh>

class TelemetryLogger
{
private:
   static string m_filePath;
   static int m_writeCounter;
   static datetime m_lastFlush;
   static const int FLUSH_INTERVAL_SECONDS;

   static void WriteLine(const string level, const string scope, const string detail)
   {
      datetime now = TimeCurrent();
      string timestamp = TimeToString(now, TIME_DATE | TIME_SECONDS);
      string line = timestamp + "|" + level + "|" + scope + "|" + detail;

      Print("[", scope, "] ", (level == "ERROR" ? "ERROR: " : ""), detail);

      int handle = FileOpen(m_filePath, FILE_READ | FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(handle == INVALID_HANDLE)
         return;
      FileSeek(handle, 0, SEEK_END);
      FileWrite(handle, line);
      m_writeCounter++;
      FileClose(handle);

      if(m_writeCounter >= 100 || (int)(now - m_lastFlush) >= FLUSH_INTERVAL_SECONDS)
      {
         RotateIfNeeded();
         m_writeCounter = 0;
         m_lastFlush = now;
      }
   }

   static void RotateIfNeeded()
   {
      int handle = FileOpen(m_filePath, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(handle == INVALID_HANDLE)
         return;
      long sizeLong = (long)FileSize(handle);
      FileClose(handle);
      if(sizeLong < 5 * 1024 * 1024)
         return;

      string archivePath = "ForexSlave\\logs\\telemetry_" +
         TimeToString(TimeCurrent(), TIME_DATE) + ".log";
      int src = FileOpen(m_filePath, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
      int dst = FileOpen(archivePath, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(src != INVALID_HANDLE && dst != INVALID_HANDLE)
      {
         while(!FileIsEnding(src))
            FileWrite(dst, FileReadString(src));
         FileClose(dst);
      }
      if(src != INVALID_HANDLE)
         FileClose(src);

      int clr = FileOpen(m_filePath, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(clr != INVALID_HANDLE)
         FileClose(clr);
   }

public:
   static void LogInfo(const string scope, const string detail)
   {
      WriteLine("INFO", scope, detail);
   }

   static void LogDecision(const string scope, const string action, const string reason)
   {
      WriteLine("DECISION", scope, "action=" + action + " reason=" + reason);
   }

   static void LogError(const string scope, const string detail)
   {
      WriteLine("ERROR", scope, detail);
   }

   static string GetFilePath()
   {
      return m_filePath;
   }
};

string TelemetryLogger::m_filePath = "ForexSlave\\logs\\telemetry.log";
int TelemetryLogger::m_writeCounter = 0;
datetime TelemetryLogger::m_lastFlush = 0;
const int TelemetryLogger::FLUSH_INTERVAL_SECONDS = 60;

#endif