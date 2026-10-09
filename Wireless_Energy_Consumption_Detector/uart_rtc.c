////////////////////////////////////////
// 文件名称: uart_rtc.c
// 文件描述: 
// 文件版本: V1.0
// 修改记录:
//   1. (2026-05-01) 创建文件
//使用说明
//发送 “功率阈值” 帧：	0x52 0x54 0x43 0x01 低位 高位 CRC_L CRC_H（总 8 字节）；
//发送 “休眠” 帧：		0x52 0x54 0x43 0x02 0x00 CRC_L CRC_H（总 7 字节）；
//发送 “唤醒” 帧：		0x52 0x54 0x43 0x02 0xAA CRC_L CRC_H（总 7 字节）；
//发送 “日期 + 时间” 帧：	0x52 0x54 0x43 0x03 年 月 日 时 分 秒 CRC_L CRC_H（总 12 字节）；
//CRC 计算范围：帧头 (3) + 指令 (1) + 数据段（日期 / 时间 / 日期时间），采用 Modbus CRC16 算法；
//CRC 字节顺序：低字节在前，高字节在后（与原代码保持一致）。
////////////////////////////////////////



#include "config.h"


// 全局变量
volatile uint8_t  u8RTC_Frame_Buffer[RTC_FRAME_LEN_DATETIME]; // 按最大帧长度定义
volatile bit      fRTC_Frame_Ready = 0;

// UART接收状态机
typedef enum {
    UART_SEARCH_HEADER1,
    UART_SEARCH_HEADER2,
    UART_SEARCH_HEADER3,
    UART_RECEIVE_CMD,       // 接收指令类型
    UART_RECEIVE_DATA,      // 接收数据段
    UART_RECEIVE_CRC        // 接收CRC（可选优化，此处合并到DATA）
} UART_StateTypeDef;

static UART_StateTypeDef UART_State = UART_SEARCH_HEADER1;
static uint8_t u8DataIndex = 0;
static uint8_t u8CurrentFrameLen = 0; // 当前帧的总长度（根据指令类型动态调整）

/*/=========================================================================
// 内部函数：RTC 更新日期
//=========================================================================
static void RTC_UpdateDate(uint8_t year, uint8_t month, uint8_t day)
{
    RTC_Stop();
    RTC_SetYear(year);
    RTC_SetMonth(month);
    RTC_SetDay(day);
    RTC_Run();
    RTC_SyncInitial();
    while (RTC_IsSyncing());
}
//=========================================================================
// 内部函数：RTC 更新时间
//=========================================================================
static void RTC_UpdateTime(uint8_t hour, uint8_t min, uint8_t sec)
{
    RTC_Stop();
    RTC_SetHour(hour);
    RTC_SetMinute(min);
    RTC_SetSecond(sec);
    RTC_SetSSecond(0);
    RTC_Run();
    RTC_SyncInitial();
    while (RTC_IsSyncing());
}
*/


//=========================================================================
// 内部函数：RTC 更新日期+时间
//=========================================================================
static void RTC_UpdateDateTime(uint8_t year, uint8_t month, uint8_t day, uint8_t hour, uint8_t min, uint8_t sec)
{
    RTC_Stop();
    RTC_SetYear(year);
    RTC_SetMonth(month);
    RTC_SetDay(day);
    RTC_SetHour(hour);
    RTC_SetMinute(min);
    RTC_SetSecond(sec);
    RTC_SetSSecond(0);
    RTC_Run();
    RTC_SyncInitial();
    while (RTC_IsSyncing());
}

//=========================================================================
// 中断接收状态机
//=========================================================================
void UART1_ReceiveHandler(uint8_t rec_byte)
{
    switch (UART_State) {
        case UART_SEARCH_HEADER1:
            if (rec_byte == FRAME_HEADER1) {
                u8RTC_Frame_Buffer[0] = rec_byte;
                UART_State = UART_SEARCH_HEADER2;
            }
            break;
        case UART_SEARCH_HEADER2:
            if (rec_byte == FRAME_HEADER2) {
                u8RTC_Frame_Buffer[1] = rec_byte;
                UART_State = UART_SEARCH_HEADER3;
            } else {
                UART_State = UART_SEARCH_HEADER1; // 帧头错误，重置
            }
            break;
        case UART_SEARCH_HEADER3:
            if (rec_byte == FRAME_HEADER3) {
                u8RTC_Frame_Buffer[2] = rec_byte;
                UART_State = UART_RECEIVE_CMD; // 接收指令类型
            } else {
                UART_State = UART_SEARCH_HEADER1; // 帧头错误，重置
            }
            break;
        case UART_RECEIVE_CMD:
            // 保存指令类型，并确定当前帧总长度
            u8RTC_Frame_Buffer[3] = rec_byte;
            switch (rec_byte) {
                case CMD_SET_PW_TH:
                    u8CurrentFrameLen = RTC_FRAME_LEN_PW_TH;
                    break;
                case CMD_SET_TIME:
                    u8CurrentFrameLen = RTC_FRAME_LEN_SEEP;
                    break;
                case CMD_SET_DATETIME:
                    u8CurrentFrameLen = RTC_FRAME_LEN_DATETIME;
                    break;
                default:
                    UART_State = UART_SEARCH_HEADER1; // 指令无效，重置
                    return;
            }
            u8DataIndex = 4; // 数据段起始索引（第4字节）
            UART_State = UART_RECEIVE_DATA;
            break;
        case UART_RECEIVE_DATA:
            u8RTC_Frame_Buffer[u8DataIndex++] = rec_byte;
            // 接收完所有字节（数据段+CRC）
            if (u8DataIndex >= u8CurrentFrameLen) {
                fRTC_Frame_Ready = 1; // 帧接收完成
                UART_State = UART_SEARCH_HEADER1; // 重置状态机
            }
            break;
        default:
            UART_State = UART_SEARCH_HEADER1; // 异常状态，重置
            break;
    }
}

