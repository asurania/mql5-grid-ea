#pragma once

enum EntryDirection
  {
   ENTRY_NONE = 0,
   ENTRY_BUY = 1,
   ENTRY_SELL = 2
  };

struct EntryDecision
  {
   bool           shouldEnter;
   EntryDirection direction;
   double         lots;
   string         reason;
  };

class CEntrySignal
  {
private:
   double m_defaultLots;

public:
   CEntrySignal()
     {
      m_defaultLots = 0.01;
     }

   void Configure(double defaultLots=0.01)
     {
      m_defaultLots = defaultLots;
     }

   EntryDecision EvaluateFirstEntry(string pair)
     {
      EntryDecision out;
      out.shouldEnter = false;
      out.direction = ENTRY_NONE;
      out.lots = m_defaultLots;
      out.reason = "first-entry signal not implemented yet";
      return out;
     }
  };
