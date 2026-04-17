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

   datetime GetNyCloseTimeUTC()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      // NY close = InpNyCloseHourUTC:InpNyCloseMinuteUTC on the current day
      datetime closeTime = StringToTime(IntegerToString(dt.year) + "." +
                                        IntegerToString(dt.mon, 2) + "." +
                                        IntegerToString(dt.day, 2) + " " +
                                        IntegerToString(InpNyCloseHourUTC) + ":" +
                                        IntegerToString(InpNyCloseMinuteUTC) + ":00");
      return closeTime;
     }

public:
   CSessionManager() : m_logger(NULL), m_lastState(SESSION_ACTIVE), m_liquidatedThisSession(false), m_lastLogTime(0)
     {
     }

   void Configure(CTelemetryLogger &logger)
     {
      m_logger = &logger;
     }

   SessionState EvaluateSessionState()
     {
      if(!InpSessionManagedClose)
         return SESSION_ACTIVE;

      datetime nowUTC = TimeCurrent();
      datetime nyCloseUTC = GetNyCloseTimeUTC();

      // If we're past NY close, session is closed
      if(nowUTC >= nyCloseUTC)
        {
         // Reset liquidation flag for next day at midnight-ish
         MqlDateTime dt;
         TimeToStruct(nowUTC, dt);
         // After 23:00 UTC, allow reset for next day
         if(dt.hour >= 23)
            m_liquidatedThisSession = false;
         return SESSION_CLOSED;
        }

      int secondsUntilClose = (int)(nyCloseUTC - nowUTC);
      int managedCloseSeconds = InpManagedCloseMinutesBeforeEnd * 60;
      int liquidateSeconds = InpLiquidateMinutesBeforeEnd * 60;

      // Within liquidation window: force close everything
      if(secondsUntilClose <= liquidateSeconds)
        {
         if(m_liquidatedThisSession)
            return SESSION_LIQUIDATE;  // already liquidated, stay in this state
         return SESSION_LIQUIDATE;
        }

      // Within managed close window: no new baskets, let existing manage
      if(secondsUntilClose <= managedCloseSeconds)
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

         m_logger.Info("SESSION_STATE_CHANGE: " + oldStr + " -> " + stateStr
            + " for " + pair
            + " (managed_close_min=" + IntegerToString(InpManagedCloseMinutesBeforeEnd)
            + ", liquidate_min=" + IntegerToString(InpLiquidateMinutesBeforeEnd)
            + ", ny_close_utc=" + IntegerToString(InpNyCloseHourUTC) + ":" + IntegerToString(InpNyCloseMinuteUTC, 2) + ")");

         m_lastState = newState;
         m_lastLogTime = TimeCurrent();
        }
     }

   SessionState GetLastState() const { return m_lastState; }
  };

#endif