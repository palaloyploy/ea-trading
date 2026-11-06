//+------------------------------------------------------------------+
//|                                        WickFill_H1Pair_EA.mq5    |
//|  เทคนิค "แท่งคู่" + Wick-Fill (E-Book โค้ชน้ำ เทรดท่าเดียว)        |
//|  1) ตีโซนแท่งคู่ (แดง-เขียว = แนวรับ / เขียว-แดง = แนวต้าน) บน H1   |
//|  2) ย่อลง M15 รอราคากลับมาแตะโซน -> เข้าออเดอร์                    |
//|  3) ใช้โซนเดิมได้ไม่เกิน 2 ครั้ง                                    |
//|  หน่วยระยะทั้งหมดเป็น "จุด" แบบที่คนไทยใช้กับทอง: 1 จุด = 0.01$      |
//+------------------------------------------------------------------+
#property copyright "Custom"
#property version   "2.40"
#property description "H1 pair-candle zone + Wick-Fill, M15 entry (XAUUSD)"

#include <Trade\Trade.mqh>

#define PREFIX "WF_"

enum ENUM_ENTRY_MODE
  {
   ENTRY_TOUCH       = 0, // แตะโซนแล้วเข้าทันที (Limit ที่ขอบโซน)
   ENTRY_M15_CONFIRM = 1, // แตะโซน + แท่ง M15 ปิดกลับออกนอกโซน
   ENTRY_ENGULF      = 2  // แตะโซน + แท่ง M15 กลืนไส้แท่งก่อนหน้า -> Limit ที่ปลายไส้แท่งก่อนหน้า
  };

enum ENUM_SL_MODE
  {
   SL_FIXED = 0, // SL คงที่ (จุด) จากจุดเข้า
   SL_ZONE  = 1, // SL หลังโซน + บัฟเฟอร์
   SL_WICK  = 2, // SL ใต้/เหนือไส้ที่ลงมาแตะโซน + บัฟเฟอร์
   SL_CANDLE = 3 // SL ใต้ Low / เหนือ High ของแท่งสัญญาณ + บัฟเฟอร์
  };

enum ENUM_LOT_MODE
  {
   LOT_FIXED = 0, // Lot คงที่
   LOT_RISK  = 1  // คิดตาม % ความเสี่ยง
  };

input group "=== โซนแท่งคู่ (H1) ==="
input ENUM_TIMEFRAMES InpZoneTF               = PERIOD_H1;
input bool            InpRequireOppositeColor = true;   // แดง→เขียว = แนวรับ(Buy), เขียว→แดง = แนวต้าน(Sell)
input int             InpSwingLookback        = 10;     // ไส้ต้องต่ำ/สูงสุดในกี่แท่งก่อนหน้า (0 = ไม่กรอง)
input int             InpMinZonePts           = 100;    // ความสูงโซนขั้นต่ำ (จุด)
input int             InpMaxZonePts           = 1200;   // ความสูงโซนสูงสุด (จุด)
input int             InpMinAwayPts           = 500;    // ราคาต้องวิ่งออกจากโซนก่อนกลับมาแตะ (จุด)
input int             InpZoneMaxAgeBars       = 48;     // อายุโซน (จำนวนแท่ง H1)
input int             InpMaxTradesPerZone     = 1;      // ใช้โซนเดิมได้กี่ครั้ง (E-Book: ไม่เกิน 2)
input bool            InpDrawZones            = true;   // วาดโซนบนกราฟ
input bool            InpAvoidOppositeZone    = true;   // ระวังโซนฝั่งตรงข้าม (แนวต้านเหนือ Buy / แนวรับใต้ Sell)
input int             InpMinRoomPts           = 500;    // ห่างโซนตรงข้ามน้อยกว่านี้ (จุด) -> ไม่เข้า
input int             InpTPBeforeZonePts      = 50;     // TP ชนโซนตรงข้าม -> เลื่อน TP มาไว้ก่อนถึงโซนกี่จุด
input int             InpLevelMaxAgeBars      = 120;    // จำโซนตรงข้ามย้อนหลังกี่แท่ง H1

input group "=== เล่นต่อข้างบน/ข้างล่าง หลังโซน H1 โดนทะลุ ==="
input bool            InpUseMainSetup         = true;   // ระบบหลัก: แท่งคู่ H1 + กลืนไส้ M15 (ปิดเพื่อทดสอบทริค M1 อย่างเดียว)
input bool            InpUseBreakoutLTF       = false;   // หลังโซน H1 โดนปิดทะลุ -> รอเล่นกลับที่ยอด/ก้นบน M15
input int             InpBreakWatchBars       = 6;      // เฝ้าหาสัญญาณได้กี่แท่ง H1 หลังทะลุ
input int             InpLtfSLBufferPts       = 100;    // SL เหนือยอด / ใต้ก้น (จุด)

input group "=== ทริค M1: ถึงโซนใหญ่ RSI แตะ Oversold + M1 ถอดไส้ (โค้ช 6 พ.ย. 69) ==="
input bool            InpUseM1Trick           = false;  // เปิดใช้ทริค M1 (MT5 real tick 2026: PF 0.98 DD 51% -> ปิดไว้)
input int             InpTrickRSIPeriod       = 14;
input double          InpTrickRSILevel        = 20.0;   // Buy เมื่อ RSI M1 <= ค่านี้ / Sell เมื่อ >= 100-ค่านี้
input int             InpTrickRSIBars         = 3;      // RSI แตะระดับภายในกี่แท่ง M1 ล่าสุด
input double          InpTrickWickRatio       = 0.3;    // ไส้ต้องยาวอย่างน้อยกี่ส่วนของแท่ง (ถอดไส้)
input int             InpTrickMinRangePts     = 80;     // แท่ง M1 ต้องยาวอย่างน้อยกี่จุด
input int             InpTrickSLBufPts        = 150;    // SL ใต้ไส้ต่ำสุด / เหนือไส้สูงสุด กี่จุด
input int             InpTrickMaxSLPts        = 1500;   // SL ไกลกว่านี้ ไม่เข้า
input int             InpTrickTPPts           = 1500;   // TP ไกล แล้วให้กฎปิด M1 ด้านล่างเป็นตัวเก็บกำไร
input bool            InpTrickM1Exit          = true;   // ปิดหมดเมื่อ M1 ปิดสวน cf หรือถอดไส้สวน (เฉพาะตอนกำไรแล้ว)
input int             InpTrickExitMinPts      = 300;    // ต้องกำไรอย่างน้อยกี่จุดก่อนใช้กฎปิด M1
input double          InpTrickExitWick        = 0.5;    // ไส้สวนยาวกี่ส่วนของแท่ง = ถอดไส้
input int             InpTrickMaxPerZone      = 2;      // ใช้ทริคกับโซนเดิมได้กี่ครั้ง
input bool            InpTrickAddOnCF         = true;   // เติมอีก 1 ไม้ตอนแท่ง M1 ยืนยัน (cf) ปิดเหนือ High/ใต้ Low แท่งถอดไส้
input int             InpTrickCFBars          = 30;     // รอ cf ได้กี่แท่ง M1
input bool            InpTrickUseTrendFilter  = false;  // ทริคนี้เทรดสวนเทรนได้ที่โซนใหญ่ (backtest: ไม่กรองดีกว่า)

input group "=== การเข้าเทรด (ย่อลง M15) ==="
input ENUM_ENTRY_MODE InpEntryMode            = ENTRY_ENGULF;
input ENUM_TIMEFRAMES InpEntryTF              = PERIOD_M15;
input int             InpMaxChasePts          = 1500;   // แท่งยืนยันต้องปิดห่างขอบโซนไม่เกินกี่จุด (กันไล่ราคา)
input int             InpLimitExpiryBars      = 4;      // Limit ที่ปลายไส้ รอได้กี่แท่ง M15 แล้วยกเลิก
input bool            InpUseContinuation      = true;   // ไล่เทรน: แท่งกลืนไส้แท่งสีเดียวกันก่อนหน้า = เข้าเพิ่ม
input int             InpMaxContEntries       = 1;      // ไล่เทรนเข้าเพิ่มได้สูงสุดกี่ไม้ต่อรอบ
input int             InpContMinBodyPts       = 300;    // แท่งไล่เทรนต้องมีเนื้อเทียนอย่างน้อยกี่จุด
input bool            InpUseFVG               = true;   // Limit ยังไม่ถูกแตะ แต่เกิด FVG 3 แท่งใกล้ราคากว่า -> ย้าย Limit ไปขอบ gap
input bool            InpUseTrendFilter       = true;   // กรองเทรนด้วย EMA บน H1 (ไม่เทรดสวนเทรน)
input int             InpTrendEMA             = 200;
input bool            InpUseD1Bias            = false;  // โค้ช "ดูแท่งเทียน Day": Buy เมื่อแท่ง D1 ล่าสุดที่ปิดแล้วเป็นแท่งเขียว / Sell เมื่อแดง
input int             InpEntryRSIOffset       = 0;      // 0=ปิด | 4 = Buy เฉพาะเมื่อ RSI14 M15 ยัง <= 46 / Sell >= 54 (เข้าก่อนราคาฟื้น)
input bool            InpUseRSIRange          = true;   // RSI Range Rule (Cardwell): Buy เมื่อ RSI H1 ไม่หลุด 40 / Sell เมื่อไม่เกิน 60 (backtest: บวกทุกปี DD เหลือ 1/3)
input int             InpRSIRangePeriod       = 9;
input double          InpRSIRangeLevel        = 40.0;   // ขาขึ้น: RSI ต่ำสุดต้อง >= ค่านี้ / ขาลง: RSI สูงสุดต้อง <= 100-ค่านี้
input int             InpRSIRangeBars         = 10;     // ดูย้อนกี่แท่ง H1    // EMA บน H1 (200 ~ เทรน H4; backtest: 100-300 ให้ผลดีกว่า 50)

