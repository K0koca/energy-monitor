//<<AICUBE_USER_HEADER_REMARK_BEGIN>>
////////////////////////////////////////
// 在此添加用户文件头说明信息  
// 文件名称: uart.h
////////////////////////////////////////
//<<AICUBE_USER_HEADER_REMARK_END>>


#ifndef __UART_H__
#define __UART_H__


//<<AICUBE_USER_DEFINE_BEGIN>>
// 在此添加用户宏定义  
//<<AICUBE_USER_DEFINE_END>>


#define UART1_RXSIZE            128     //串口1接收缓冲区大小
#define UART2_RXSIZE            128     //串口2接收缓冲区大小

#define UART4_RXSIZE            128      //串口4接收缓冲区大小


void UART1_Init(void);
void UART1_SendByte(uint8_t dat);
void UART1_SendBuffer(uint8_t *dat, uint8_t size);
void UART1_SendString(char *str);
void UART2_Init(void);
void UART2_SendByte(uint8_t dat);
void UART2_SendBuffer(uint8_t *dat, uint8_t size);
void UART2_SendString(char *str);
void UART4_Init(void);
void UART4_SendByte(uint8_t dat);
void UART4_SendBuffer(uint8_t *dat, uint8_t size);
void UART4_SendString(char *str);
uint16_t MODBUS_CRC16_Check(uint8_t *dat, int size);

extern BOOL fPrintfBusy;
extern BOOL fUART1ReadyRead;
extern uint8_t u8UART1RxCount;
extern uint8_t xdata pu8UART1RxBuffer[UART1_RXSIZE];
extern BOOL fUART2SendBusy;
extern BOOL fUART2ReadyRead;
extern uint8_t u8UART2RxCount;
extern uint8_t xdata pu8UART2RxBuffer[UART2_RXSIZE];
extern BOOL fUART4SendBusy;
extern BOOL fUART4ReadyRead;
extern uint8_t u8UART4RxCount;
extern uint8_t xdata pu8UART4RxBuffer[UART4_RXSIZE];


//<<AICUBE_USER_EXTERNAL_DECLARE_BEGIN>>
// 在此添加用户外部函数和外部变量声明  
//<<AICUBE_USER_EXTERNAL_DECLARE_END>>


#endif
