
#ifndef __CONFIG_H__
#define __CONFIG_H__

#define __ENCODING              "GB2312" //DO NOT DELETE or MODIFY


#define HIRC                    40000000UL		// 内部高速时钟 40MHz
#define FOSC                    40000000UL		// 系统主时钟 40MHz
#define SYSCLK                  FOSC
#define MAIN_Fosc               FOSC

#include <ai8051u.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <float.h>
#include <intrins.h>

#include "def.h"
#include "ai8051u_def.h"


#include "port.h"
#include "clock.h"
#include "wdt.h"
#include "iap.h"
#include "timer.h"
#include "uart.h"
#include "i2c.h"
#include "rtc.h"
#include "lcm.h"

void SYS_Init(void);
void delay_us(uint16_t us);
void delay_ms(uint16_t ms);



//<<AICUBE_USER_EXTERNAL_DECLARE_BEGIN>>
#include "dht11.h"
#include "ina219.h"
#include "esp8266.h"
#include "uart_rtc.h"
#include "Soft_Convert.h"
//<<AICUBE_USER_EXTERNAL_DECLARE_END>>


//========================I/O口输入输出=============================
#define	AVA_LM		P00			//声光报警
#define	RUN			P01			//正常运行指示
#define DHT11_DATA	P10			// DATA引脚
#define	WIFI_POWER	P11			//无线供电继电器
#define ESP12E_RST	P14
#define	ESP01S_RST	P15

#define EE_ADDRESS		0x0400			//EEPROM起始地址
#define Par_Length		1				//参数个数
#define EEPROM_Length	(Par_Length*2)	//EEPROM个数
extern u8  EEPROM_date[EEPROM_Length];			//EEPROM操作缓冲
extern int16	CanShu[Par_Length];				//参数
//[0]为检测功率阀值（？？.？？？mW）;

extern bit	volatile B_RUN ;
extern bit	volatile B_AVA_LM ;



#endif
