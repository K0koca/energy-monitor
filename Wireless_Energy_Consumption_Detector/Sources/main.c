//<<AICUBE_USER_HEADER_REMARK_BEGIN>>
////////////////////////////////////////
// 在此添加用户文件头说明信息  
// 文件名称: main.c
// 文件描述: 
// 文件版本: V1.0
// 修改记录:
//   1. (2026-05-03) 创建文件
////////////////////////////////////////
//<<AICUBE_USER_HEADER_REMARK_END>>


#include "config.h"                     //默认已包含stdio.h、intrins.h等头文件
#include "picture1.h"
#include "picture2.h"



// 温度符号 ℃ 16x16 字模（32字节）
const unsigned char code Celsius_1616[32] = {0x00,0x00,0x00,0x00,0x30,0x00,0x48,0x00,0x48,
0x70,0x30,0x88,0x01,0x00,0x01,0x00,0x01,0x00,0x01,0x00,0x00,0x80,
0x00,0x70,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00};

u8  hour,minute,second; 		//T0_RTC变量
u16 msecond;					//时钟毫秒
u8	LCD_second =0;
u16	AVA_msecond =0;

bit B_lcd =0;
bit volatile B_ok;
bit	volatile B_RUN =1;
bit	volatile B_AVA_LM =0;

// 128x64 点阵屏的 DMA 绘图缓存
u8 xdata LCD_GRAM[1024]; // 128列 × 64行 / 8 = 1024字节
void	T0_RTC(void);				//T0_RTC函数
void INA219DHT11_LCD(void);

void LCD_CGRAM_WriteFont(const unsigned char *font,unsigned char cgram_addr);
void Display_Celsius(u8 x, u8 y);



//本地常量声明
const u8  uctech[]	= {"戴凯宁毕业设计："};
const u8  net[]	= {"主芯片-AI8051U"};
const u8  mcu[]	= {"功耗模块-INA219"};
const u8  qq[]	= {"无线模块-ESP8266"};

//EEPROM 常量声明=变量
u8  EEPROM_date[EEPROM_Length];			//EEPROM操作缓冲
int16	CanShu[Par_Length];				//参数


void main(void)
{
	u16 i =0;
	u8	alm_dur = 0; //报警时长计次
    SYS_Init();
	
	
	EEPROM_read_n( EE_ADDRESS,EEPROM_date,EEPROM_Length);//读取设置参数
	convert8to16(EEPROM_date, CanShu, EEPROM_Length);


	for(i=0; i<1024; i++)	DisTmp[i] = gImage_picture2[i];	//将图片装载到显存
	LCDClear();
	DMA_Config(DisTmp);	//启动DMA，显示图形

    u8UART1RxCount = 0;
    for(i = 0; i < 128; i++)
    {
        pu8UART1RxBuffer[i] = 0x00;
    }
	
	i =0;
	esp8266_Init:
	if( i++ >1 )
		goto esp8266_Lose;
	
	
	ESP12E_RST =0;
	delay_ms(1000);
	ESP12E_RST =1;
	delay_ms(6000);
	B_ok = 	SendCmdAndWaitOk("AT+CIPMODE=1\r\n");
	if ( B_ok == 0)
		goto esp8266_Init;
	B_ok = SendCmdAndWaitOk("AT+CIPSTA=\"192.168.137.100\",\"192.168.137.1\",\"255.255.255.0\"\r\n");
	if ( B_ok == 0)
		goto esp8266_Init;
    B_ok = SendCmdAndWaitOk("AT+CWJAP=\"SPN460D\",\"13390920428_dai\"\r\n");
	if ( B_ok == 0)
		goto esp8266_Init;
    B_ok = SendCmdAndWaitOk("AT+CIPMUX=0\r\n");
	if ( B_ok == 0)
		goto esp8266_Init;
    B_ok = SendCmdAndWaitOk("AT+CIPSTART=\"TCP\",\"192.168.137.1\",8088\r\n");
	if ( B_ok == 0)
		goto esp8266_Init;
    B_ok = SendCmdAndWaitOk("AT+CIPMODE=1\r\n");
	if ( B_ok == 0)
		goto esp8266_Init;
    B_ok = SendCmdAndWaitOk("AT+CIPSEND\r\n");
	if ( B_ok == 0)
		goto esp8266_Init;
	
	esp8266_Lose:
	

	LCDClear();
	DisplayListChar(0,1,uctech);    //显示字库中的中文数字
	DisplayListChar(0,2,net);       //显示字库中的中文数字
	DisplayListChar(0,3,mcu);       //显示字库中的中文
	DisplayListChar(0,4,qq);        //显示字库中的中文数字
	delay_ms(1000);

	LCD_CGRAM_WriteFont( Celsius_1616 ,0x40 );
	delay_ms(1000);


    while (1)
    {
        WDT_Clear();        //清看门狗定时器
		T0_RTC( );							//刷新时钟
		if( LCD_second > 2)
		{
			LCD_second =0;
			INA219DHT11_LCD();
		}
		if( B_AVA_LM )
		{
			if( AVA_msecond >200 )
			{
				AVA_msecond =0;
				RUN =0;
				AVA_LM =!AVA_LM;
				++ alm_dur;			//报警时长计次
				if ( alm_dur >25 )
				{
					alm_dur =0;
					WIFI_POWER =0;
					B_AVA_LM =0;
					AVA_LM =0;
				}
			}
		}
		else
		{
			if( AVA_msecond >10000 )
			{
				AVA_msecond =0;
				RUN =1;
				WIFI_POWER =1;
				AVA_LM =0;
			}
		}
	}
}