input group "=== SL / TP (จุด, 1 จุด = 0.01$) ==="
input ENUM_SL_MODE    InpSLMode               = SL_FIXED;
input int             InpSLPoints             = 1000;   // SL จากจุดเข้า (โหมด SL_FIXED)
input int             InpSLBufferPts          = 50;     // บัฟเฟอร์ (โหมด SL_ZONE / SL_WICK / SL_CANDLE)
input int             InpTPPoints             = 1000;   // TP จากจุดเข้า (0 = ใช้ RR)
input double          InpRR                   = 1.5;    // ใช้เมื่อ TP = 0
input bool            InpUseRoundTP           = true;   // TP หยุดก่อนเลขกลม (backtest: ช่วยให้ผลดีขึ้น)
input double          InpRoundStepUSD         = 20.0;   // เลขกลมทุกกี่ $ (เช่น 4,260 / 4,280 / 4,300)
input double          InpRoundGapUSD          = 1.0;    // ตั้ง TP ก่อนถึงเลขกลมกี่ $
input int             InpRoundMinPts          = 300;    // ถ้าเลขกลมใกล้กว่านี้ (จุด) ข้ามไปใช้เลขกลมถัดไป
input bool            InpUseBreakeven         = false;  // เลื่อน SL บังหน้าทุน (backtest: ปิดดีกว่า)
input int             InpBE_TriggerPts        = 500;    // กำไรถึงกี่จุดแล้วเลื่อน SL
input int             InpBE_OffsetPts         = 20;     // ล็อกกำไรเหนือทุนกี่จุด

input group "=== Lot / Money Management ==="
input ENUM_LOT_MODE   InpLotMode              = LOT_FIXED;
input double          InpFixedLot             = 0.01;
input double          InpRiskPct              = 3.0;    // % ต่อไม้ (โหมด LOT_RISK)
input double          InpMaxRiskPct           = 15.0;   // ไม้ไหนเสี่ยงเกิน % นี้ของทุน ข้ามไม่เข้า

input group "=== ตัวกรอง Sideway / เวลา / ข่าว ==="
input bool            InpUseAdxFilter         = true;   // ไม่เทรดตอน Sideway (ADX บน H1 ต่ำ)
input int             InpAdxPeriod            = 14;
input double          InpAdxMin               = 20.0;
input bool            InpUseThaiSession       = false;  // เทรดเฉพาะช่วงเวลาไทย (backtest: ไม่ช่วย จึงปิดไว้)
input int             InpThaiStartHour        = 13;
input int             InpThaiEndHour          = 23;
input bool            InpServerIsNYplus7      = true;   // เวลาเซิร์ฟเวอร์ = นิวยอร์ก+7 (โบรกส่วนใหญ่) คำนวณ DST ให้อัตโนมัติ
input int             InpServerGMTOffset      = 3;      // ใช้เมื่อ InpServerIsNYplus7 = false
input bool            InpUseNewsFilter        = true;   // ไม่เปิดไม้ช่วงข่าว USD กล่องแดง (ใช้ได้ตอนรันจริง ไม่มีใน Strategy Tester)
input int             InpNewsBeforeMin        = 30;
input int             InpNewsAfterMin         = 30;

input group "=== ตัวกรอง ==="
input int             InpMaxSpreadPts         = 50;     // สเปรดสูงสุด (จุด)
input int             InpMaxOpenPositions     = 2;      // ออเดอร์เปิด+ค้างพร้อมกันสูงสุด
input int             InpMaxTradesPerDay      = 4;
input int             InpStartHour            = 0;      // ชั่วโมงเริ่มเทรด (เวลาเซิร์ฟเวอร์)
input int             InpEndHour              = 24;     // ชั่วโมงหยุดเทรด (เวลาเซิร์ฟเวอร์)
input long            InpMagic                = 20261013;

//+------------------------------------------------------------------+
struct WZone
  {
   datetime          tA;            // เวลาเปิดแท่งแรกของคู่
   datetime          formed;        // เวลาที่โซนเกิด (แท่งที่สองปิด)
   datetime          expiry;
   int               dir;           // +1 = แนวรับ (Buy), -1 = แนวต้าน (Sell)
   double            top;
   double            bottom;
   bool              movedAway;
   bool              touched;
   double            touchExtreme;  // ไส้ต่ำสุด/สูงสุดตั้งแต่แตะโซน
   int               trades;        // ใช้โซนนี้ไปแล้วกี่ครั้ง
   bool              dead;
   ulong             pendingTicket;
   bool              tkAway;        // ทริค M1: ราคาวิ่งออกจากโซนแล้ว
   double            tkExt;         // ทริค M1: ไส้ต่ำสุด/สูงสุดตั้งแต่แตะโซน
   int               tkCount;       // ทริค M1: ใช้ไปแล้วกี่ครั้ง
   datetime          pendingTime;   // เวลาที่ตั้ง Limit
   double            pendingSL;     // SL ตามโครงสร้างของ Limit นี้
   bool              pendingIsCont; // Limit นี้เป็นไม้ไล่เทรน
   bool              cont;          // อยู่ในโหมดไล่เทรน
   int               contCount;
   double            contStop;      // Low/High ของแท่งสัญญาณล่าสุด
   bool              ltf;           // กรอบแท่งคู่ M15 (เล่นต่อหลังทะลุ)
   string            obj;
  };

struct WLevel                       // โซนทั้งหมดที่เคยเกิด (ใช้เป็นแนวกั้น TP)
  {
   int               dir;
   double            top;
   double            bottom;
   datetime          formed;
   datetime          expiry;
   bool              broken;
  };

CTrade   trade;
WZone    zones[];
WLevel   levels[];
datetime lastZoneBar  = 0;
datetime lastEntryBar = 0;
int      emaHandle    = INVALID_HANDLE;
int      adxHandle    = INVALID_HANDLE;
int      rsiH1Handle  = INVALID_HANDLE;
int      rsiM15Handle = INVALID_HANDLE;
int      rsiM1Handle  = INVALID_HANDLE;
datetime lastM1Bar    = 0;
bool     cfWait       = false;   // ทริค M1: รอแท่ง cf เพื่อเติมไม้
int      cfDir        = 0;
double   cfLevel      = 0.0;     // High (Buy) / Low (Sell) ของแท่งถอดไส้
double   cfSL         = 0.0;
double   cfTP         = 0.0;
datetime cfUntil      = 0;
datetime breakUpUntil = 0;     // ทะลุแนวต้าน H1 ขึ้นไป -> เฝ้าหา Sell ที่ยอด
datetime breakDnUntil = 0;     // หลุดแนวรับ H1 ลงมา -> เฝ้าหา Buy ที่ก้น
double   breakUpLevel = 0.0;
double   breakDnLevel = 0.0;
double   upSwingHigh  = 0.0;   // ยอดสูงสุดหลังทะลุขึ้น
double   upRefLow     = 0.0;   // Low ของแท่งเขียวที่ทำยอด
bool     upDone       = true;
double   dnSwingLow   = 0.0;   // ก้นต่ำสุดหลังหลุดลง
double   dnRefHigh    = 0.0;   // High ของแท่งแดงที่ทำก้น
bool     dnDone       = true;

double Pts(double p) { return p*0.01; }   // จุด -> ราคา ($)

//+------------------------------------------------------------------+
int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(50);
   trade.SetTypeFillingBySymbol(_Symbol);