//=========================================================================
// 主循环解析帧
//=========================================================================
void UART1_Process_RTC_Frame(void)
{
    uint16_t crc_calc, crc_recv;
    uint8_t cmd_type;
    // 日期字段
    uint8_t year, month, day;
    // 时间字段
    uint8_t hour, min, sec;
	
	uint8_t crc_check_len;

    if (!fRTC_Frame_Ready) return; // 无有效帧，直接返回
    fRTC_Frame_Ready = 0;          // 标记帧开始处理

    // 1. 获取指令类型
    cmd_type = u8RTC_Frame_Buffer[3];

    // 2. 计算CRC校验（帧头3 + 指令1 + 数据段 = 校验长度）
    crc_check_len = 0;
    switch (cmd_type) {
        case CMD_SET_PW_TH:
            crc_check_len = CRC_LEN_PW_TH; // 3(头)+1(指令)+2(功率阈值)=6字节
            break;
        case CMD_SET_TIME:
            crc_check_len = CRC_LEN_SEEP; // 3(头)+1(指令)+3(时间)=5字节
            break;
        case CMD_SET_DATETIME:
            crc_check_len = CRC_LEN_DATETIME; // 3(头)+1(指令)+6(日期时间)=10字节
            break;
        default:
            return; // 无效指令，直接返回
    }

    // 提取接收到的CRC（低字节在前，高字节在后）
    crc_recv = ((uint16_t)u8RTC_Frame_Buffer[u8CurrentFrameLen-1] << 8) | 
                u8RTC_Frame_Buffer[u8CurrentFrameLen-2];
    // 计算CRC
    crc_calc = MODBUS_CRC16_Check(u8RTC_Frame_Buffer, crc_check_len);

    // 3. CRC校验通过后，处理指令
    if (crc_calc != crc_recv) {
        return; // CRC错误，丢弃帧
    }

    // 4. 按指令类型解析数据并更新RTC
    switch (cmd_type) 
	{
        case CMD_SET_PW_TH:
            // 保存功率阈值
			CanShu[0] = ((uint16_t)u8RTC_Frame_Buffer[u8CurrentFrameLen-3] << 8) | 
                u8RTC_Frame_Buffer[u8CurrentFrameLen-4];
			IAP_EraseSector(EE_ADDRESS); //擦除一个扇区
			convert16to8( CanShu, EEPROM_date, Par_Length);
			delay_ms(1);
			EEPROM_write_n(EE_ADDRESS,EEPROM_date,EEPROM_Length);
			delay_ms(4);
			EEPROM_read_n( EE_ADDRESS,EEPROM_date,EEPROM_Length);//读取设置参数
			convert8to16(EEPROM_date, CanShu, EEPROM_Length);
            break;
        case CMD_SET_TIME:
			//发送 “休眠” 帧：0x52 0x54 0x43 0x02 0x00 CRC_L CRC_H（总 7 字节）；
			//发送 “唤醒” 帧：0x52 0x54 0x43 0x02 0xAA CRC_L CRC_H（总 7 字节）；
            if( u8RTC_Frame_Buffer[4] == 0x00 )
			{
				UART2_SendString("AT+GSLP=5000\r\n");
			}
            if( u8RTC_Frame_Buffer[4] == 0xAA )
			{
				ESP01S_RST =0;
				delay_ms(100);
				ESP01S_RST =1;
			}
            break;
        case CMD_SET_DATETIME:
            // 解析日期+时间
            year  = u8RTC_Frame_Buffer[4];
            month = u8RTC_Frame_Buffer[5];
            day   = u8RTC_Frame_Buffer[6];
            hour  = u8RTC_Frame_Buffer[7];
            min   = u8RTC_Frame_Buffer[8];
            sec   = u8RTC_Frame_Buffer[9];
            // 合法性校验
            if (month >=1 && month <=12 && day >=1 && day <=31 
                && hour <=23 && min <=59 && sec <=59) {
                RTC_UpdateDateTime(year, month, day, hour, min, sec);
            }
            break;
        default:
            break;
    }
}

