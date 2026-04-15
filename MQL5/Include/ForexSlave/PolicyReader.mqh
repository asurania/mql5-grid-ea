#pragma once

#include <ForexSlave/Types.mqh>

class CPolicyReader
  {
private:
   PairPolicy m_policy;
   string     m_lastError;

public:
   CPolicyReader()
     {
      Reset();
     }

   void Reset()
     {
      m_policy.pair = _Symbol;
      m_policy.action = POLICY_INVALID;
      m_policy.policyBand = "unknown";
      m_policy.maxScoreAvoidSession = 0.0;
      m_policy.triggerEventId = "";
      m_policy.triggerEventName = "";
      m_policy.triggerEventTime = 0;
      m_policy.generatedAt = 0;
      m_policy.status = POLICY_STATUS_MISSING;
      m_lastError = "policy not loaded";
     }

   bool Refresh()
     {
      // Stub implementation for v1 skeleton.
      // Replace with JSON file read + parse logic in next step.
      Reset();
      m_policy.action = POLICY_ALLOW_TRADING;
      m_policy.policyBand = "stub_allow";
      m_policy.status = POLICY_STATUS_FRESH;
      m_lastError = "";
      return true;
     }

   PairPolicy GetPolicy(string pair)
     {
      PairPolicy out = m_policy;
      out.pair = pair;
      return out;
     }

   string GetLastError()
     {
      return m_lastError;
     }
  };
