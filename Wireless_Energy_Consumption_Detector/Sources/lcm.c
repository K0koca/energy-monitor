
#include "config.h"


#define	LCM_M68_I80		1		//TFT彩屏接口数据模式选择位(bit0), 0: I8080模式，1:M6800模式
#define	LCMHOLDT		3		//TFT彩屏接口数据保持时间控制位(bit1~bit0), 0~3, 对应1~4个LCMIF时钟

/*IO定义*/
	sbit	LCD_RS	= P4^5;
	sbit	LCD_RW	= P3^6;
	sbit	LCD_E	= P3^7;
	sbit	LCD_RST	= P4^7;
	#define	LCD_Data	P2




//本地变量声明
u16	LCM_TxCnt;		//LCM DMA触发发送次数, 一次16字节, 一共64次
bit	B_LCM_DMA_busy;	//LCM DMA忙标志，使用前确认此标志为0
u16	LCM_TxAddr;		//LCM DMA要发送数据的首地址
bit	B_TxCmd;		//已发送命令标志
u8	xdata CmdTmp[2];	//命令缓冲
u8	xdata DisTmp[1024] _at_ 0x0000;	//显示缓冲，将要显示的内容放在显存里，启动DMA即可
uint8_t xdata pu8LCMDMATxBuffer[LCM_DMASIZE]; //LCM DMA发送缓冲区数组


// 描述: LCM配置函数。ST7920 @540KHz，清屏指令典型时间为1.6ms，读忙信号0us, 写入、读出数据、命令72us. 本例子DMA刷新时间84ms @24MHz.

//LCM接口配置寄存器
#define	LCMIFIE			(0<<7)	//TFT彩屏接口中断使能控制位(bit7), 1->允许中断，0->禁止
#define	LCMIFIP			(0<<4)	//TFT彩屏接口中断优先级控制位(bit5~bit4), (最低)0~3(最高).
#define	LCMIFDPS		(0<<2)	//TFT彩屏接口数据脚选择位(bit3~bit2), D18_D8=0: 0或2->8位数据在P2, D18_D8=1: 0: P2-高字节, P0低字节, 2: P2-高字节,低字节P0[7:4] P4.7 P4.6 P4.3 P4.1.
#define	LCM_D16_D8		(0<<1)	//TFT彩屏接口数据宽度控制位(bit1), 0: 8位数据，1:16位数据
#define	LCM_M68_I80		1		//TFT彩屏接口数据模式选择位(bit0), 0: I8080模式，1:M6800模式

//LCM接口配置寄存器2
#define	LCMIFCPS		(1<<5)	//TFT彩屏接口控制脚选择位(bit6~bit5), RS RD(E) WR(RW), 0->P4.5 P4.4 P4.2，1->P4.5 P3.7 P3.6, 2->P4.0 P4.4 P4.2, 3->P4.0 P3.7 P3.6
#define	LCMSETUPT		(4<<2)	//TFT彩屏接口数据建立时间控制位(bit4~bit2), 0~7, 对应1~8个LCMIF时钟, 对于6800模式就是E高电平时间, 至少20us.
#define	LCMHOLDT		3		//TFT彩屏接口数据保持时间控制位(bit1~bit0), 0~3, 对应1~4个LCMIF时钟

//LCM接口控制寄存器
#define	ENLCMIF			(1<<7)	//TFT彩屏接口使能控制位(bit7), 1->允许TFT彩屏接口功能, 0->禁止
#define	LCM_WRCMD		4		//4->写命令
#define	LCM_WRDAT		5		//5->写数据
#define	LCM_RDCMD		6		//6->读命令/状态
#define	LCM_RDDAT		7		//7->读数据

void LCM_Config(void)
{
	LCMIFCFG  = LCMIFIE  | LCMIFIP   | LCMIFDPS | LCM_D16_D8 | LCM_M68_I80;
	LCMIFCFG2 = LCMIFCPS | LCMSETUPT | LCMHOLDT;	//RS:P45,E:P37,RW:P36; Setup Time,HOLD Time
	LCMIFSTA  = 0x00;	//中断请求标志，软件清0
	LCMIFPSCR = (u8)(MAIN_Fosc/250000UL-1);	//TFT彩屏接口时钟预分频
	LCMIFCR   = ENLCMIF;
}



// 描述: LCM DMA配置函数。

//LCM_DMA控制寄存器
#define		DMA_ENLCM	(1<<7)	//LCM DMA功能使能控制位
#define		LCM_TRIGWC	(1<<6)	//LCM DMA触发写命令
#define		LCM_TRIGWD	(1<<5)	//LCM DMA触发写数据
#define		LCM_TRIGRC	(1<<4)	//LCM DMA触发读命令
#define		LCM_TRIGRD	(1<<3)	//LCM DMA触发读数据
#define		LCM_CLRFIFO	0		// 清除LCM DMA接收FIFO控制位

//LCM_DMA配置寄存器
#define		DMA_LCMIE	(1<<7)	//LCM DMA中断使能控制位
#define		DMA_LCMIP	(0<<2)	//LCM DMA中断优先级控制位
#define		DMA_LCMPTY	0		//LCM DMA数据总线访问优先级控制位

//LCM_DMA状态寄存器
#define		LCM_TXOVW	(1<<1)	// LCM DMA数据覆盖标志位
#define		DMA_LCMIF	1		// LCM DMA中断请求标志位

