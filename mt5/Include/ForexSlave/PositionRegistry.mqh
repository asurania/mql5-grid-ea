#ifndef __FOREXSLAVE_POSITION_REGISTRY_MQH__
#define __FOREXSLAVE_POSITION_REGISTRY_MQH__

#include <ForexSlave/SlaveIdentity.mqh>

class PositionRegistry
{
public:
   static int CountOwnedPositions(const string pair)
   {
      int count = 0;
      int total = PositionsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;

         string symbol = PositionGetString(POSITION_SYMBOL);
         long magic = PositionGetInteger(POSITION_MAGIC);
         string comment = PositionGetString(POSITION_COMMENT);
         if(symbol != pair)
            continue;
         if(magic != FOREXSLAVE_MAGIC)
            continue;
         if(StringFind(comment, FOREXSLAVE_COMMENT_PREFIX, 0) != 0)
            continue;
         count++;
      }
      return count;
   }

   static int CountOwnedPositionsByType(const string pair, const long positionType)
   {
      int count = 0;
      int total = PositionsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;

         string symbol = PositionGetString(POSITION_SYMBOL);
         long magic = PositionGetInteger(POSITION_MAGIC);
         string comment = PositionGetString(POSITION_COMMENT);
         long type = PositionGetInteger(POSITION_TYPE);
         if(symbol != pair)
            continue;
         if(magic != FOREXSLAVE_MAGIC)
            continue;
         if(StringFind(comment, FOREXSLAVE_COMMENT_PREFIX, 0) != 0)
            continue;
         if(type != positionType)
            continue;
         count++;
      }
      return count;
   }

   static double AverageOwnedLotsByType(const string pair, const long positionType)
   {
      double totalLots = 0.0;
      int count = 0;
      int total = PositionsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;

         string symbol = PositionGetString(POSITION_SYMBOL);
         long magic = PositionGetInteger(POSITION_MAGIC);
         string comment = PositionGetString(POSITION_COMMENT);
         long type = PositionGetInteger(POSITION_TYPE);
         if(symbol != pair)
            continue;
         if(magic != FOREXSLAVE_MAGIC)
            continue;
         if(StringFind(comment, FOREXSLAVE_COMMENT_PREFIX, 0) != 0)
            continue;
         if(type != positionType)
            continue;
         totalLots += PositionGetDouble(POSITION_VOLUME);
         count++;
      }
      if(count <= 0)
         return 0.0;
      return totalLots / count;
   }

   static double LastOwnedOpenPriceByType(const string pair, const long positionType)
   {
      double lastPrice = 0.0;
      datetime lastTime = 0;
      int total = PositionsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;

         string symbol = PositionGetString(POSITION_SYMBOL);
         long magic = PositionGetInteger(POSITION_MAGIC);
         string comment = PositionGetString(POSITION_COMMENT);
         long type = PositionGetInteger(POSITION_TYPE);
         datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
         if(symbol != pair)
            continue;
         if(magic != FOREXSLAVE_MAGIC)
            continue;
         if(StringFind(comment, FOREXSLAVE_COMMENT_PREFIX, 0) != 0)
            continue;
         if(type != positionType)
            continue;
         if(openTime >= lastTime)
         {
            lastTime = openTime;
            lastPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         }
      }
      return lastPrice;
   }

   static int CountOwnedActiveSlots()
   {
      string seen[];
      int uniqueCount = 0;
      int total = PositionsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;

         string symbol = PositionGetString(POSITION_SYMBOL);
         long magic = PositionGetInteger(POSITION_MAGIC);
         string comment = PositionGetString(POSITION_COMMENT);
         if(magic != FOREXSLAVE_MAGIC)
            continue;
         if(StringFind(comment, FOREXSLAVE_COMMENT_PREFIX, 0) != 0)
            continue;

         bool exists = false;
         for(int j = 0; j < uniqueCount; j++)
         {
            if(seen[j] == symbol)
            {
               exists = true;
               break;
            }
         }
         if(!exists)
         {
            ArrayResize(seen, uniqueCount + 1);
            seen[uniqueCount] = symbol;
            uniqueCount++;
         }
      }
      return uniqueCount;
   }
};

#endif
