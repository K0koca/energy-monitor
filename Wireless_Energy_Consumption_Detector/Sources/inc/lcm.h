//<<AICUBE_USER_HEADER_REMARK_BEGIN>>
////////////////////////////////////////
// 在此添加用户文件头说明信息  
// 文件名称: lcm.h
////////////////////////////////////////
//<<AICUBE_USER_HEADER_REMARK_END>>


#ifndef __LCM_H__
#define __LCM_H__


//<<AICUBE_USER_DEFINE_BEGIN>>
// 在此添加用户宏定义  
//<<AICUBE_USER_DEFINE_END>>


#define LCM_STPCYC              3		//LCM数据建立时间
#define LCM_HLDCYC              1		//LCM数据保持时间
#define LCM_DMASIZE             1024	//LCM DMA发送/接收缓冲区大小
#define LCM_DMAITV              400	//LCM DMA发送/接收字节间隔时间（系统时钟）


void 	LCM_Init(void);
void    WriteDataLCD(u8 WDLCD);
void    WriteCommandLCD(u8 WCLCD);
void    ReadStatusLCD(void);
void    LCDInit(void);
void    LCDClear(void);
void    DisplayListChar(u8 X, u8 Y, const u8 *DData);
//void    DisplayImage (u8 xdata *DData);
//void	DMA_Display(void);
void 	LCM_Config(void);
void 	DMA_Config(u8 xdata *pic);

extern bit	B_LCM_DMA_busy;	//LCM DMA忙标志， 1标志LCM-DMA忙，LCM DMA中断中清除此标志，使用LCM DMA前要确认此标志为0

extern uint8_t xdata pu8LCMDMATxBuffer[LCM_DMASIZE] __attribute__((aligned (4)));
extern u8	xdata DisTmp[1024] _at_ 0x0000;	//显示缓冲，将要显示的内容放在显存里，启动DMA即可. 由于LCM DMA有4字节对齐问题，所以这里定位对地址为4的倍数


#endif
