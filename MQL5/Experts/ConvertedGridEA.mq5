#property strict
#include <Trade/Trade.mqh>
#include <NewsImpactFilter.mqh>

CTrade trade_engine;

enum time_filter_action
{
   close_all_trades,
   stop_entering_new_trades,
   managed_closing_of_trades
};

enum variable_logic
{
   managed,
   immediate
};

struct time_filter
{
   string day_week_s;
   int    day_week_n;
   int    start_hour[10];
   int    start_minute[10];
   int    stop_hour[10];
   int    stop_minute[10];
};

enum dir
{
   all,
   buy,
   sell
};

enum step_type
{
   fixed,
   variable
};

input string             s1="";                       //---------------Grid Setup---------------
input double             lot_start=0.1;               //Initial Lot Size
input double             lot_max=10.0;                //Max Lot Level Size
input double             g_mult=1.5;                  //Grid Multiplier
input step_type          used_step=fixed;             //Step Type
input double             g_step_fixed=10.0;           //Step Fixed in Pips
input string             g_step_varible="6;6;6;6;7;7;7;8.5"; //Step Variable in Pips
input double             g_tp=10.0;                   //Take Profit in Pips
input double             g_sl=1000.0;                 //Stop Loss in Pips / 0 = No Stop Loss
input int                g_level_buy=10;              //Max Grid Level for Buy /0 = Unlimited
input int                g_level_sell=10;             //Max Grid Level for Short /0 = Unlimited
input int                magic_buy=1001;              //Buy Magic Number
input int                magic_sell=1002;             //Short Magic Number

input string             s12="";                      //---------------Variable EA---------------
input bool               variable_ea=true;            //Variable EA
input variable_logic     vl=managed;                  //Variable Step / Take Profit Logic
input double             v_st_1=4.0;                  //Step TF 1
input double             v_st_2=2.0;                  //Step TF 2
input double             v_st_3=0.0;                  //Step TF 3
input double             v_st_4=0.0;                  //Step TF 4
input string             v_st_tf_1="02:00-08:00";    //Step Time Filter 1
input string             v_st_tf_2="08:00-19:00";    //Step Time Filter 2
input string             v_st_tf_3="";               //Step Time Filter 3
input string             v_st_tf_4="";               //Step Time Filter 4
input double             v_tp_1=4.0;                  //Take Profit TF 1
input double             v_tp_2=3.0;                  //Take Profit TF 2
input double             v_tp_3=0.0;                  //Take Profit TF 3
input double             v_tp_4=0.0;                  //Take Profit TF 4
input string             v_tp_tf_1="02:00-08:00";    //Take Profit Time Filter 1
input string             v_tp_tf_2="08:00-19:00";    //Take Profit Time Filter 2
input string             v_tp_tf_3="";               //Take Profit Time Filter 3
input string             v_tp_tf_4="";               //Take Profit Time Filter 4

input string             s11="";                      //---------------Automated Stop Loss using Equity Drawdown limit---------------
input bool               auto_sl=true;                //Automated Stop Loss

input string             s4="";                       //---------------Drawdown / Profit Limit---------------
input double             ddov_max=300.0;              //Max Overall Drawdown in USD /0 = Unlimited
input double             ddeq_max=300.0;              //Max Equity Drawdown in USD /0 = Unlimited
input double             prof_max=300.0;              //Max Overall Profit in USD /0 = Unlimited
input bool               autotrade_off=true;          //Turn off Auto Trade
input double             stop_equity=0;               //Target Equity Balance /0 = No Target Equity Balance

input string             s_news="";                  //---------------News Impact Filter---------------
input bool               use_news_filter=true;        //Use News Impact Filter
input string             news_csv_file="event_scores.csv"; //CSV file with event scores
input double             news_score_threshold=50.0;   //Score threshold to block trading (0-100)
input int                news_pre_minutes=120;        //Minutes before event to start blocking (120 min = 2 hours)
input int                news_post_minutes=120;       //Minutes after event to stop blocking (120 min = 2 hours)

input string             s5="";                       //---------------Time Filter---------------
input string             time_d0="";                  //Sunday
input string             time_d1="00:00-05:00,08:00-12:30,14:00-15:30,16:00-18:30";
input string             time_d2="08:00-17:00";
input string             time_d3="08:00-17:00";
input string             time_d4="08:00-17:00";
input string             time_d5="08:00-17:00";
input string             time_d6="";
input time_filter_action time_action=close_all_trades;     //Action
input bool               trade_expire=true;           //Trade Expire
input string             time_expire="23:50";        //Trade Expire Time
input string             s_days_exemption="3,6,8,27";//Trade Days Exemption
input bool               automated=true;              //Fully Automation