//--- เช็กว่าสัญลักษณ์นี้เปิดให้เทรดได้ไหม (บางบัญชีตั้งทองบางตัวเป็น "ปิดได้อย่างเดียว")
   long tm=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE);
   if(tm!=SYMBOL_TRADE_MODE_FULL)
     {
      string why=(tm==SYMBOL_TRADE_MODE_CLOSEONLY) ? "Close only (ปิดได้อย่างเดียว)" :
                 (tm==SYMBOL_TRADE_MODE_DISABLED) ? "Disabled (ปิดการเทรด)" :
                 (tm==SYMBOL_TRADE_MODE_LONGONLY) ? "Long only (Buy ได้อย่างเดียว)" :
                 (tm==SYMBOL_TRADE_MODE_SHORTONLY) ? "Short only (Sell ได้อย่างเดียว)" : "จำกัด";
      string msg=StringFormat("%s เทรดไม่ได้เต็มที่: %s -> ใช้สัญลักษณ์ทองตัวอื่นที่ Trade = Full access",_Symbol,why);
      Print(msg);
      if(!MQLInfoInteger(MQL_TESTER))
         Alert(msg);
      if(tm==SYMBOL_TRADE_MODE_CLOSEONLY || tm==SYMBOL_TRADE_MODE_DISABLED)
         return(INIT_FAILED);
     }

   if(InpUseTrendFilter)
     {
      emaHandle=iMA(_Symbol,InpZoneTF,InpTrendEMA,0,MODE_EMA,PRICE_CLOSE);
      if(emaHandle==INVALID_HANDLE)
         Print("สร้าง EMA ไม่สำเร็จ - จะไม่ใช้ตัวกรองเทรน");
     }

   if(InpUseAdxFilter)
     {
      adxHandle=iADX(_Symbol,InpZoneTF,InpAdxPeriod);
      if(adxHandle==INVALID_HANDLE)
         Print("สร้าง ADX ไม่สำเร็จ - จะไม่ใช้ตัวกรอง Sideway");
     }

   if(InpEntryRSIOffset>0)
      rsiM15Handle=iRSI(_Symbol,InpEntryTF,14,PRICE_CLOSE);

   if(InpUseRSIRange)
     {
      rsiH1Handle=iRSI(_Symbol,InpZoneTF,InpRSIRangePeriod,PRICE_CLOSE);
      if(rsiH1Handle==INVALID_HANDLE)
         Print("สร้าง RSI H1 ไม่สำเร็จ - ไม่ใช้ RSI Range");
     }

   if(InpUseM1Trick)
     {
      rsiM1Handle=iRSI(_Symbol,PERIOD_M1,InpTrickRSIPeriod,PRICE_CLOSE);
      if(rsiM1Handle==INVALID_HANDLE)
         Print("สร้าง RSI M1 ไม่สำเร็จ - ปิดทริค M1");
     }

   ArrayResize(zones,0);
   LoadHistoryZones();

   lastZoneBar  = iTime(_Symbol,InpZoneTF,0);
   lastEntryBar = iTime(_Symbol,InpEntryTF,0);
   PrintFormat("WickFill EA เริ่มทำงาน: พบโซนแท่งคู่ที่ยังใช้ได้ %d โซน",ArraySize(zones));
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(reason==REASON_REMOVE)   // ถอด EA ออก -> ลบ Limit ที่ค้างของ EA นี้
     {
      for(int i=OrdersTotal()-1;i>=0;i--)
        {
         ulong tk=OrderGetTicket(i);
         if(tk>0 && OrderGetString(ORDER_SYMBOL)==_Symbol && OrderGetInteger(ORDER_MAGIC)==InpMagic)
            trade.OrderDelete(tk);
        }
     }
   if(emaHandle!=INVALID_HANDLE)
      IndicatorRelease(emaHandle);
   if(adxHandle!=INVALID_HANDLE)
      IndicatorRelease(adxHandle);
   if(rsiM1Handle!=INVALID_HANDLE)
      IndicatorRelease(rsiM1Handle);
   if(rsiH1Handle!=INVALID_HANDLE)
      IndicatorRelease(rsiH1Handle);
   if(rsiM15Handle!=INVALID_HANDLE)
      IndicatorRelease(rsiM15Handle);
   ObjectsDeleteAll(0,PREFIX);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   if(IsNewBar(InpZoneTF,lastZoneBar))
      OnNewZoneBar();
   if(IsNewBar(InpEntryTF,lastEntryBar))
      OnNewEntryBar();
   if(InpUseM1Trick && rsiM1Handle!=INVALID_HANDLE && IsNewBar(PERIOD_M1,lastM1Bar))
      OnNewM1Bar();
   ManageBreakeven();
  }