// 系统初始化函数

void SYS_Init(void)
{
    EnableAccessXFR();                  //使能访问扩展XFR
    AccessCodeFastest();                //设置最快速度访问程序代码
    AccessIXramFastest();               //设置最快速度访问内部XDATA
    IAP_SetTimeBase();                  //设置IAP等待参数,产生1us时基


    PORT0_Init();                       //P0口初始化
    PORT1_Init();                       //P1口初始化
    PORT2_Init();                       //P2口初始化
    PORT3_Init();                       //P3口初始化
    PORT4_Init();                       //P4口初始化
    PORT5_Init();                       //P5口初始化
    CLK_Init();                         //时钟模块初始化
//    WDT_Init();                         //看门狗初始化
    IAP_Init();                         //EEPROM初始化
    TIMER0_Init();                      //定时器0初始化
    UART1_Init();                       //串口1初始化
    UART2_Init();                       //串口2初始化
    UART4_Init();                       //串口4初始化
    I2C_Init();                         //I2C初始化
    RTC_Init();                         //RTC初始化
//    LCM_Init();                         //LCM模块初始化
	LCM_Config();


    DHT11_Init();  
    INA219_Init(); 
	delay_ms(10);
	LCDInit();		//LCM初始化

	delay_ms(10);
    EnableGlobalInt();  //使能全局中断
}


// 微秒延时函数

void delay_us(uint16_t us)
{
    do
    {
        NOP(34);     //(MAIN_Fosc + 500000) / 1000000 - 6
    } while (--us);
}



// 毫秒延时函数

void delay_ms(uint16_t ms)
{
    uint16_t i;

    do
    {
		WDT_Clear();     //清看门狗定时器
        i = MAIN_Fosc / 6010;
        while (--i);
    } while (--ms);
}


//T0_RTC函数
void T0_RTC(void)
{
	if(T0_1ms)   //1ms到
	{
		T0_1ms = 0;
		++ AVA_msecond;
		if(msecond == 500)
		{
			UART1_Process_RTC_Frame();
			INA219_SendDataToUART4();
		}
		if(++msecond >= 1000)   //1秒到
		{
			++ LCD_second;
			DHT11_SendDataToUART4();
			msecond = 0;
			if(++ second >= 60)   //1分钟到
			{
				second = 0;
				if(++minute >= 60)   //1小时到
				{
					minute = 0;
					if(++hour >= 24)    hour = 0;
				}
			}
		}
		
	}
}

//INA219/DHT11_LCD显示函数
void INA219DHT11_LCD(void)
{
	// 现在 → 用LCD显示
	LCDClear();
	
	if( B_lcd )
	{
		// 显示第一行：电压
		sprintf(buf, "总电压:%.3fV", bus_volt);
		DisplayListChar(0, 1, buf);

		// 显示第二行：分流电压
		sprintf(buf, "分流电压:%.1fmV", shunt_volt);
		DisplayListChar(0, 2, buf);

		// 显示第三行：电流
		sprintf(buf, "电流:%.3fmA", current);
		DisplayListChar(0, 3, buf);

		// 显示第四行：功率
		sprintf(buf, "功率:%.3fmW", power_w);
		DisplayListChar(0, 4, buf);
	}
	else
	{
		sprintf(buf, "   %04d-%02d-%02d  ", 
		2000+RTC_ReadYear(), RTC_ReadMonth(), RTC_ReadDay());
		DisplayListChar(0, 1, buf);
		
		sprintf(buf, "    %02d:%02d:%02d ", 
		RTC_ReadHour(), RTC_ReadMinute(), RTC_ReadSecond());
		DisplayListChar(0, 2, buf);
		if(!read_ok)
		{
			sprintf(buf,"DHT11 连接失败！");
			DisplayListChar(0, 4, buf);
		}
		else
		{
			sprintf(buf,"温度：%.1f ", temp);
			DisplayListChar(0, 3, buf);
			Display_Celsius(5, 3);  		// 直接调用，显示℃

			sprintf(buf, "湿度：%.1f%% RH", humi);
			DisplayListChar(0, 4, buf);
		}
	}
	B_lcd =!B_lcd;

}


//只在指定位置写入1个℃

void Display_Celsius(u8 x, u8 y)
{
	u8 X2;
	X2 = x;

	
	if(y < 1)   y=1;
	if(y > 4)   y=4;
	x &= 0x0F; //限制X不能大于16，Y在1-4之内
	switch(y)
	{
		case 1: X2 |= 0X80; break;  //根据行数来选择相应地址
		case 2: X2 |= 0X90; break;
		case 3: X2 |= 0X88; break;
		case 4: X2 |= 0X98; break;
	}
	WriteCommandLCD(X2); //发送地址码

	WriteDataLCD(0);
	WriteDataLCD(0);

}

// 功能：通用 CGRAM 造字函数
void LCD_CGRAM_WriteFont(const unsigned char *font,unsigned char cgram_addr)
{
    unsigned char i;
    WriteCommandLCD(0x30);
    WriteCommandLCD(cgram_addr);
    for(i=0;i<32;i++)
    {
        WriteDataLCD(font[i]);
    }
}