input string             s2="";                       //---------------Moving Average---------------
input int                ma_period=21;                //Look Back Period
input ENUM_MA_METHOD     ma_type=MODE_SMA;            //Type of Moving Average
input ENUM_APPLIED_PRICE ma_price=PRICE_CLOSE;        //Price Type

input string             s3="";                       //---------------Gann Signal HILO Activator---------------
input bool               gann_use=true;               //Use GANN
input int                gann_period=21;              //Look Back Period
input ENUM_MA_METHOD     gann_ma_type=MODE_SMA;       //Type of Moving Average

input string             s6="";                       //---------------Other Settings---------------
input double             slip_pip=1.5;                //Admissible slippage in pips
input double             pip=10.0;                    //Number of points in 1 pip

time_filter day[7],var_ea_step[4],var_ea_tp[4];
int slip,b,s,lot_digits,n_dd;
double buy_price,sell_price,buy_lot,sell_lot;
bool ea_on,action_close,action_stop,action_manage,exempted;
double profit,profit_closed,profit_open,dd_max;
int hour_expire,minute_expire,days_exemption[];
double k_pip;
string s_day;
double steps[],use_step_buy,use_step_sell,use_step_last;
int step_buy_number,step_sell_number;
double use_tp_buy=g_tp,use_tp_sell=g_tp,use_tp_last=g_tp;
datetime date_start;
double ballance_start;
int day_cur;
int ma_handle=-1,gann_high_handle=-1,gann_low_handle=-1;

double nd(double v){ return NormalizeDouble(v,_Digits); }

bool CopyBufferValue(int handle,int shift,double &out)
{
   double buf[];
   if(handle==INVALID_HANDLE) return false;
   if(CopyBuffer(handle,0,shift,1,buf)!=1) return false;
   out=buf[0];
   return true;
}

double CurrentBid(){ return SymbolInfoDouble(_Symbol,SYMBOL_BID); }
double CurrentAsk(){ return SymbolInfoDouble(_Symbol,SYMBOL_ASK); }

double MAValue(int shift)
{
   double v=0.0;
   if(!CopyBufferValue(ma_handle,shift,v)) return 0.0;
   return v;
}

double GannCalc(int shift)
{
   if(shift+1>=iBars(_Symbol,PERIOD_CURRENT)) return 0.0;
   double close0=iClose(_Symbol,PERIOD_CURRENT,shift);
   double high_ma=0.0, low_ma=0.0;
   CopyBufferValue(gann_high_handle,shift+1,high_ma);
   CopyBufferValue(gann_low_handle,shift+1,low_ma);
   if(close0>high_ma) return low_ma;
   if(close0<low_ma) return high_ma;
   return low_ma;
}

string dw(int i)
{
   switch(i)
   {
      case 0: return "Sunday         ";
      case 1: return "Monday         ";
      case 2: return "Tuesday        ";
      case 3: return "Wednesday    ";
      case 4: return "Thursday       ";
      case 5: return "Friday           ";
      case 6: return "Saturday       ";
   }
   return "No day";
}

void t0(datetime &d_cur,datetime &d_0)
{
   d_cur=TimeCurrent();
   MqlDateTime tm; TimeToStruct(d_cur,tm);
   tm.hour=0; tm.min=0; tm.sec=0;
   d_0=StructToTime(tm);
}

bool calc_time_1(string s_alert,string s_time,int &hour,int &minute)
{
   string t[];
   StringSplit(s_time,StringGetCharacter(":",0),t);
   if(ArraySize(t)==2){ hour=(int)StringToInteger(t[0]); minute=(int)StringToInteger(t[1]); return true; }
   Comment(s_alert); Alert(s_alert); return false;
}