//+------------------------------------------------------------------+
bool IsNewBar(ENUM_TIMEFRAMES tf,datetime &last)
  {
   datetime t=iTime(_Symbol,tf,0);
   if(t==0)
      return false;
   if(t!=last)
     {
      last=t;
      return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| แท่ง H1 ใหม่: เช็กโซนเดิมโดนปิดทะลุ/หมดอายุ แล้วหาแท่งคู่ใหม่      |
//+------------------------------------------------------------------+
void OnNewZoneBar()
  {
   double c=iClose(_Symbol,InpZoneTF,1);
   for(int i=0;i<ArraySize(zones);i++)
     {
      if(zones[i].dead)
         continue;
      bool broken=(zones[i].dir>0 && c<zones[i].bottom) ||
                  (zones[i].dir<0 && c>zones[i].top);
      if(broken || TimeCurrent()>=zones[i].expiry)
         KillZone(zones[i]);
     }
   for(int j=0;j<ArraySize(levels);j++)
     {
      if(levels[j].broken)
         continue;
      if(levels[j].dir<0 && c>levels[j].top)          // แนวต้านโดนปิดทะลุขึ้น -> รอเล่นข้างบน
        {
         levels[j].broken=true;
         breakUpUntil=TimeCurrent()+InpBreakWatchBars*PeriodSeconds(InpZoneTF);
         breakUpLevel=levels[j].top;
         upSwingHigh=0.0;
         upRefLow=0.0;
         upDone=false;
        }
      if(levels[j].dir>0 && c<levels[j].bottom)       // แนวรับโดนปิดหลุดลง -> รอเล่นข้างล่าง
        {
         levels[j].broken=true;
         breakDnUntil=TimeCurrent()+InpBreakWatchBars*PeriodSeconds(InpZoneTF);
         breakDnLevel=levels[j].bottom;
         dnSwingLow=0.0;
         dnRefHigh=0.0;
         dnDone=false;
        }
     }
   DetectAt(1);
   CompactZones();
   CompactLevels();
  }

//+------------------------------------------------------------------+
void CompactLevels()
  {
   int j=0;
   for(int i=0;i<ArraySize(levels);i++)
     {
      if(levels[i].broken || TimeCurrent()>=levels[i].expiry)
         continue;
      if(i!=j)
         levels[j]=levels[i];
      j++;
     }
   ArrayResize(levels,j);
  }

//+------------------------------------------------------------------+
//| ขอบโซนฝั่งตรงข้ามที่ใกล้ที่สุดในทิศของ TP (0 = ไม่มี)               |
//+------------------------------------------------------------------+
double NearestObstacle(int dir,double entry)
  {
   double best=0.0;
   for(int i=0;i<ArraySize(levels);i++)
     {
      if(levels[i].broken || levels[i].formed>TimeCurrent())
         continue;
      if(dir>0 && levels[i].dir<0 && levels[i].bottom>entry)        // แนวต้านเหนือ Buy
        {
         if(best==0.0 || levels[i].bottom<best)
            best=levels[i].bottom;
        }
      if(dir<0 && levels[i].dir>0 && levels[i].top<entry)           // แนวรับใต้ Sell
        {
         if(best==0.0 || levels[i].top>best)
            best=levels[i].top;
        }
      // ราคาเข้าอยู่ในโซนตรงข้ามพอดี -> ห้ามเข้า
      if(levels[i].dir==-dir && entry>=levels[i].bottom && entry<=levels[i].top)
         return entry;
     }
   return best;
  }

//+------------------------------------------------------------------+
//| หาแท่งคู่ โดย s = shift ของแท่งที่สอง (แท่งใหม่กว่า)               |
//+------------------------------------------------------------------+
int DetectAt(int s)
  {
   int added=0;
   double oA=iOpen(_Symbol,InpZoneTF,s+1),  cA=iClose(_Symbol,InpZoneTF,s+1);
   double hA=iHigh(_Symbol,InpZoneTF,s+1),  lA=iLow(_Symbol,InpZoneTF,s+1);
   double oB=iOpen(_Symbol,InpZoneTF,s),    cB=iClose(_Symbol,InpZoneTF,s);
   double hB=iHigh(_Symbol,InpZoneTF,s),    lB=iLow(_Symbol,InpZoneTF,s);
   datetime tA=iTime(_Symbol,InpZoneTF,s+1);
   datetime tB=iTime(_Symbol,InpZoneTF,s);
   if(tA==0 || tB==0)
      return 0;
   int per=PeriodSeconds(InpZoneTF);

//--- แนวรับ (Buy): แท่งแดงตามด้วยแท่งเขียว  โซน = ไส้ล่างของคู่
   bool bullPair=InpRequireOppositeColor ? (cA<oA && cB>oB) : true;
   if(bullPair)
     {
      double bottom=MathMin(lA,lB);
      double top=MathMin(MathMin(oA,cA),MathMin(oB,cB));
      double h=top-bottom;
      bool swingOK=true;
      if(InpSwingLookback>0)
        {
         int idx=iLowest(_Symbol,InpZoneTF,MODE_LOW,InpSwingLookback,s+2);
         if(idx>=0 && iLow(_Symbol,InpZoneTF,idx)<bottom)
            swingOK=false;
        }
      if(swingOK && h>=Pts(InpMinZonePts) && h<=Pts(InpMaxZonePts))
         if(AddZone(tA,tB+per,+1,top,bottom,(hB-top)>=Pts(InpMinAwayPts))>=0)
            added++;
     }

//--- แนวต้าน (Sell): แท่งเขียวตามด้วยแท่งแดง  โซน = ไส้บนของคู่
   bool bearPair=InpRequireOppositeColor ? (cA>oA && cB<oB) : true;
   if(bearPair)
     {
      double top=MathMax(hA,hB);
      double bottom=MathMax(MathMax(oA,cA),MathMax(oB,cB));
      double h=top-bottom;
      bool swingOK=true;
      if(InpSwingLookback>0)
        {
         int idx=iHighest(_Symbol,InpZoneTF,MODE_HIGH,InpSwingLookback,s+2);
         if(idx>=0 && iHigh(_Symbol,InpZoneTF,idx)>top)
            swingOK=false;
        }
      if(swingOK && h>=Pts(InpMinZonePts) && h<=Pts(InpMaxZonePts))
         if(AddZone(tA,tB+per,-1,top,bottom,(bottom-lB)>=Pts(InpMinAwayPts))>=0)
            added++;
     }
   return added;
  }

//+------------------------------------------------------------------+
int AddZone(datetime tA,datetime formed,int dir,double top,double bottom,bool away,bool ltf=false)
  {
   for(int i=0;i<ArraySize(zones);i++)
      if(zones[i].tA==tA && zones[i].dir==dir)
         return -1;

   if(!ltf)
     {
   int m=ArraySize(levels);
   ArrayResize(levels,m+1);
   levels[m].dir    = dir;
   levels[m].top    = top;
   levels[m].bottom = bottom;
   levels[m].formed = formed;
   levels[m].expiry = formed+InpLevelMaxAgeBars*PeriodSeconds(InpZoneTF);
   levels[m].broken = false;
     }

   int n=ArraySize(zones);
   ArrayResize(zones,n+1);
   zones[n].tA            = tA;
   zones[n].formed        = formed;
   zones[n].expiry        = ltf ? formed+(InpLimitExpiryBars+1)*PeriodSeconds(InpEntryTF)
                                 : formed+InpZoneMaxAgeBars*PeriodSeconds(InpZoneTF);
   zones[n].dir           = dir;
   zones[n].top           = top;
   zones[n].bottom        = bottom;
   zones[n].movedAway     = away;
   zones[n].touched       = false;
   zones[n].touchExtreme  = 0.0;
   zones[n].trades        = 0;
   zones[n].dead          = false;
   zones[n].pendingTicket = 0;
   zones[n].tkAway        = away;
   zones[n].tkExt         = 0.0;
   zones[n].tkCount       = 0;
   zones[n].pendingTime   = 0;
   zones[n].pendingSL     = 0.0;
   zones[n].pendingIsCont = false;
   zones[n].cont          = false;
   zones[n].contCount     = 0;
   zones[n].contStop      = 0.0;
   zones[n].ltf           = ltf;
   zones[n].obj           = PREFIX+(ltf ? "L" : "")+(dir>0 ? "B_" : "S_")+IntegerToString((long)tA);
   if(InpDrawZones)
      DrawZone(zones[n]);
   return n;
  }

//+------------------------------------------------------------------+
//| โหลดโซนย้อนหลังตอนเปิด EA (นับครั้งที่โซนถูกแตะไปแล้วด้วย)         |
//+------------------------------------------------------------------+
void LoadHistoryZones()
  {
   int bars=iBars(_Symbol,InpZoneTF);
   int maxS=MathMin(MathMax(InpZoneMaxAgeBars,InpLevelMaxAgeBars),bars-InpSwingLookback-3);
   for(int s=maxS;s>=1;s--)
     {
      int before=ArraySize(zones);
      DetectAt(s);
      for(int i=before;i<ArraySize(zones);i++)
         ReplayZone(zones[i],s-1);
     }
   CompactZones();
//--- แนวที่โดนแท่ง H1 ปิดทะลุไปแล้ว ไม่ถือเป็นแนวกั้น
   for(int j=0;j<ArraySize(levels);j++)
     {
      int sh=iBarShift(_Symbol,InpZoneTF,levels[j].formed);
      for(int k=sh;k>=1 && !levels[j].broken;k--)
        {
         double c=iClose(_Symbol,InpZoneTF,k);
         if((levels[j].dir>0 && c<levels[j].bottom) || (levels[j].dir<0 && c>levels[j].top))
            levels[j].broken=true;
        }
     }
   CompactLevels();
  }

//+------------------------------------------------------------------+
void ReplayZone(WZone &z,int fromShift)
  {
   for(int k=fromShift;k>=1 && !z.dead;k--)
     {
      double h=iHigh(_Symbol,InpZoneTF,k);
      double l=iLow(_Symbol,InpZoneTF,k);
      double c=iClose(_Symbol,InpZoneTF,k);
      if(z.dir>0)
        {
         if(z.movedAway && l<=z.top)
           {
            z.trades++;
            z.movedAway=false;
           }
         if(c<z.bottom)
            z.dead=true;
         else
            if(!z.movedAway && (h-z.top)>=Pts(InpMinAwayPts))
               z.movedAway=true;
        }
      else
        {
         if(z.movedAway && h>=z.bottom)
           {
            z.trades++;
            z.movedAway=false;
           }
         if(c>z.top)
            z.dead=true;
         else
            if(!z.movedAway && (z.bottom-l)>=Pts(InpMinAwayPts))
               z.movedAway=true;
        }
      if(z.trades>=InpMaxTradesPerZone)
         z.dead=true;
     }
   if(z.dead || TimeCurrent()>=z.expiry)
      KillZone(z);
  }

//+------------------------------------------------------------------+
//| แท่ง M15 ใหม่: ตรวจเงื่อนไขเข้าเทรดของแต่ละโซน                    |
//+------------------------------------------------------------------+
void OnNewEntryBar()
  {
   datetime t=iTime(_Symbol,InpEntryTF,1);
   double o=iOpen(_Symbol,InpEntryTF,1);
   double h=iHigh(_Symbol,InpEntryTF,1);
   double l=iLow(_Symbol,InpEntryTF,1);
   double c=iClose(_Symbol,InpEntryTF,1);
   double prevO=iOpen(_Symbol,InpEntryTF,2);
   double prevH=iHigh(_Symbol,InpEntryTF,2);
   double prevL=iLow(_Symbol,InpEntryTF,2);
   double prevC=iClose(_Symbol,InpEntryTF,2);
   if(t==0 || prevH==0)
      return;

   if(InpUseBreakoutLTF)
      LtfSignal(t,o,h,l,c);

   for(int i=0;i<ArraySize(zones);i++)
     {
      if(zones[i].dead)
         continue;

      //--- Limit ปลายไส้รอนานเกินไป -> ยกเลิก รอสัญญาณใหม่
      if(zones[i].pendingTicket>0 && OrderSelect(zones[i].pendingTicket) &&
         (InpEntryMode==ENTRY_ENGULF || zones[i].ltf) &&
         TimeCurrent()-zones[i].pendingTime>=InpLimitExpiryBars*PeriodSeconds(InpEntryTF))
        {
         trade.OrderDelete(zones[i].pendingTicket);
         zones[i].pendingTicket=0;
         if(!zones[i].cont)
            zones[i].touched=false;
        }

      //--- Limit ถูกแมตช์แล้ว -> ไม้แรกของโซนนับเป็น 1 ครั้ง (ไม้ไล่เทรนไม่นับ)
      if(zones[i].pendingTicket>0 && !OrderSelect(zones[i].pendingTicket))
        {
         zones[i].pendingTicket=0;
         if(!zones[i].pendingIsCont)
           {
            zones[i].trades++;
            zones[i].movedAway=false;
            zones[i].touched=false;
           }
        }
      if(!zones[i].cont && zones[i].pendingTicket==0 &&
         zones[i].trades>=(zones[i].ltf ? 1 : InpMaxTradesPerZone))
        {
         KillZone(zones[i]);
         continue;
        }

      //--- ราคายังมาไม่ถึง Limit แต่เกิด FVG 3 แท่งที่ใกล้ราคากว่า -> ย้าย Limit ไปรอที่ขอบ gap
      if(InpUseFVG && (InpEntryMode==ENTRY_ENGULF || zones[i].ltf) &&
         zones[i].pendingTicket>0 && OrderSelect(zones[i].pendingTicket))
         MoveLimitToFVG(zones[i]);

      if(t<zones[i].formed)
         continue;
      //--- กรอบ M15: แท่ง M15 ปิดทะลุกรอบ = จบ
      if(zones[i].ltf && ((zones[i].dir<0 && c>zones[i].top) || (zones[i].dir>0 && c<zones[i].bottom)))
        {
         KillZone(zones[i]);
         continue;
        }
      if(TimeCurrent()>=zones[i].expiry)
        {
         KillZone(zones[i]);
         continue;
        }
      if(InpUseMainSetup || zones[i].ltf)
         ProcessZone(zones[i],o,h,l,c,prevO,prevH,prevL,prevC);
     }
  }

//+------------------------------------------------------------------+
void ProcessZone(WZone &z,double o,double h,double l,double c,
                 double prevO,double prevH,double prevL,double prevC)
  {
   bool isBuy=(z.dir>0);
   double edge=isBuy ? z.top : z.bottom;   // ขอบโซนที่ราคาจะมาแตะก่อน

//--- สัญญาณหลังทะลุ: ตั้ง Limit ไปแล้วตอนเกิดสัญญาณ ใช้ครั้งเดียว
   if(z.ltf)
     {
      if(z.pendingTicket==0)
         KillZone(z);
      return;
     }

//--- 0) โหมดไล่เทรน (หลังเข้าไม้แรกแล้ว)
   if(z.cont)
     {
      // โครงสร้างเสีย: ปิดหลุด Low (Buy) / ทะลุ High (Sell) ของแท่งสัญญาณล่าสุด -> หยุดไล่
      if(isBuy ? (c<z.contStop) : (c>z.contStop))
        {
         z.cont=false;
         z.touched=false;
         return;
        }
      bool prevSame=isBuy ? (prevC>prevO) : (prevC<prevO);      // แท่งก่อนหน้าสีเดียวกัน
      bool sig=isBuy ? (c>o && c>prevH) : (c<o && c<prevL);      // แท่งนี้ปิดกลืนไส้แท่งก่อนหน้า
      bool big=(MathAbs(c-o)>=Pts(InpContMinBodyPts));           // ต้องเป็นแท่งตัวใหญ่จริง
      if(prevSame && sig && big && z.contCount<InpMaxContEntries)
        {
         double sl=isBuy ? l-Pts(InpSLBufferPts) : h+Pts(InpSLBufferPts);   // SL ใต้/เหนือแท่งปัจจุบัน
         if(PlaceEngulfOrder(z,isBuy ? prevH : prevL,sl,true))
           {
            z.contCount++;
            z.contStop=isBuy ? l : h;
           }
        }
      return;
     }

//--- 1) ราคาต้องวิ่งออกไปจากโซนก่อน
   if(!z.movedAway)
     {
      double dist=isBuy ? (h-z.top) : (z.bottom-l);
      if(dist>=Pts(InpMinAwayPts))
         z.movedAway=true;
      return;
     }
   if(z.pendingTicket>0)
      return;   // มี Limit รออยู่แล้ว

   double zoneSL=isBuy ? z.bottom-Pts(InpSLBufferPts) : z.top+Pts(InpSLBufferPts);

//--- 2a) แตะแล้วเข้าทันที: ตั้ง Limit รอที่ขอบโซน
   if(InpEntryMode==ENTRY_TOUCH)
     {
      if(!CanTrade(z.dir,false))
         return;
      double price=NormalizeDouble(edge,_Digits);
      double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
      double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
      bool valid=isBuy ? (ask>price) : (bid<price);
      if(valid && PlaceOrder(z.dir,true,price,zoneSL,z))
        {
         z.pendingTime=TimeCurrent();
         z.pendingIsCont=false;
        }
      return;
     }

//--- 2b) แตะโซนก่อน แล้วรอแท่ง M15 ยืนยัน
   if(isBuy ? (l<=z.top) : (h>=z.bottom))
     {
      if(!z.touched)
         z.touchExtreme=isBuy ? l : h;
      z.touched=true;
     }
   if(!z.touched)
      return;
   z.touchExtreme=isBuy ? MathMin(z.touchExtreme,l) : MathMax(z.touchExtreme,h);

   bool confirm;
   if(InpEntryMode==ENTRY_ENGULF)
      // แท่งเขียวปิดเหนือ High แท่งก่อนหน้า (กลืนไส้) / แท่งแดงปิดใต้ Low แท่งก่อนหน้า
      confirm=isBuy ? (c>o && c>prevH) : (c<o && c<prevL);
   else
      confirm=isBuy ? (c>z.top && c>o) : (c<z.bottom && c<o);

   // ราคาวิ่งหนีโซนไปไกลแล้วโดยไม่มีสัญญาณ -> ต้องรอแตะโซนใหม่
   double chase=isBuy ? (c-z.top) : (z.bottom-c);
   if(chase>Pts(InpMaxChasePts))
     {
      z.touched=false;
      return;
     }
   if(!confirm)
      return;

//--- ตัวกรองจากการเรียนรู้: เข้าเฉพาะตอน RSI M15 ยังไม่ฟื้น (ไม้ที่ RSI ฟื้นแล้วค่อยเข้า แพ้บ่อย)
   if(InpEntryRSIOffset>0 && rsiM15Handle!=INVALID_HANDLE)
     {
      double rb[];
      if(CopyBuffer(rsiM15Handle,0,1,1,rb)==1)
        {
         if(isBuy ? (rb[0]>50.0-InpEntryRSIOffset) : (rb[0]<50.0+InpEntryRSIOffset))
            return;
        }
     }

   double sl=zoneSL;
   if(InpSLMode==SL_WICK)
      sl=isBuy ? z.touchExtreme-Pts(InpSLBufferPts) : z.touchExtreme+Pts(InpSLBufferPts);
   if(InpSLMode==SL_CANDLE)
      sl=isBuy ? l-Pts(InpSLBufferPts) : h+Pts(InpSLBufferPts);

   if(InpEntryMode==ENTRY_ENGULF)
     {
      //--- ไม้แรก: Limit ที่ปลายไส้แท่งก่อนหน้า (Buy = High แท่งแดง / Sell = Low แท่งเขียว)
      if(PlaceEngulfOrder(z,isBuy ? prevH : prevL,sl,false))
        {
         z.cont=InpUseContinuation;
         z.contCount=0;
         z.contStop=isBuy ? l : h;
        }
      return;
     }

   if(CanTrade(z.dir,true) && PlaceOrder(z.dir,false,0,sl,z))
     {
      z.trades++;
      z.touched=false;
      z.movedAway=false;
      if(z.trades>=InpMaxTradesPerZone)
         KillZone(z);
     }
  }

//+------------------------------------------------------------------+
//| หลังโซน H1 โดนทะลุ: เล่นกลับที่ยอด/ก้นบน M15                        |
//| ยอด: แท่งเขียวที่ทำยอด = แท่งอ้างอิง -> รอแท่งแดง "ปิดต่ำกว่า Low"   |
//|      ของแท่งเขียวนั้น (แดงที่ปิดไม่ผ่านยังไม่นับ รอแดงแท่งใหม่)       |
//|      -> Sell Limit ที่ Low แท่งเขียว, SL เหนือยอด                     |
//| ก้น: กลับด้านทั้งหมด                                                |
//+------------------------------------------------------------------+
void LtfSignal(datetime t,double o,double h,double l,double c)
  {
   datetime now=TimeCurrent();
   datetime formed=t+PeriodSeconds(InpEntryTF);
//--- ยอด (Sell)
   if(!upDone && now<breakUpUntil)
     {
      if(c>o && h>=upSwingHigh && h>breakUpLevel)
        {
         upSwingHigh=h;
         upRefLow=l;
        }
      else
         if(upRefLow>0)
           {
            upSwingHigh=MathMax(upSwingHigh,h);
            if(c<o && c<upRefLow)
              {
               double sl=upSwingHigh+Pts(InpLtfSLBufferPts);
               int idx=AddZone(t,formed,-1,upSwingHigh,upRefLow,true,true);
               if(idx>=0)
                  PlaceEngulfOrder(zones[idx],upRefLow,sl,true);
               upDone=true;
              }
           }
     }
//--- ก้น (Buy)
   if(!dnDone && now<breakDnUntil)
     {
      if(c<o && (dnSwingLow==0.0 || l<=dnSwingLow) && l<breakDnLevel)
        {
         dnSwingLow=l;
         dnRefHigh=h;
        }
      else
         if(dnRefHigh>0)
           {
            dnSwingLow=MathMin(dnSwingLow,l);
            if(c>o && c>dnRefHigh)
              {
               double sl=dnSwingLow-Pts(InpLtfSLBufferPts);
               int idx=AddZone(t,formed,+1,dnRefHigh,dnSwingLow,true,true);
               if(idx>=0)
                  PlaceEngulfOrder(zones[idx],dnRefHigh,sl,true);
               dnDone=true;
              }
           }
     }
  }

//+------------------------------------------------------------------+
//| ทริค M1 (โค้ช): ถึงโซน H1 ใหญ่ + RSI M1 แตะ Oversold/Overbought      |
//| + แท่ง M1 ถอดไส้ -> เข้าทันที, SL ใต้ไส้, TP 900 จุด                 |
//+------------------------------------------------------------------+
bool TrickOpen()
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong tk=PositionGetTicket(i);
      if(tk==0)
         continue;
      if(PositionGetString(POSITION_SYMBOL)==_Symbol && PositionGetInteger(POSITION_MAGIC)==InpMagic &&
         StringFind(PositionGetString(POSITION_COMMENT),"TRICK")>=0)
         return true;
     }
   return false;
  }

