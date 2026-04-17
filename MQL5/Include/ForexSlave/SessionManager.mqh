#ifndef __SESSIONMANAGER_MQH__
#define __SESSIONMANAGER_MQH__


#include <ForexSlave/Types.mqh>
#include <ForexSlave/TelemetryLogger.mqh>

class CSessionManager
  {
private:
   CTelemetryLogger *m_logger;
   SessionState      m_lastState;
   bool              m_liquidatedThisSession;
   datetime          m_lastLogTime;
   datetime          m_managedCloseTimeUTC;    // from Python grid policy
   datetime          m_liquidateTimeUTC;       // from Python grid policy
   datetime          m_sessionCloseTimeUTC;     // from Python grid policy
   bool              m_usePythonTimings;        // true if Python provided timings

   datetime GetNyCloseTimeUTC()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      datetime closeTime = StringToTime(IntegerToString(dt.year) + "." +
                                        IntegerToString(dt.mon, 2) + "." +
                                        IntegerToString(dt.day, 2) + " " +
                                        IntegerToString(InpNyCloseHourUTC) + ":" +
                                        IntegerToString(InpNyCloseMinuteUTC) + ":00");
      return closeTime;
     }

   datetime GetEffectiveManagedCloseTime()
     {
      if(m_usePythonTimings && m_managedCloseTimeUTC > 0)
         return m_managedCloseTimeUTC;
      // Fallback: compute from config
      datetime nyClose = GetNyCloseTimeUTC();
      return nyClose - InpManagedCloseMinutesBeforeEnd * 60;
     }

   datetime GetEffectiveLiquidateTime()
     {
      if(m_usePythonTimings && m_liquidateTimeUTC > 0)
         return m_liquidateTimeUTC;
      // Fallback: compute from config
      datetime nyClose = GetNyCloseTimeUTC();
      return nyClose - InpLiquidateMinutesBeforeEnd * 60;
     }

   datetime GetEffectiveSessionCloseTime()
     {
      if(m_usePythonTimings && m_sessionCloseTimeUTC > 0)
         return m_sessionCloseTimeUTC;
      // Fallback: compute from config
      return GetNyCloseTimeUTC();
     }

public:
   CSessionManager() : m_logger(NULL), m_lastState(SESSION_ACTIVE), m_liquidatedThisSession(false), m_lastLogTime(0),
                       m_managedCloseTimeUTC(0), m_liquidateTimeUTC(0), m_sessionCloseTimeUTC(0), m_usePythonTimings(false)
     {
     }

   void Configure(CTelemetryLogger &logger)
     {
      m_logger = &logger;
     }

   // Called when grid policy is refreshed with Python-provided session timings
   void UpdatePythonTimings(datetime managedCloseUTC, datetime liquidateUTC, datetime sessionCloseUTC)
     {
      m_managedCloseTimeUTC = managedCloseUTC;
      m_liquidateTimeUTC = liquidateUTC;
      m_sessionCloseTimeUTC = sessionCloseUTC;
      m_usePythonTimings = (managedCloseUTC > 0 && liquidateUTC > 0 && sessionCloseUTC > 0);
      if(m_usePythonTimings)
        {
         ResetLiquidatedIfNeeded();
        }
     }

   // Parse MT5 timestamp string "2026.04.17 20:30:00" to datetime
   datetime ParseMT5Timestamp(string ts)
     {
      return StringToTime(ts);
     }

   void ResetLiquidatedIfNeeded()
     {
      // Allow re-liquidation if we've moved to a new session
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      if(dt.hour >= 0 && dt.hour < 3)  // early UTC hours = new day reset
         m_liquidatedThisSession = false;
     }

   SessionState EvaluateSessionState()
     {
      if(!InpSessionManagedClose)
         return SESSION_ACTIVE;

      datetime nowUTC = TimeCurrent();
      datetime managedCloseUTC = GetEffectiveManagedCloseTime();
      datetime liquidateUTC = GetEffectiveLiquidateTime();
      datetime sessionCloseUTC = GetEffectiveSessionCloseTime();

      // If we're past session close, session is closed
      if(nowUTC >= sessionCloseUTC)
        {
         MqlDateTime dt;
         TimeToStruct(nowUTC, dt);
         // Reset liquidation flag for next day
         if(dt.hour >= 23 || dt.hour < 3)
            m_liquidatedThisSession = false;
         return SESSION_CLOSED;
        }

      // Within liquidation window: force close everything
      if(nowUTC >= liquidateUTC)
        {
         return SESSION_LIQUIDATE;
        }

      // Within managed close window: no new baskets, let existing manage
      if(nowUTC >= managedCloseUTC)
         return SESSION_MANAGED_CLOSE;

      // Normal trading
      return SESSION_ACTIVE;
     }

   bool ShouldAllowNewBasket(SessionState state)
     {
      return (state == SESSION_ACTIVE);
     }

   bool ShouldAllowExpansion(SessionState state)
     {
      // Managed close still allows grid expansion of existing baskets
      return (state == SESSION_ACTIVE || state == SESSION_MANAGED_CLOSE);
     }

   bool ShouldLiquidate(SessionState state)
     {
      return (state == SESSION_LIQUIDATE);
     }

   bool ShouldForceCloseAll(SessionState state)
     {
      return (state == SESSION_LIQUIDATE || state == SESSION_CLOSED);
     }

   void SetLiquidated()
     {
      m_liquidatedThisSession = true;
     }

   void LogStateChange(SessionState newState, string pair)
     {
      if(m_logger == NULL)
         return;

      if(newState != m_lastState)
        {
         string stateStr = "ACTIVE";
         if(newState == SESSION_MANAGED_CLOSE) stateStr = "MANAGED_CLOSE";
         else if(newState == SESSION_LIQUIDATE) stateStr = "LIQUIDATE";
         else if(newState == SESSION_CLOSED) stateStr = "CLOSED";

         string oldStr = "ACTIVE";
         if(m_lastState == SESSION_MANAGED_CLOSE) oldStr = "MANAGED_CLOSE";
         else if(m_lastState == SESSION_LIQUIDATE) oldStr = "LIQUIDATE";
         else if(m_lastState == SESSION_CLOSED) oldStr = "CLOSED";

         string timingSource = m_usePythonTimings ? "python" : "config";

         m_logger.Info("SESSION_STATE_CHANGE: " + oldStr + " -> " + stateStr
            + " for " + pair
            + " (source=" + timingSource
            + ", managed_close_min=" + IntegerToString(InpManagedCloseMinutesBeforeEnd)
            + ", liquidate_min=" + IntegerToString(InpLiquidateMinutesBeforeEnd)
            + ", ny_close_utc=" + IntegerToString(InpNyCloseHourUTC) + ":" + IntegerToString(InpNyCloseMinuteUTC, 2) + ")");

         m_lastState = newState;
         m_lastLogTime = TimeCurrent();
        }
     }

   SessionState GetLastState() const { return m_lastState; }
   bool UsesPythonTimings() const { return m_usePythonTimings; }
  };

#endif