bool calc_time_2(string s_alert,string s_time,int &start_hour,int &start_minute,int &stop_hour,int &stop_minute)
{
   string t[],ts[],tf[];
   StringSplit(s_time,StringGetCharacter("-",0),t);
   if(ArraySize(t)==2)
   {
      StringSplit(t[0],StringGetCharacter(":",0),ts);
      StringSplit(t[1],StringGetCharacter(":",0),tf);
      if(ArraySize(ts)==2 && ArraySize(tf)==2)
      {
         start_hour=(int)StringToInteger(ts[0]);
         start_minute=(int)StringToInteger(ts[1]);
         stop_hour=(int)StringToInteger(tf[0]);
         stop_minute=(int)StringToInteger(tf[1]);
         return true;
      }
   }
   Comment(s_alert); Alert(s_alert); return false;
}

bool calc_steps()
{
   string t[];
   StringSplit(g_step_varible,StringGetCharacter(";",0),t);
   if(ArraySize(t)<1){ Comment("Check correct data in Step Variable"); Alert("Check correct data in Step Variable"); return false; }
   ArrayResize(steps,ArraySize(t));
   for(int i=0;i<ArraySize(t);i++) steps[i]=StringToDouble(t[i]);
   return true;
}

bool time_filter_calc()
{
   int i,j; string d[7],t[],s_alert;
   d[0]=time_d0; d[1]=time_d1; d[2]=time_d2; d[3]=time_d3; d[4]=time_d4; d[5]=time_d5; d[6]=time_d6;
   s_day="";
   for(i=0;i<=6;i++) if(d[i]!="")
   {
      s_alert="Check correct data in Time Filter - "+dw(i);
      StringSplit(d[i],StringGetCharacter(",",0),t);
      s_day+=dw(i);
      for(j=0;j<ArraySize(t);j++)
      {
         if(!calc_time_2(s_alert,t[j],day[i].start_hour[j],day[i].start_minute[j],day[i].stop_hour[j],day[i].stop_minute[j])) return false;
         s_day+=IntegerToString(day[i].start_hour[j])+":"+IntegerToString(day[i].start_minute[j])+"-"+IntegerToString(day[i].stop_hour[j])+":"+IntegerToString(day[i].stop_minute[j])+", ";
      }
      s_day+="\n";
   }
   if(trade_expire)
   {
      s_alert="Check correct data in Time Filter - Time Expire";
      if(!calc_time_1(s_alert,time_expire,hour_expire,minute_expire)) return false;
   }
   if(variable_ea)
   {
      string ds[4]={v_st_tf_1,v_st_tf_2,v_st_tf_3,v_st_tf_4};
      for(i=0;i<=3;i++) if(ds[i]!="") if(!calc_time_2("Check correct data in Time Filter - Variable EA Step "+IntegerToString(i+1),ds[i],var_ea_step[i].start_hour[0],var_ea_step[i].start_minute[0],var_ea_step[i].stop_hour[0],var_ea_step[i].stop_minute[0])) return false;
      string dt[4]={v_tp_tf_1,v_tp_tf_2,v_tp_tf_3,v_tp_tf_4};
      for(i=0;i<=3;i++) if(dt[i]!="") if(!calc_time_2("Check correct data in Time Filter - Variable EA TP "+IntegerToString(i+1),dt[i],var_ea_tp[i].start_hour[0],var_ea_tp[i].start_minute[0],var_ea_tp[i].stop_hour[0],var_ea_tp[i].stop_minute[0])) return false;
   }
   StringSplit(s_days_exemption,StringGetCharacter(",",0),t);
   ArrayResize(days_exemption,ArraySize(t));
   for(i=0;i<ArraySize(t);i++) days_exemption[i]=(int)StringToInteger(t[i]);
   return true;
}

void lot_digits_calc()
{
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   lot_digits=2;
   for(int i=0;i<100;i++) if(MathRound(step*MathPow(10,i))==step*MathPow(10,i)){ lot_digits=i; break; }
}

void reset_step()
{
   step_buy_number=0; step_sell_number=0;
   if(used_step==fixed){ use_step_buy=g_step_fixed; use_step_sell=g_step_fixed; use_step_last=g_step_fixed; }
   else if(ArraySize(steps)>0){ use_step_buy=steps[0]; use_step_sell=steps[0]; use_step_last=steps[0]; }
}

void calc_step(dir d)
{
   int i;
   if(d==buy)
   {
      if(used_step==fixed) use_step_buy=g_step_fixed;
      else { i=(int)MathMin(step_buy_number,ArraySize(steps)-1); use_step_buy=steps[i]; }
   }
   else
   {
      if(used_step==fixed) use_step_sell=g_step_fixed;
      else { i=(int)MathMin(step_sell_number,ArraySize(steps)-1); use_step_sell=steps[i]; }
   }
}