void DMA_Config(u8 xdata *pic)
{
	WriteCommandLCD(0x36);			//选择扩充指令集, 显示图形

	LCM_TxAddr   = (u16)pic;		//要发送数据的首地址
	DMA_LCM_STA  = 0x00;
	DMA_LCM_CFG  = DMA_LCMIE | DMA_LCMIP | DMA_LCMPTY;;
	DMA_LCM_ITVH = 0;	//设置传输间隔时间(高8位)
	DMA_LCM_ITVL = 9-1;	//设置传输间隔时间(低8位)

	B_TxCmd   = 0;		//已发送命令标志
	LCM_TxCnt = 0;		//LCM DMA触发发送次数, 一次16字节, 一共64次
	B_LCM_DMA_busy = 1;	//标志LCM-DMA忙，LCM DMA中断中清除此标志，使用LCM DMA前要确认此标志为0
	DMA_LCM_STA = DMA_LCMIF;	//软件触发LCM DMA中断，启动发送
}

void LCMIF_DMA_ISR(void) interrupt DMA_LCM_VECTOR
{
	if(DMA_LCM_STA & DMA_LCMIF)
	{
		if(LCM_TxCnt >= 64)	//判断发送是否完毕
		{
			DMA_LCM_CR = 0;
			B_LCM_DMA_busy = 0;		//清除LCM-DMA忙标志
		}
		else		
		{
			if(!B_TxCmd)	//先发设置地址命令
			{
				B_TxCmd = 1;	
				if(LCM_TxCnt <32)   //上半屏
				{
					CmdTmp[0] = (u8)(0x80+LCM_TxCnt);	//列地址
					CmdTmp[1] = 0x80;					//行地址，上半屏地址0X80
				}
				else   //下半屏
				{
					CmdTmp[0] = (u8)(0x80+LCM_TxCnt-32);	//列地址
					CmdTmp[1] = 0x88;						//行地址，下半屏地址0X88
				}
				DMA_LCM_TXAH = (u8)((u16)CmdTmp >> 8);	//LCM DMA发送命令首地址
				DMA_LCM_TXAL = (u8)CmdTmp;
				DMA_LCM_AMTH = 0;				//设置传输总字节数(高8位)
				DMA_LCM_AMT  = 2-1;				//设置传输总字节数(低8位).
				DMA_LCM_CR   = DMA_ENLCM | LCM_TRIGWC;	//启动LCM DMA发送命令
			}
			else
			{
				B_TxCmd = 0;	//清除已发地址命令
				DMA_LCM_TXAH = (u8)(LCM_TxAddr >> 8);	//LCM DMA发送数据首地址
				DMA_LCM_TXAL = (u8)LCM_TxAddr;
				DMA_LCM_AMTH = 0;				//设置传输总字节数(高8位),	设置传输总字节数 = N+1
				DMA_LCM_AMT  = 16-1;			//设置传输总字节数(低8位).
				DMA_LCM_CR   = DMA_ENLCM | LCM_TRIGWD;	//启动LCM DMA发送数据
				LCM_TxAddr  += 16;	//要发送数据的首地址, 一次DMA传输16字节
				LCM_TxCnt++;		//发送次数+1
			}
		}
	}
	DMA_LCM_STA = 0;
}

//读状态
void ReadStatusLCD(void)
{
//	LCD_Data = 0xFF;
	LCMIFSTA = 0;	//清除完成标志
    do
    {
		LCMIFCR   = ENLCMIF | LCM_RDCMD;	//读状态
		while((LCMIFSTA & 1) == 0)	;	//等待读完成
		LCMIFSTA = 0;	//清除完成标志
		LCD_E = 0;
    }while(LCMIFDATL & 0x80);	
}


//写数据
void WriteDataLCD(u8 WDLCD)
{
	ReadStatusLCD(); //检测忙
	LCMIFDATL = WDLCD;
	LCMIFCR   = ENLCMIF | LCM_WRDAT;	//写数据
	while((LCMIFSTA & 1) == 0)	;	//等待写完成
	LCMIFSTA = 0;	//清除完成标志
}

//写指令
void WriteCommandLCD(u8 WCLCD)
{
	ReadStatusLCD(); //检测忙
	LCMIFDATL = WCLCD;
	LCMIFCR   = ENLCMIF | LCM_WRCMD;	//写命令
	while((LCMIFSTA & 1) == 0)	;	//等待写完成
	LCMIFSTA = 0;	//清除完成标志
}

void LCDInit(void) //LCM初始化
{
	delay_ms(10);
	LCD_RST = 0;
	delay_ms(10);
	LCD_RST = 1;
	delay_ms(100);	//至少40ms

	WriteCommandLCD(0x30);	//显示模式设置,开始要求每次检测忙信号
	WriteCommandLCD(0x01);	//显示清屏
	WriteCommandLCD(0x04);	//反白显示设置，不反白
	WriteCommandLCD(0x0C);	//不睡眠
}

void LCDClear(void) //清屏
{
	WriteCommandLCD(0x30); //选择基本指令集
	WriteCommandLCD(0x01); //显示清屏, 忙信号长达1.2ms
}


//按指定位置显示一串字符
void DisplayListChar(u8 X, u8 Y, const u8 *DData)
{
	u8 ListLength,X2;
	X2 = X;
	if(Y < 1)   Y=1;
	if(Y > 4)   Y=4;
	X &= 0x0F; //限制X不能大于16，Y在1-4之内
	WriteCommandLCD(0x30);		//选择基本指令集
	switch(Y)
	{
		case 1: X2 |= 0X80; break;  //根据行数来选择相应地址
		case 2: X2 |= 0X90; break;
		case 3: X2 |= 0X88; break;
		case 4: X2 |= 0X98; break;
	}
	WriteCommandLCD(X2); //发送地址码
	ListLength = 0;
	while (DData[ListLength] >= 0x20) //若到达字串尾则退出
	{
		if (X <= 0x0F) //X坐标应小于0xF
		{
			WriteDataLCD(DData[ListLength]); //
			ListLength++;
			X++;
		}
	}
}

