#ifndef __ENTRYSIGNAL_MQH__
#define __ENTRYSIGNAL_MQH__


#include <ForexSlave/Types.mqh>

class CEntryIntentReader;

class CEntrySignal
  {
private:
   double m_defaultLots;
   CEntryIntentReader *m_reader;

public:
   CEntrySignal()
     {
      m_defaultLots = 0.01;
      m_reader = NULL;
     }

   void Configure(CEntryIntentReader &reader,double defaultLots=0.01)
     {
      m_defaultLots = defaultLots;
      m_reader = &reader;
     }

   EntryDecision EvaluateFirstEntry(string pair)
     {
      EntryDecision out;
      out.shouldEnter = false;
      out.direction = ENTRY_NONE;
      out.lots = m_defaultLots;
      out.reason = "entry intent reader not configured";

      if(m_reader == NULL)
         return out;

      out = m_reader.Evaluate(pair);
      if(out.lots <= 0.0)
         out.lots = m_defaultLots;
      return out;
     }
  };

#endif