void OnNewM1Bar()
  {
   datetime t=iTime(_Symbol,PERIOD_M1,1);
   double o=iOpen(_Symbol,PERIOD_M1,1), h=iHigh(_Symbol,PERIOD_M1,1);
   double l=iLow(_Symbol,PERIOD_M1,1),  c=iClose(_Symbol,PERIOD_M1,1);
   if(t==0)
      return;
   double r[];
   if(CopyBuffer(rsiM1Handle,0,1,InpTrickRSIBars,r)!=InpTrickRSIBars)
      return;
   double rMin=r[ArrayMinimum(r)], rMax=r[ArrayMaximum(r)];
   double rng=h-l;

//--- กฎปิด (คุณ/โค้ช): กำไรแล้ว + M1 แท่งปิดสวน cf หรือถอดไส้สวน -> ปิดไม้ทริคทั้งหมด
   if(InpTrickM1Exit)
     {
      double ph=iHigh(_Symbol,PERIOD_M1,2), pl=iLow(_Symbol,PERIOD_M1,2);
      for(int k=PositionsTotal()-1;k>=0;k--)
        {
         ulong tk=PositionGetTicket(k);
         if(tk==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
            continue;
         if(StringFind(PositionGetString(POSITION_COMMENT),"TRICK")<0)
            continue;
         int pd=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY) ? 1 : -1;
         double op=PositionGetDouble(POSITION_PRICE_OPEN);
         if((c-op)*pd<Pts(InpTrickExitMinPts))
            continue;
         bool cfAgainst=(pd>0) ? (c<o && c<pl) : (c>o && c>ph);
         double wk=(pd>0) ? (h-MathMax(o,c)) : (MathMin(o,c)-l);
         bool wickAgainst=(rng>0 && wk>=InpTrickExitWick*rng);
         if(cfAgainst || wickAgainst)
           {
            trade.PositionClose(tk);
            PrintFormat("ปิดไม้ทริค #%I64u: M1 %s สวน",tk,cfAgainst ? "cf" : "ถอดไส้");
           }
        }
     }

//--- รอ cf: แท่ง M1 ปิดเหนือ High แท่งถอดไส้ (Buy) / ใต้ Low (Sell) -> เติม 1 ไม้ SL/TP เดิม
   if(cfWait)
     {
      bool slHit=(cfDir>0) ? (l<=cfSL) : (h>=cfSL);
      if(TimeCurrent()>cfUntil || slHit || !TrickOpen())
         cfWait=false;
      else
         if((cfDir>0) ? (c>o && c>cfLevel) : (c<o && c<cfLevel))
           {
            double entry=(cfDir>0) ? SymbolInfoDouble(_Symbol,SYMBOL_ASK) : SymbolInfoDouble(_Symbol,SYMBOL_BID);
            double lot=CalcLot(cfDir,entry,cfSL);
            if(lot>0 && (entry-cfSL)*cfDir>0 && (cfTP-entry)*cfDir>0)
              {
               string cmt=(cfDir>0) ? "PairZone TRICK CF BUY" : "PairZone TRICK CF SELL";
               bool ok=(cfDir>0) ? trade.Buy(lot,_Symbol,0,cfSL,cfTP,cmt) : trade.Sell(lot,_Symbol,0,cfSL,cfTP,cmt);
               if(ok)
                  PrintFormat("%s lot=%.2f SL=%.2f TP=%.2f",cmt,lot,cfSL,cfTP);
              }
            cfWait=false;
           }
     }

   for(int i=0;i<ArraySize(zones);i++)
     {
      if(zones[i].dead || zones[i].ltf || t<zones[i].formed)
         continue;
      bool isBuy=(zones[i].dir>0);
      //--- ต้องวิ่งออกจากโซนก่อน
      if(!zones[i].tkAway)
        {
         if((isBuy ? h-zones[i].top : zones[i].bottom-l)>=Pts(InpMinAwayPts))
            zones[i].tkAway=true;
         continue;
        }
      if(zones[i].tkCount>=InpTrickMaxPerZone)
         continue;
      //--- แตะโซน: จำไส้ต่ำสุด/สูงสุด
      if(isBuy ? (l<=zones[i].top) : (h>=zones[i].bottom))
         zones[i].tkExt=(zones[i].tkExt==0.0) ? (isBuy ? l : h)
                                               : (isBuy ? MathMin(zones[i].tkExt,l) : MathMax(zones[i].tkExt,h));
      if(zones[i].tkExt==0.0)
         continue;
      //--- RSI แตะ OVS/OVB + ถอดไส้
      bool rsiOK=isBuy ? (rMin<=InpTrickRSILevel) : (rMax>=100.0-InpTrickRSILevel);
      double wick=isBuy ? (MathMin(o,c)-l) : (h-MathMax(o,c));
      bool wickOK=(rng>=Pts(InpTrickMinRangePts) && wick>=InpTrickWickRatio*rng);
      if(!rsiOK || !wickOK || TrickOpen() || !CanTrade(zones[i].dir,true,true))
         continue;

      double entry=isBuy ? SymbolInfoDouble(_Symbol,SYMBOL_ASK) : SymbolInfoDouble(_Symbol,SYMBOL_BID);
      double sl=isBuy ? zones[i].tkExt-Pts(InpTrickSLBufPts) : zones[i].tkExt+Pts(InpTrickSLBufPts);
      double dist=(entry-sl)*zones[i].dir;
      if(dist<=0 || dist>Pts(InpTrickMaxSLPts))
         continue;
      double stopLvl=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
      if(dist<stopLvl)
         continue;
      sl=NormalizeDouble(sl,_Digits);
      double tp=NormalizeDouble(entry+zones[i].dir*Pts(InpTrickTPPts),_Digits);
      double lot=CalcLot(zones[i].dir,entry,sl);
      if(lot<=0)
         continue;
      string cmt=isBuy ? "PairZone TRICK BUY" : "PairZone TRICK SELL";
      bool ok=isBuy ? trade.Buy(lot,_Symbol,0,sl,tp,cmt) : trade.Sell(lot,_Symbol,0,sl,tp,cmt);
      if(ok && trade.ResultRetcode()==TRADE_RETCODE_DONE)
        {
         zones[i].tkCount++;
         zones[i].tkAway=false;
         zones[i].tkExt=0.0;
         if(InpTrickAddOnCF)
           {
            cfWait=true;
            cfDir=zones[i].dir;
            cfLevel=isBuy ? h : l;
            cfSL=sl;
            cfTP=tp;
            cfUntil=TimeCurrent()+InpTrickCFBars*60;
           }
         PrintFormat("%s lot=%.2f SL=%.2f TP=%.2f (RSI %.1f)",cmt,lot,sl,tp,isBuy ? rMin : rMax);
         return;
        }
     }
  }

