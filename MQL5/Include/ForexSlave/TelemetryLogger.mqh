#ifndef __TELEMETRYLOGGER_MQH__
#define __TELEMETRYLOGGER_MQH__


class CTelemetryLogger
  {
public:
   void Info(string message)
     {
      Print("[INFO] ", message);
     }

   void Warn(string message)
     {
      Print("[WARN] ", message);
     }

   void Error(string message)
     {
      Print("[ERROR] ", message);
     }

   void LogPolicyState(string pair,string detail)
     {
      Print("[POLICY] ", pair, " :: ", detail);
     }

   void LogTradeDecision(string pair,string action,string reason)
     {
      Print("[DECISION] ", pair, " :: ", action, " :: ", reason);
     }
  };

#endif
