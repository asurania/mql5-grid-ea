#pragma once

class CTradeExecutor
  {
public:
   bool OpenBuy(string pair,double lots,double sl,double tp,string comment)
     {
      Print("[TRADE] OpenBuy stub :: ", pair, " lots=", DoubleToString(lots,2), " comment=", comment);
      return false;
     }

   bool OpenSell(string pair,double lots,double sl,double tp,string comment)
     {
      Print("[TRADE] OpenSell stub :: ", pair, " lots=", DoubleToString(lots,2), " comment=", comment);
      return false;
     }
  };