//+------------------------------------------------------------------+
//| FVG 3 แท่ง: Buy = Low แท่ง1 > High แท่ง3 (gap ขาขึ้น)               |
//|             Sell = High แท่ง1 < Low แท่ง3 (gap ขาลง)                |
//| ถ้าขอบ gap อยู่ระหว่างราคาปัจจุบันกับ Limit เดิม -> ย้าย Limit ไปขอบ gap |
//+------------------------------------------------------------------+
void MoveLimitToFVG(WZone &z)
  {
   double cur=OrderGetDouble(ORDER_PRICE_OPEN);
   bool isBuy=(z.dir>0);
   double l1=iLow(_Symbol,InpEntryTF,1),  h1=iHigh(_Symbol,InpEntryTF,1);
   double l3=iLow(_Symbol,InpEntryTF,3),  h3=iHigh(_Symbol,InpEntryTF,3);
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   double edge=0.0;
   if(isBuy && l1>h3 && l1>cur && l1<ask)
      edge=l1;
   if(!isBuy && h1<l3 && h1<cur && h1>bid)
      edge=h1;
   if(edge<=0.0)
      return;
   datetime keepTime=z.pendingTime;
   bool keepCont=z.pendingIsCont;
   double keepSL=z.pendingSL;
   trade.OrderDelete(z.pendingTicket);
   z.pendingTicket=0;
   if(PlaceOrder(z.dir,true,NormalizeDouble(edge,_Digits),keepSL,z,keepCont))
     {
      z.pendingTime=keepTime;
      z.pendingIsCont=keepCont;
      z.pendingSL=keepSL;
      PrintFormat("ย้าย Limit ไปขอบ FVG ที่ %.2f",edge);
     }
  }

