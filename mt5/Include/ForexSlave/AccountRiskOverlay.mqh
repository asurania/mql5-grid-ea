#ifndef __FOREXSLAVE_ACCOUNT_RISK_OVERLAY_MQH__
#define __FOREXSLAVE_ACCOUNT_RISK_OVERLAY_MQH__

#include <ForexSlave/CorePortfolioPolicyReader.mqh>
#include <ForexSlave/SlaveIdentity.mqh>
#include <ForexSlave/SessionClock.mqh>

class AccountRiskOverlay
{
private:
   CorePortfolioPolicyReader *m_policyReader;
   string m_lastReason;
   bool m_shouldFlatten;

public:
   AccountRiskOverlay(CorePortfolioPolicyReader &policyReader)
   {
      m_policyReader = &policyReader;
      m_lastReason = "";
      m_shouldFlatten = false;
   }

   string LastReason() { return m_lastReason; }

   bool ShouldFlatten() { return m_shouldFlatten; }

   double EstimateFloatingDrawdownCurrency()
   {
      double total = 0.0;
      int totalPos = PositionsTotal();
      for(int i = 0; i < totalPos; i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         long magic = PositionGetInteger(POSITION_MAGIC);
         string comment = PositionGetString(POSITION_COMMENT);
         if(magic != FOREXSLAVE_MAGIC)
            continue;
         if(StringFind(comment, FOREXSLAVE_COMMENT_PREFIX, 0) != 0)
            continue;
         double profit = PositionGetDouble(POSITION_PROFIT);
         if(profit < 0.0)
            total += -profit;
      }
      return total;
   }

   double EstimateDailyRealizedPnL()
   {
      datetime now = TimeCurrent();
      MqlDateTime ts;
      TimeToStruct(now, ts);
      ts.hour = 0;
      ts.min = 0;
      ts.sec = 0;
      datetime dayStart = StructToTime(ts);
      return SumOwnedClosedPnL(dayStart, now, "");
   }

   double EstimateSessionRealizedPnL(const string sessionName)
   {
      if(sessionName == "")
         return 0.0;

      datetime nowGmt = TimeGMT();
      datetime sessionStart = SessionClock::CurrentSessionStartUtc(sessionName);
      if(sessionStart <= 0 || sessionStart > nowGmt)
         return 0.0;

      return SumOwnedClosedPnL(sessionStart, nowGmt, sessionName);
   }

   bool AllowSessionEntries(const string pair)
   {
      m_shouldFlatten = false;

      if(m_policyReader == NULL)
         return false;

      CorePortfolioGuardrails g = m_policyReader.Guardrails();
      if(!g.valid)
         return false;

      string sessionName = m_policyReader.GetSessionName(pair);
      double sessionPnl = EstimateSessionRealizedPnL(sessionName);
      if(g.sessionLossCapCurrency > 0.0 && sessionPnl <= -g.sessionLossCapCurrency)
      {
         m_lastReason = "session_loss_cap_breached";
         m_shouldFlatten = false;
         return false;
      }

      m_lastReason = "allow_session_entries";
      return true;
   }

   bool AllowNewEntries()
   {
      m_shouldFlatten = false;

      if(m_policyReader == NULL)
         return false;

      CorePortfolioGuardrails g = m_policyReader.Guardrails();
      if(!g.valid)
         return false;

      double floatingDd = EstimateFloatingDrawdownCurrency();
      if(g.maxTotalDrawdownCurrency > 0.0 && floatingDd >= g.maxTotalDrawdownCurrency)
      {
         m_lastReason = "account_drawdown_cap_breached";
         m_shouldFlatten = g.flattenOnAccountBreach;
         return false;
      }

      double dailyPnl = EstimateDailyRealizedPnL();
      if(g.dailyLossCapCurrency > 0.0 && dailyPnl <= -g.dailyLossCapCurrency)
      {
         m_lastReason = "daily_loss_cap_breached";
         m_shouldFlatten = g.flattenOnAccountBreach;
         return false;
      }

      m_lastReason = "allow_new_entries";
      return true;
   }
private:
   double SumOwnedClosedPnL(const datetime fromTs, const datetime toTs, const string sessionNameFilter)
   {
      if(!HistorySelect(fromTs, toTs))
         return 0.0;

      double total = 0.0;
      int rows = m_policyReader.RowCount();
      int deals = HistoryDealsTotal();
      for(int i = 0; i < deals; i++)
      {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0)
            continue;

         string symbol = HistoryDealGetString(ticket, DEAL_SYMBOL);
         bool managedPair = false;
         string pairSessionName = "";
         for(int j = 0; j < rows; j++)
         {
            CorePortfolioPairPolicy row = m_policyReader.GetRow(j);
            if(row.valid && row.pair == symbol)
            {
               managedPair = true;
               pairSessionName = row.sessionName;
               break;
            }
         }
         if(!managedPair)
            continue;
         if(sessionNameFilter != "" && pairSessionName != sessionNameFilter)
            continue;

         long magic = HistoryDealGetInteger(ticket, DEAL_MAGIC);
         string comment = HistoryDealGetString(ticket, DEAL_COMMENT);
         if(magic != FOREXSLAVE_MAGIC)
            continue;
         if(StringFind(comment, FOREXSLAVE_COMMENT_PREFIX, 0) != 0)
            continue;

         long entryType = HistoryDealGetInteger(ticket, DEAL_ENTRY);
         if(entryType != DEAL_ENTRY_OUT && entryType != DEAL_ENTRY_OUT_BY)
            continue;

         double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
         double swap = HistoryDealGetDouble(ticket, DEAL_SWAP);
         double commission = HistoryDealGetDouble(ticket, DEAL_COMMISSION);
         total += profit + swap + commission;
      }
      return total;
   }
};

#endif