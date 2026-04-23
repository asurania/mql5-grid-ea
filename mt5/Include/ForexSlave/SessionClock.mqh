#ifndef __FOREXSLAVE_SESSION_CLOCK_MQH__
#define __FOREXSLAVE_SESSION_CLOCK_MQH__

struct SessionWindow
{
   int startMinutes;
   int endMinutes;
   bool valid;
};

class SessionClock
{
public:
   static int MinutesToSessionClose(const string sessionName)
   {
      SessionWindow w = ResolveSessionWindow(sessionName);
      if(!w.valid)
         return 24 * 60;

      int calgaryMinutes = CalgaryMinutesNow();
      return MinutesUntilBoundary(calgaryMinutes, w.endMinutes);
   }

   static datetime CurrentSessionStartUtc(const string sessionName)
   {
      SessionWindow w = ResolveSessionWindow(sessionName);
      if(!w.valid)
         return 0;

      datetime nowGmt = TimeGMT();
      datetime calgary = nowGmt + CalgaryUtcOffsetSeconds(nowGmt);
      MqlDateTime tm;
      TimeToStruct(calgary, tm);
      int nowMinutes = tm.hour * 60 + tm.min;

      bool open = false;
      if(w.startMinutes <= w.endMinutes)
         open = (nowMinutes >= w.startMinutes && nowMinutes < w.endMinutes);
      else
         open = (nowMinutes >= w.startMinutes || nowMinutes < w.endMinutes);

      if(!open)
         return 0;

      int startDayShift = 0;
      if(w.startMinutes > w.endMinutes && nowMinutes < w.endMinutes)
         startDayShift = -1;

      MqlDateTime startTm = tm;
      startTm.hour = w.startMinutes / 60;
      startTm.min = w.startMinutes % 60;
      startTm.sec = 0;
      datetime calgaryStart = StructToTime(startTm) + startDayShift * 86400;
      return calgaryStart - CalgaryUtcOffsetSeconds(nowGmt);
   }

   static bool IsSessionOpen(const string sessionName)
   {
      SessionWindow w = ResolveSessionWindow(sessionName);
      if(!w.valid)
         return false;

      int calgaryMinutes = CalgaryMinutesNow();
      if(w.startMinutes <= w.endMinutes)
         return (calgaryMinutes >= w.startMinutes && calgaryMinutes < w.endMinutes);
      return (calgaryMinutes >= w.startMinutes || calgaryMinutes < w.endMinutes);
   }

private:
   static int CalgaryMinutesNow()
   {
      datetime nowGmt = TimeGMT();
      datetime calgary = nowGmt + CalgaryUtcOffsetSeconds(nowGmt);
      MqlDateTime tm;
      TimeToStruct(calgary, tm);
      return tm.hour * 60 + tm.min;
   }

   static int MinutesUntilBoundary(const int nowMinutes, const int boundaryMinutes)
   {
      int delta = boundaryMinutes - nowMinutes;
      if(delta < 0)
         delta += 24 * 60;
      return delta;
   }

   static SessionWindow ResolveSessionWindow(const string sessionName)
   {
      SessionWindow w;
      w.startMinutes = 0;
      w.endMinutes = 0;
      w.valid = false;

      string s = sessionName;
      StringToLower(s);

      if(s == "asia")
      {
         w.startMinutes = 16 * 60;
         w.endMinutes = 21 * 60;
         w.valid = true;
      }
      else if(s == "london")
      {
         w.startMinutes = 21 * 60;
         w.endMinutes = 4 * 60;
         w.valid = true;
      }
      else if(s == "new_york" || s == "newyork")
      {
         w.startMinutes = 4 * 60;
         w.endMinutes = 12 * 60;
         w.valid = true;
      }

      return w;
   }

   static int CalgaryUtcOffsetSeconds(const datetime gmt)
   {
      MqlDateTime tm;
      TimeToStruct(gmt, tm);
      int year = tm.year;

      datetime dstStartUtc = NthWeekdayOfMonthUtc(year, 3, 0, 2, 9);
      datetime dstEndUtc = NthWeekdayOfMonthUtc(year, 11, 0, 1, 8);

      if(gmt >= dstStartUtc && gmt < dstEndUtc)
         return -6 * 3600;
      return -7 * 3600;
   }

   static datetime NthWeekdayOfMonthUtc(const int year, const int month, const int weekday, const int nth, const int hourUtc)
   {
      MqlDateTime first;
      first.year = year;
      first.mon = month;
      first.day = 1;
      first.hour = 0;
      first.min = 0;
      first.sec = 0;
      datetime firstTs = StructToTime(first);
      MqlDateTime firstTm;
      TimeToStruct(firstTs, firstTm);
      int firstWeekday = firstTm.day_of_week;
      int offsetDays = weekday - firstWeekday;
      if(offsetDays < 0)
         offsetDays += 7;
      int day = 1 + offsetDays + (nth - 1) * 7;

      MqlDateTime out;
      out.year = year;
      out.mon = month;
      out.day = day;
      out.hour = hourUtc;
      out.min = 0;
      out.sec = 0;
      return StructToTime(out);
   }
};

#endif