//+------------------------------------------------------------------+
bool AdxOK()
  {
   if(!InpUseAdxFilter || adxHandle==INVALID_HANDLE)
      return true;
   double b[];
   if(CopyBuffer(adxHandle,0,1,1,b)!=1)
      return true;
   return (b[0]>=InpAdxMin);
  }

//+------------------------------------------------------------------+
//| วันอาทิตย์ที่ n ของเดือน (ใช้คำนวณ DST สหรัฐ)                          |
//+------------------------------------------------------------------+
int NthSunday(int year,int month,int nth)
  {
   MqlDateTime d;
   d.year=year; d.mon=month; d.day=1; d.hour=0; d.min=0; d.sec=0;
   TimeToStruct(StructToTime(d),d);
   int first=1+(7-d.day_of_week)%7;
   return first+(nth-1)*7;
  }

int ThaiHour()
  {
   datetime now=TimeCurrent();
   MqlDateTime d;
   TimeToStruct(now,d);
   int offset;   // เวลาไทย - เวลาเซิร์ฟเวอร์
   if(InpServerIsNYplus7)
     {
      int ds=NthSunday(d.year,3,2), de=NthSunday(d.year,11,1);
      bool dst=(d.mon>3 && d.mon<11) || (d.mon==3 && d.day>=ds) || (d.mon==11 && d.day<de);
      offset=dst ? 4 : 5;
     }
   else
      offset=7-InpServerGMTOffset;
   return (d.hour+offset+24)%24;
  }

bool SessionOK()
  {
   if(!InpUseThaiSession)
      return true;
   int hh=ThaiHour();
   return (InpThaiStartHour<=InpThaiEndHour) ? (hh>=InpThaiStartHour && hh<InpThaiEndHour)
                                             : (hh>=InpThaiStartHour || hh<InpThaiEndHour);
  }

//+------------------------------------------------------------------+
//| ข่าว USD ความสำคัญสูงภายในช่วงเวลาที่กำหนด (ปฏิทินข่าวใน MT5)       |
//+------------------------------------------------------------------+
bool NewsOK()
  {
   if(!InpUseNewsFilter || MQLInfoInteger(MQL_TESTER))
      return true;
   static datetime lastCheck=0;
   static bool lastOK=true;
   datetime now=TimeTradeServer();
   if(now-lastCheck<60)
      return lastOK;
   lastCheck=now;
   MqlCalendarValue vals[];
   datetime from=now-InpNewsAfterMin*60, to=now+InpNewsBeforeMin*60;
   lastOK=true;
   if(CalendarValueHistory(vals,from,to,NULL,"USD")>0)
     {
      for(int i=0;i<ArraySize(vals);i++)
        {
         MqlCalendarEvent ev;
         if(CalendarEventById(vals[i].event_id,ev) && ev.importance==CALENDAR_IMPORTANCE_HIGH)
           {
            lastOK=false;
            break;
           }
        }
     }
   return lastOK;
  }

//+------------------------------------------------------------------+
//| ตั้ง Limit ที่ปลายไส้ (ถ้าราคาย่อถึงแล้วเข้าตลาดเลย)                |
//| isCont = ไม้ไล่เทรน -> SL ตามแท่ง ไม่นับเป็นครั้งของโซน             |
//+------------------------------------------------------------------+
bool PlaceEngulfOrder(WZone &z,double price,double sl,bool isCont)
  {
   if(z.pendingTicket>0 && OrderSelect(z.pendingTicket))
      trade.OrderDelete(z.pendingTicket);    // มีสัญญาณใหม่ -> แทน Limit เดิม
   z.pendingTicket=0;
   if(!CanTrade(z.dir,true))
      return false;

   bool isBuy=(z.dir>0);
   price=NormalizeDouble(price,_Digits);
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   bool limitOK=isBuy ? (ask>price) : (bid<price);
   if(limitOK)
     {
      if(!PlaceOrder(z.dir,true,price,sl,z,isCont))
         return false;
      z.pendingTime=TimeCurrent();
      z.pendingIsCont=isCont;
      z.pendingSL=sl;
      return true;
     }
   if(!PlaceOrder(z.dir,false,0,sl,z,isCont))
      return false;
   if(!isCont)
     {
      z.trades++;
      z.movedAway=false;
      z.touched=false;
     }
   return true;
  }

//+------------------------------------------------------------------+
bool PlaceOrder(int dir,bool isLimit,double price,double structSL,WZone &z,bool forceStructSL=false)
  {
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   double entry=isLimit ? price : (dir>0 ? ask : bid);

   double sl;
   if(InpSLMode==SL_FIXED && !forceStructSL)
      sl=(dir>0) ? entry-Pts(InpSLPoints) : entry+Pts(InpSLPoints);
   else
      sl=structSL;
   sl=NormalizeDouble(sl,_Digits);

   double risk=MathAbs(entry-sl);
   if(risk<=0)
      return false;
   double stopLvl=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
   if(risk<stopLvl)
     {
      Print("ข้ามไม้: SL ใกล้เกิน Stop Level ของโบรก");
      return false;
     }

   double tpDist=(InpTPPoints>0) ? Pts(InpTPPoints) : InpRR*risk;
   double tp=NormalizeDouble(dir>0 ? entry+tpDist : entry-tpDist,_Digits);

//--- เลขกลม: ราคาทองมักหยุดก่อนถึงเลข $20 ประมาณ $1 -> วาง TP ก่อนถึง
   if(InpUseRoundTP && InpRoundStepUSD>0)
     {
      double st=InpRoundStepUSD;
      double lvl=(dir>0) ? (MathFloor(entry/st)+1)*st : (MathCeil(entry/st)-1)*st;
      if((lvl-entry)*dir<Pts(InpRoundMinPts))
         lvl+=dir*st;
      double cap=lvl-dir*InpRoundGapUSD;
      if((cap-tp)*dir<0)
         tp=NormalizeDouble(cap,_Digits);
     }

//--- ระวังโซนฝั่งตรงข้าม (กรอบแนวต้าน/แนวรับที่ TP ต้องวิ่งผ่าน)
   if(InpAvoidOppositeZone)
     {
      double obs=NearestObstacle(dir,entry);
      if(obs>0)
        {
         double room=(dir>0) ? obs-entry : entry-obs;
         if(room<Pts(InpMinRoomPts))
           {
            PrintFormat("ข้ามไม้: ใกล้โซนตรงข้ามเกินไป (%.0f จุด)",room/0.01);
            return false;
           }
         double capTP=(dir>0) ? obs-Pts(InpTPBeforeZonePts) : obs+Pts(InpTPBeforeZonePts);
         if((dir>0 && capTP<tp) || (dir<0 && capTP>tp))
            tp=NormalizeDouble(capTP,_Digits);
        }
     }

   double lot=CalcLot(dir,entry,sl);
   if(lot<=0)
      return false;

   string cmt=(dir>0 ? "PairZone BUY" : "PairZone SELL");
   if(forceStructSL)
      cmt=cmt+" ADD";
   bool ok;
   if(isLimit)
      ok=(dir>0) ? trade.BuyLimit(lot,entry,_Symbol,sl,tp,ORDER_TIME_GTC,0,cmt)
                 : trade.SellLimit(lot,entry,_Symbol,sl,tp,ORDER_TIME_GTC,0,cmt);
   else
      ok=(dir>0) ? trade.Buy(lot,_Symbol,0,sl,tp,cmt)
                 : trade.Sell(lot,_Symbol,0,sl,tp,cmt);

   uint rc=trade.ResultRetcode();
   if(!ok || (rc!=TRADE_RETCODE_DONE && rc!=TRADE_RETCODE_PLACED))
     {
      PrintFormat("เปิดออเดอร์ไม่สำเร็จ: %u %s",rc,trade.ResultRetcodeDescription());
      return false;
     }
   if(isLimit)
      z.pendingTicket=trade.ResultOrder();
   PrintFormat("%s%s lot=%.2f entry=%.2f SL=%.2f TP=%.2f",
               cmt,(isLimit ? " LIMIT" : ""),lot,entry,sl,tp);
   return true;
  }