bool news_block_active=false;

void reset_ea()
{
   date_start=TimeCurrent();
   ballance_start=AccountInfoDouble(ACCOUNT_BALANCE);
   action_close=false; action_stop=false; action_manage=false;
   news_block_active=false;
   use_tp_buy=g_tp; use_tp_sell=g_tp; use_tp_last=g_tp; ea_on=true; reset_step();
}

void check_action()
{
   if(time_action==close_all_trades) action_close=true;
   if(time_action==stop_entering_new_trades) action_stop=true;
   if(time_action==managed_closing_of_trades) action_manage=true;
}

void check_time()
{
   datetime d_cur,d_0,d_start,d_stop; int d;
   action_close=false; action_stop=false; action_manage=false;
   MqlDateTime tm; TimeToStruct(TimeCurrent(),tm); d=tm.day;
   for(int i=0;i<ArraySize(days_exemption);i++) if(days_exemption[i]==d){ check_action(); exempted=true; return; }
   exempted=false;
   t0(d_cur,d_0); d=tm.day_of_week;
   for(int i=0;i<ArraySize(day[d].start_hour);i++)
   {
      d_start=d_0+day[d].start_hour[i]*3600+day[d].start_minute[i]*60;
      d_stop=d_0+day[d].stop_hour[i]*3600+day[d].stop_minute[i]*60;
      if(d_start!=d_stop)
      {
         if(d_cur<d_start || d_cur>d_stop){ check_action(); return; }
      }
      else return;
   }
}

void check_orders()
{
   b=0; s=0; buy_lot=0; sell_lot=0; buy_price=0; sell_price=0; profit=0; profit_closed=0; profit_open=0;
   datetime buy_time=0,sell_time=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      long magic=(long)PositionGetInteger(POSITION_MAGIC);
      if(magic!=magic_buy && magic!=magic_sell) continue;
      profit_open += PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
      ENUM_POSITION_TYPE type=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      datetime opentime=(datetime)PositionGetInteger(POSITION_TIME);
      if(type==POSITION_TYPE_BUY)
      {
         b++;
         if(opentime>buy_time){ buy_time=opentime; buy_lot=PositionGetDouble(POSITION_VOLUME); buy_price=PositionGetDouble(POSITION_PRICE_OPEN); }
      }
      if(type==POSITION_TYPE_SELL)
      {
         s++;
         if(opentime>sell_time){ sell_time=opentime; sell_lot=PositionGetDouble(POSITION_VOLUME); sell_price=PositionGetDouble(POSITION_PRICE_OPEN); }
      }
   }
   profit_closed=AccountInfoDouble(ACCOUNT_BALANCE)-ballance_start;
   dd_max=MathMin(dd_max,profit_open);
   profit=nd(profit_open+profit_closed);
}

bool check_orders_history()
{
   if(!HistorySelect(date_start,TimeCurrent())) return false;
   int total=(int)HistoryDealsTotal();
   for(int i=total-1;i>=0;i--)
   {
      ulong deal=HistoryDealGetTicket(i);
      if(deal==0) continue;
      if(HistoryDealGetString(deal,DEAL_SYMBOL)!=_Symbol) continue;
      long magic=(long)HistoryDealGetInteger(deal,DEAL_MAGIC);
      if(magic!=magic_buy && magic!=magic_sell) continue;
      string comment=HistoryDealGetString(deal,DEAL_COMMENT);
      if(StringFind(comment,"sl",0)>=0) return true;
   }
   return false;
}

bool close_position_ticket(ulong ticket)
{
   if(!PositionSelectByTicket(ticket)) return false;
   trade_engine.SetAsyncMode(false);
   return trade_engine.PositionClose(ticket);
}

void close(dir ot)
{
   bool changed=true;
   while(changed)
   {
      changed=false;
      for(int i=PositionsTotal()-1;i>=0;i--)
      {
         ulong ticket=PositionGetTicket(i);
         if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
         if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
         long magic=(long)PositionGetInteger(POSITION_MAGIC);
         if(magic!=magic_buy && magic!=magic_sell) continue;
         ENUM_POSITION_TYPE type=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         if((ot==all) || (ot==buy && type==POSITION_TYPE_BUY) || (ot==sell && type==POSITION_TYPE_SELL))
         {
            close_position_ticket(ticket);
            changed=true;
         }
      }
      if(changed) Sleep(100);
   }
   check_orders();
}

