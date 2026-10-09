#ifndef __UART_RTC_H
#define __UART_RTC_H


//======================== 帧定义 ==============================
#define FRAME_HEADER1         0x52    // 帧头1
#define FRAME_HEADER2         0x54    // 帧头2
#define FRAME_HEADER3         0x43    // 帧头3

// 指令类型
#define CMD_SET_PW_TH         0x01		// 设置功率阈值
#define CMD_SET_TIME          0x02		// 仅设置时间
#define CMD_SET_DATETIME      0x03		// 设置日期+时间

// 正确帧长度
#define RTC_FRAME_LEN_PW_TH		8		// 3+1+2+2 = 8
#define RTC_FRAME_LEN_SEEP		7		// 3+1+3+2 = 9
#define RTC_FRAME_LEN_DATETIME	12		// 3+1+6+2 = 12

// CRC 校验长度（帧头+指令+数据）
#define CRC_LEN_PW_TH			6		// 3+1+2 = 6
#define CRC_LEN_SEEP			5		// 3+1+3 = 7
#define CRC_LEN_DATETIME		10		// 3+1+6 = 10

//======================== 外部函数 ============================
void UART1_ReceiveHandler(uint8_t rec_byte);
void UART1_Process_RTC_Frame(void);

//======================== 全局变量 ============================
extern volatile uint8_t  u8RTC_Frame_Buffer[RTC_FRAME_LEN_DATETIME];
extern volatile bit      fRTC_Frame_Ready;

#endif