//+------------------------------------------------------------------+
double CalcLot(int dir,double entry,double sl)
  {
   double bal=AccountInfoDouble(ACCOUNT_BALANCE);
   ENUM_ORDER_TYPE ot=(dir>0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double lossPerLot=0.0;
   if(!OrderCalcProfit(ot,_Symbol,1.0,entry,sl,lossPerLot))
      lossPerLot=0.0;
   lossPerLot=MathAbs(lossPerLot);

   double lot=InpFixedLot;
   if(InpLotMode==LOT_RISK && lossPerLot>0 && bal>0)
      lot=bal*InpRiskPct/100.0/lossPerLot;
   lot=NormalizeLot(lot);

   if(lossPerLot>0 && bal>0)
     {
      double riskPct=lossPerLot*lot/bal*100.0;
      if(riskPct>InpMaxRiskPct)
        {
         PrintFormat("ข้ามไม้: ความเสี่ยง %.1f%% ของทุน เกินที่ตั้งไว้ %.1f%%",riskPct,InpMaxRiskPct);
         return 0.0;
        }
     }
   return lot;
  }

//+------------------------------------------------------------------+
double NormalizeLot(double lot)
  {
   double minL=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double maxL=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(step<=0)
      step=0.01;
   lot=MathFloor(lot/step+1e-9)*step;
   if(lot<minL)
      lot=minL;
   if(lot>maxL)
      lot=maxL;
   int d=(int)MathMax(0,MathCeil(-MathLog10(step)));
   return NormalizeDouble(lot,d);
  }

//+------------------------------------------------------------------+
bool RSIRangeOK(int dir)
  {
   if(!InpUseRSIRange || rsiH1Handle==INVALID_HANDLE)
      return true;
   double b[];
   if(CopyBuffer(rsiH1Handle,0,1,InpRSIRangeBars,b)!=InpRSIRangeBars)
      return true;
   if(dir>0)
      return (b[ArrayMinimum(b)]>=InpRSIRangeLevel);
   return (b[ArrayMaximum(b)]<=100.0-InpRSIRangeLevel);
  }

bool D1BiasOK(int dir)
  {
   if(!InpUseD1Bias)
      return true;
   double o=iOpen(_Symbol,PERIOD_D1,1), c=iClose(_Symbol,PERIOD_D1,1);
   if(o==0 || c==0)
      return true;
   return (dir>0) ? (c>o) : (c<o);
  }

bool TrendOK(int dir)
  {
   if(!D1BiasOK(dir))
      return false;
   if(!RSIRangeOK(dir))
      return false;
   if(!InpUseTrendFilter || emaHandle==INVALID_HANDLE)
      return true;
   double b[];
   if(CopyBuffer(emaHandle,0,1,1,b)!=1)
      return true;
   double c=iClose(_Symbol,InpZoneTF,1);
   return (dir>0) ? (c>b[0]) : (c<b[0]);
  }

//+------------------------------------------------------------------+
bool CanTrade(int dir,bool checkSpread,bool isTrick=false)
  {
   if(checkSpread)
     {
      double spr=SymbolInfoDouble(_Symbol,SYMBOL_ASK)-SymbolInfoDouble(_Symbol,SYMBOL_BID);
      if(spr>Pts(InpMaxSpreadPts))
         return false;
     }
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(),dt);
   bool inHours=(InpStartHour<=InpEndHour)
                ? (dt.hour>=InpStartHour && dt.hour<InpEndHour)
                : (dt.hour>=InpStartHour || dt.hour<InpEndHour);
   if(!inHours)
      return false;
   if(!isTrick || InpTrickUseTrendFilter)
     {
      if(!TrendOK(dir) || !AdxOK())
         return false;
     }
   if(!SessionOK() || !NewsOK())
      return false;
   if(CountOpen()>=InpMaxOpenPositions)
      return false;
   if(TradesToday()>=InpMaxTradesPerDay)
      return false;
   return true;
  }

//+------------------------------------------------------------------+
int CountOpen()
  {
   int n=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong tk=PositionGetTicket(i);
      if(tk==0)
         continue;
      if(PositionGetString(POSITION_SYMBOL)==_Symbol && PositionGetInteger(POSITION_MAGIC)==InpMagic)
         n++;
     }
   for(int i=OrdersTotal()-1;i>=0;i--)
     {
      ulong tk=OrderGetTicket(i);
      if(tk==0)
         continue;
      if(OrderGetString(ORDER_SYMBOL)==_Symbol && OrderGetInteger(ORDER_MAGIC)==InpMagic)
         n++;
     }
   return n;
  }

//+------------------------------------------------------------------+
int TradesToday()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(),dt);
   dt.hour=0;
   dt.min=0;
   dt.sec=0;
   datetime start=StructToTime(dt);
   if(!HistorySelect(start,TimeCurrent()+60))
      return 0;
   int n=0;
   for(int i=HistoryDealsTotal()-1;i>=0;i--)
     {
      ulong tk=HistoryDealGetTicket(i);
      if(tk==0)
         continue;
      if(HistoryDealGetString(tk,DEAL_SYMBOL)!=_Symbol)
         continue;
      if(HistoryDealGetInteger(tk,DEAL_MAGIC)!=InpMagic)
         continue;
      if(HistoryDealGetInteger(tk,DEAL_ENTRY)==DEAL_ENTRY_IN)
         n++;
     }
   return n;
  }

//+------------------------------------------------------------------+
//| เลื่อน SL บังหน้าทุนเมื่อกำไรถึงระยะที่ตั้ง                         |
//+------------------------------------------------------------------+
void ManageBreakeven()
  {
   if(!InpUseBreakeven)
      return;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong tk=PositionGetTicket(i);
      if(tk==0)
         continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      double open=PositionGetDouble(POSITION_PRICE_OPEN);
      double sl=PositionGetDouble(POSITION_SL);
      double tp=PositionGetDouble(POSITION_TP);
      if(sl<=0)
         continue;
      if(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY)
        {
         if(sl>=open)
            continue;   // บังหน้าทุนแล้ว
         double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
         if(bid-open>=Pts(InpBE_TriggerPts))
            trade.PositionModify(tk,NormalizeDouble(open+Pts(InpBE_OffsetPts),_Digits),tp);
        }
      else
        {
         if(sl<=open)
            continue;
         double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
         if(open-ask>=Pts(InpBE_TriggerPts))
            trade.PositionModify(tk,NormalizeDouble(open-Pts(InpBE_OffsetPts),_Digits),tp);
        }
     }
  }

//+------------------------------------------------------------------+
void KillZone(WZone &z)
  {
   z.dead=true;
   if(z.pendingTicket>0 && OrderSelect(z.pendingTicket))
      trade.OrderDelete(z.pendingTicket);   // Limit ยังไม่ถูกแมตช์ -> ลบทิ้ง
   if(InpDrawZones && ObjectFind(0,z.obj)>=0)
     {
      ObjectSetInteger(0,z.obj,OBJPROP_TIME,1,(long)TimeCurrent());
      ObjectSetInteger(0,z.obj,OBJPROP_COLOR,clrSilver);
     }
  }

//+------------------------------------------------------------------+
void DrawZone(const WZone &z)
  {
   if(ObjectFind(0,z.obj)<0)
      ObjectCreate(0,z.obj,OBJ_RECTANGLE,0,z.tA,z.top,z.expiry,z.bottom);
   color col=z.dead ? clrSilver : (z.ltf ? clrKhaki : (z.dir>0 ? clrMediumSeaGreen : clrIndianRed));
   ObjectSetInteger(0,z.obj,OBJPROP_COLOR,col);
   ObjectSetInteger(0,z.obj,OBJPROP_FILL,true);
   ObjectSetInteger(0,z.obj,OBJPROP_BACK,true);
   ObjectSetInteger(0,z.obj,OBJPROP_SELECTABLE,false);
  }

//+------------------------------------------------------------------+
void CompactZones()
  {
   int j=0;
   for(int i=0;i<ArraySize(zones);i++)
     {
      if(zones[i].dead)
         continue;
      if(i!=j)
         zones[j]=zones[i];
      j++;
     }
   ArrayResize(zones,j);
  }
//+------------------------------------------------------------------+