void tp_adjust(dir ot)
{
   double pv=0,v=0,p=0,sl=0,tp=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      long magic=(long)PositionGetInteger(POSITION_MAGIC);
      if((magic==magic_buy && ot==buy) || (magic==magic_sell && ot==sell))
      {
         double vol=PositionGetDouble(POSITION_VOLUME);
         v+=vol;
         pv+=vol*PositionGetDouble(POSITION_PRICE_OPEN);
      }
   }
   if(v<=0) return;
   p=pv/v;
   if(ot==buy)
   {
      if(auto_sl) sl=nd(p-ddeq_max/v/k_pip);
      tp=nd(p+use_tp_buy*pip*_Point);
      if(CurrentBid()>=tp || (sl>0 && CurrentBid()<=sl)){ close(ot); return; }
   }
   else
   {
      if(auto_sl) sl=nd(p+ddeq_max/v/k_pip);
      tp=nd(p-use_tp_sell*pip*_Point);
      if(CurrentAsk()<=tp || (sl>0 && CurrentAsk()>=sl)){ close(ot); return; }
   }
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      long magic=(long)PositionGetInteger(POSITION_MAGIC);
      if(!((magic==magic_buy && ot==buy) || (magic==magic_sell && ot==sell))) continue;
      trade_engine.PositionModify(ticket, sl>0?sl:PositionGetDouble(POSITION_SL), tp);
   }
}

void trade(dir ot)
{
   double sl=0,tp=0,p=0,lot=lot_start;
   if(ot==buy)
   {
      if(b>0) lot=NormalizeDouble(buy_lot*g_mult,lot_digits);
      lot=MathMax(lot,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN));
      lot=MathMin(lot,lot_max);
      lot=MathMin(lot,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX));
      p=CurrentAsk(); tp=nd(p+use_tp_buy*pip*_Point);
      if(auto_sl) sl=nd(p-ddeq_max/lot_start/k_pip); else if(nd(g_sl)>0) sl=nd(p-g_sl*pip*_Point);
      trade_engine.SetExpertMagicNumber(magic_buy);
      trade_engine.SetDeviationInPoints((int)(slip_pip*pip));
      if(trade_engine.Buy(lot,_Symbol,0.0,sl,tp,IntegerToString(magic_buy))) step_buy_number++;
   }
   if(ot==sell)
   {
      if(s>0) lot=NormalizeDouble(sell_lot*g_mult,lot_digits);
      lot=MathMax(lot,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN));
      lot=MathMin(lot,lot_max);
      lot=MathMin(lot,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX));
      p=CurrentBid(); tp=nd(p-use_tp_sell*pip*_Point);
      if(auto_sl) sl=nd(p+ddeq_max/lot_start/k_pip); else if(nd(g_sl)>0) sl=nd(p+g_sl*pip*_Point);
      trade_engine.SetExpertMagicNumber(magic_sell);
      trade_engine.SetDeviationInPoints((int)(slip_pip*pip));
      if(trade_engine.Sell(lot,_Symbol,0.0,sl,tp,IntegerToString(magic_sell))) step_sell_number++;
   }
}

void check_g()
{
   if(!variable_ea) return;
   datetime d_cur,d_0,d_start,d_stop; t0(d_cur,d_0);
   double step_calc=0,tp_calc=0;
   double ds[4]={v_st_1,v_st_2,v_st_3,v_st_4};
   for(int i=0;i<=3;i++)
   {
      d_start=d_0+var_ea_step[i].start_hour[0]*3600+var_ea_step[i].start_minute[0]*60;
      d_stop=d_0+var_ea_step[i].stop_hour[0]*3600+var_ea_step[i].stop_minute[0]*60;
      if(d_start!=d_stop && d_cur>=d_start && d_cur<d_stop){ step_calc=ds[i]; break; }
   }
   double dt[4]={v_tp_1,v_tp_2,v_tp_3,v_tp_4};
   for(int i=0;i<=3;i++)
   {
      d_start=d_0+var_ea_tp[i].start_hour[0]*3600+var_ea_tp[i].start_minute[0]*60;
      d_stop=d_0+var_ea_tp[i].stop_hour[0]*3600+var_ea_tp[i].stop_minute[0]*60;
      if(d_start!=d_stop && d_cur>=d_start && d_cur<d_stop){ tp_calc=dt[i]; break; }
   }
   if(vl==managed)
   {
      if(s==0){ use_step_sell=(step_calc>0?step_calc:use_step_last); use_tp_sell=(tp_calc>0?tp_calc:use_tp_last); }
      if(b==0){ use_step_buy=(step_calc>0?step_calc:use_step_last); use_tp_buy=(tp_calc>0?tp_calc:use_tp_last); }
   }
   else
   {
      if(step_calc>0){ use_step_sell=step_calc; use_step_buy=step_calc; }
      if(tp_calc>0)
      {
         if(nd(tp_calc-use_tp_sell)!=0){ use_tp_sell=tp_calc; tp_adjust(sell); }
         if(nd(tp_calc-use_tp_buy)!=0){ use_tp_buy=tp_calc; tp_adjust(buy); }
         use_tp_sell=tp_calc; use_tp_buy=tp_calc;
      }
   }
   if(step_calc>0) use_step_last=step_calc;
   if(tp_calc>0) use_tp_last=tp_calc;
}

