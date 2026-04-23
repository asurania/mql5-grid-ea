#ifndef __SESSIONMANAGER_MQH__
#define __SESSIONMANAGER_MQH__


#include <ForexSlave/Types.mqh>
#include <ForexSlave/TelemetryLogger.mqh>

class CSessionManager
  {
private:
   CTelemetryLogger *m_logger;
   SessionState      m_lastState;
   bool              m_liquidatedToday;
   datetime          m_lastLogTime;
   datetime          m_managedCloseTimeUTC;    // from Python grid policy
   datetime          m_sessionCloseTimeUTC;    // from Python grid policy
   datetime          m_dailyLiquidateTimeUTC;  // Daily forced liquidation (1:50 PM Calgary)
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

   datetime GetEffectiveSessionCloseTime()
     {
      if(m_usePythonTimings && m_sessionCloseTimeUTC > 0)
         return m_sessionCloseTimeUTC;
      // Fallback: compute from config
      return GetNyCloseTimeUTC();
     }

   datetime GetEffectiveDailyLiquidateTime()
     {
      if(m_usePythonTimings && m_dailyLiquidateTimeUTC > 0)
         return m_dailyLiquidateTimeUTC;
      // Fallback: 10 min before NY close
      datetime nyClose = GetNyCloseTimeUTC();
      return nyClose - InpLiquidateMinutesBeforeEnd * 60;
     }

public:
   CSessionManager() : m_logger(NULL), m_lastState(SESSION_ACTIVE), m_liquidatedToday(false), m_lastLogTime(0),
                       m_managedCloseTimeUTC(0), m_sessionCloseTimeUTC(0), m_dailyLiquidateTimeUTC(0), m_usePythonTimings(false)
     {
     }

   void Configure(CTelemetryLogger &logger)
     {
      m_logger = &logger;
     }

   // Called when grid policy is refreshed with Python-provided session timings
   void UpdatePythonTimings(datetime managedCloseUTC, datetime sessionCloseUTC, datetime dailyLiquidateUTC)
     {
      m_managedCloseTimeUTC = managedCloseUTC;
      m_sessionCloseTimeUTC = sessionCloseUTC;
      m_dailyLiquidateTimeUTC = dailyLiquidateUTC;
      m_usePythonTimings = (managedCloseUTC > 0 && sessionCloseUTC > 0 && dailyLiquidateUTC > 0);
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
      // Reset daily liquidation flag for new day
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      if(dt.hour >= 21 || dt.hour < 3)  // after 9 PM UTC or before 3 AM UTC = new day reset
         m_liquidatedToday = false;
     }

   SessionState EvaluateSessionState()
     {
      if(!InpSessionManagedClose)
         return SESSION_ACTIVE;

      datetime nowUTC = TimeCurrent();
      datetime dailyLiquidateUTC = GetEffectiveDailyLiquidateTime();

      // --- Daily forced liquidation: highest priority ---
      // At 1:50 PM Calgary (20:50 UTC), force close EVERYTHING
      if(nowUTC >= dailyLiquidateUTC && !m_liquidatedToday)
        {
         return SESSION_LIQUIDATE;
        }

      // After daily liquidation has happened, session is closed until next day
      if(m_liquidatedToday)
        {
         return SESSION_CLOSED;
        }

      // --- Per-session managed close: no new baskets, but let existing manage ---
      datetime managedCloseUTC = GetEffectiveManagedCloseTime();
      datetime sessionCloseUTC = GetEffectiveSessionCloseTime();

      // Past session close time (but before daily liquidation)
      if(nowUTC >= sessionCloseUTC)
        {
         // Between sessions: no new baskets but existing positions can manage to TP
         // This is NOT forced liquidation — positions stay open until daily liquidate
         return SESSION_MANAGED_CLOSE;
        }

      // Within managed close window of current session
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
      m_liquidatedToday = true;
     }

   bool IsLiquidatedToday() const { return m_liquidatedToday; }

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
            + ", daily_liquidate=" + TimeToString(GetEffectiveDailyLiquidateTime(), TIME_DATE|TIME_MINUTES)
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