void draw_buttons(){}

void comment_view()
{
   string c="\n";
   c+="The day is exempted = "+(string)exempted+"\n";
   c+="Time start = "+TimeToString(date_start)+" dd = "+IntegerToString(n_dd)+"\n";
   c+="Balance start = "+DoubleToString(ballance_start,2)+"\n\n";
   c+="Profit closed = "+DoubleToString(profit_closed,2)+"\n";
   c+="Profit open = "+DoubleToString(profit_open,2)+"\n";
   c+="Profit total = "+DoubleToString(profit,2)+"\n\n";
   c+="buy = "+IntegerToString(b)+"\n";
   c+="buy price = "+DoubleToString(buy_price,_Digits)+"\n";
   c+="buy lot = "+DoubleToString(buy_lot,lot_digits)+"\n\n";
   c+="sell = "+IntegerToString(s)+"\n";
   c+="sell price = "+DoubleToString(sell_price,_Digits)+"\n";
   c+="sell lot = "+DoubleToString(sell_lot,lot_digits)+"\n\n";
   c+="Close All Trades = "+(string)action_close+"\n";
   c+="Stop Entering New Trades = "+(string)action_stop+"\n";
   c+="Managed Closing = "+(string)action_manage+"\n\n";
   c+="Grid Step Sell = "+DoubleToString(use_step_sell,1)+"\n";
   c+="Grid Step Buy = "+DoubleToString(use_step_buy,1)+"\n";
   c+="Grid TP Sell = "+DoubleToString(use_tp_sell,1)+"\n";
   c+="Grid TP Buy = "+DoubleToString(use_tp_buy,1)+"\n";
   
   // News filter info
   if(use_news_filter)
   {
      c+="\n--- News Impact Filter ---\n";
      string active_events=GetActiveNewsEvents(_Symbol, news_score_threshold, news_pre_minutes, news_post_minutes);
      if(active_events!="")
         c+="ACTIVE EVENTS:\n"+active_events+"\n";
      else
      {
         string next_event=GetNextNewsEvent(_Symbol, news_score_threshold);
         if(next_event!="")
            c+="Next Event: "+next_event+"\n";
         else
            c+="No upcoming events\n";
      }
   }
   
   c+=s_day;
   Comment(c);
}

void calc_k_pip(){ k_pip=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE)*MathPow(10,_Digits); }

void calc()
{
   check_time();
   check_orders();
   check_g();
   comment_view();
   if(trade_expire)
   {
      datetime d_cur,d_0; t0(d_cur,d_0);
      if(d_cur>d_0+hour_expire*3600+minute_expire*60){ close(all); reset_step(); Comment("Expire Time is ON"); ea_on=false; return; }
   }
   if(action_close){ close(all); reset_step(); return; }
   if((nd(ddov_max)!=0 && profit<=-ddov_max) || (nd(prof_max)!=0 && profit>=prof_max))
   {
      close(all); reset_step();
      if(autotrade_off){ Comment("Autotrade is OFF"); ea_on=false; }
      else { date_start=TimeCurrent(); ballance_start=AccountInfoDouble(ACCOUNT_BALANCE); n_dd++; }
      return;
   }
   if(nd(ddeq_max)!=0 && profit_open<=-ddeq_max)
   {
      close(all); reset_step();
      if(autotrade_off){ Comment("Autotrade is OFF"); ea_on=false; } else n_dd++;
      return;
   }
   if(autotrade_off && (nd(ddov_max)!=0 || nd(prof_max)!=0 || nd(ddeq_max)!=0) && b+s==0 && check_orders_history())
   { Comment("Autotrade is OFF"); ea_on=false; return; }
   
   // News Impact Filter - use EA Action settings during news block
   if(use_news_filter)
   {
      bool is_blocked=false;
      if(LoadNewsImpactFile(news_csv_file))
         is_blocked=IsNewsBlockingTrade(_Symbol, news_score_threshold, news_pre_minutes, news_post_minutes);

      if(is_blocked)
      {
         news_block_active=true;
         check_action();
      }
      else if(news_block_active)
      {
         news_block_active=false;
         check_time();
      }
   }
   
   // Wait for indicators to be ready
   double ma=MAValue(0);
   if(ma==0.0) return;
   
   double bid=CurrentBid(), ask=CurrentAsk(), gann=0.0;
   if(gann_use)
   {
      gann=GannCalc(0);
      if(gann==0.0) return;
   }
   
   if(!action_stop)
   {
      if(!action_manage)
      {
         if(s==0 && bid>ma && (!gann_use || bid>gann)){ trade(sell); tp_adjust(sell); }
         if(b==0 && bid<ma && (!gann_use || bid<gann)){ trade(buy); tp_adjust(buy); }
      }
      if(b>0 && (g_level_buy==0 || b<g_level_buy))
      {
         if(!variable_ea) calc_step(buy);
         if(buy_price-ask>=use_step_buy*pip*_Point){ trade(buy); tp_adjust(buy); }
      }
      if(s>0 && (g_level_sell==0 || s<g_level_sell))
      {
         if(!variable_ea) calc_step(sell);
         if(bid-sell_price>=use_step_sell*pip*_Point){ trade(sell); tp_adjust(sell); }
      }
   }
}

int OnInit()
{
   date_start=TimeCurrent();
   ballance_start=AccountInfoDouble(ACCOUNT_BALANCE);
   MqlDateTime tm; TimeToStruct(TimeCurrent(),tm); day_cur=tm.day;
   n_dd=0; ea_on=true; dd_max=0; slip=(int)(slip_pip*pip);
   ma_handle=iMA(_Symbol,PERIOD_CURRENT,ma_period,0,ma_type,ma_price);
   gann_high_handle=iMA(_Symbol,PERIOD_CURRENT,gann_period,0,gann_ma_type,PRICE_HIGH);
   gann_low_handle=iMA(_Symbol,PERIOD_CURRENT,gann_period,0,gann_ma_type,PRICE_LOW);
   if(!time_filter_calc()) ea_on=false;
   if(used_step==variable) if(!calc_steps()) ea_on=false;
   reset_step(); lot_digits_calc(); calc_k_pip(); tp_adjust(sell); tp_adjust(buy);
   
   // Initialize news impact filter
   if(use_news_filter)
   {
      if(!LoadNewsImpactFile(news_csv_file))
      {
         Print("Warning: News impact filter enabled but file not found: ", news_csv_file);
         Print("Trading will continue without news filtering until file is available.");
      }
   }
   
   return INIT_SUCCEEDED;
}

void OnTick()
{
   if(nd(stop_equity)>0 && AccountInfoDouble(ACCOUNT_EQUITY)>stop_equity)
   {
      close(all); Comment("Stop Equity is reached = "+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2)); ea_on=false; return;
   }
   MqlDateTime tm; TimeToStruct(TimeCurrent(),tm);
   if(day_cur!=tm.day){ if(automated) reset_ea(); day_cur=tm.day; }
   if(ea_on) calc();
}

void OnDeinit(const int reason)
{
   if(ma_handle!=INVALID_HANDLE) IndicatorRelease(ma_handle);
   if(gann_high_handle!=INVALID_HANDLE) IndicatorRelease(gann_high_handle);
   if(gann_low_handle!=INVALID_HANDLE) IndicatorRelease(gann_low_handle);
   CleanupNewsFilter();  // Clean up news filter resources
   if(reason==1 || reason==2) ObjectsDeleteAll(0,"ea_");
}

void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam)
{
   if(id==CHARTEVENT_OBJECT_CLICK)
   {
      if(sparam=="ea_short") close(sell);
      if(sparam=="ea_long") close(buy);
      if(sparam=="ea_all") close(all);
      if(sparam=="ea_reset") reset_ea();
   }
}
