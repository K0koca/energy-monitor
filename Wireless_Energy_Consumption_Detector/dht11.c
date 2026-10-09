#include "config.h"

float temp = 0;   // 温度
float humi = 0;   // 湿度
uint8_t read_ok = 0;

/* 超时宏定义*/
#define DHT11_TIMEOUT_MAX  40000		//40M,1ms

/* DHT11初始化：主机发送起始信号 */
void DHT11_Init(void)
{
    DHT11_DATA = 1;        /* 总线拉高 */
    delay_ms(1000);        
}

/* 主机发送起始信号 */
static void DHT11_Start(void)
{
    DHT11_DATA = 1;
    delay_us(2);
    DHT11_DATA = 0;
    delay_ms(30);
    DHT11_DATA = 1;
    delay_us(40);
}

//带超时的等待电平函数
static uint8_t DHT11_WaitLevel(uint8_t level)
{
    uint32_t timeout = 0;
    while(DHT11_DATA != level)
    {
        timeout++;
        if(timeout > DHT11_TIMEOUT_MAX)
        {
            return 0; // 超时退出
        }
    }
    return 1;
}

//读取一个字节（带超时）
static unsigned char DHT11_ReadByte(uint8_t *err_flag)
{
    unsigned char i, dat = 0;

    for(i=0; i<8; i++)
    {
        // 等待低电平开始
        if(!DHT11_WaitLevel(0))
        {
            *err_flag = 1;
            return 0;
        }
        // 等待高电平
        if(!DHT11_WaitLevel(1))
        {
            *err_flag = 1;
            return 0;
        }

        delay_us(40);
        dat <<= 1;
        if(DHT11_DATA == 1)
        {
            dat |= 1;
        }

        // 等待高电平结束
        if(!DHT11_WaitLevel(0))
        {
            *err_flag = 1;
            return 0;
        }
    }
    return dat;
}

/* 读取一帧数据：返回0成功，1失败（带完整超时保护） */
unsigned char DHT11_ReadData(DHT11_Data_TypeDef *dat)
{
    unsigned char buf[5] = {0};
    uint8_t err_flag = 0;

    // 1. 起始信号
    DHT11_Start();

    // 等待DHT11拉低应答
    if(!DHT11_WaitLevel(0))
    {
        return 1;
    }
    // 等待DHT11拉高
    if(!DHT11_WaitLevel(1))
    {
        return 1;
    }

    // 2. 读取40位数据
    buf[0] = DHT11_ReadByte(&err_flag);
    buf[1] = DHT11_ReadByte(&err_flag);
    buf[2] = DHT11_ReadByte(&err_flag);
    buf[3] = DHT11_ReadByte(&err_flag);
    buf[4] = DHT11_ReadByte(&err_flag);

    if(err_flag)
    {
        return 1;
    }

    // 3. 校验
    if((buf[0] + buf[1] + buf[2] + buf[3]) == buf[4])
    {
        dat->humi_int = buf[0];
        dat->humi_dec = buf[1];
        dat->temp_int = buf[2];
        dat->temp_dec = buf[3];
        dat->check    = buf[4];
        return 0;
    }
    return 1;
}

// 串口4输出DHT11采集数据
void DHT11_SendDataToUART4(void)
{
    u8 i;
    DHT11_Data_TypeDef dht11;

    temp = 0;
    humi = 0;

    for(i=0; i<1; i++)
    {
        if(DHT11_ReadData(&dht11) == 0)
        {
            temp += dht11.temp_int + (float)dht11.temp_dec / 10.0;
            humi += dht11.humi_int + (float)dht11.humi_dec / 10.0;
            read_ok = 1;
        }
    }

    if(!read_ok)
    {
        printf("DHT11 连接失败！\r\n\r\n");
        return;
    }

    temp = temp / i;
    humi = humi / i;

    printf("DHT11 Data:\r\n");
    printf("Temperature: %.1f\xE2\x84\x83 \r\n", temp);
    printf("Humidity: %.1f%% RH\r\n\r\n", humi);
}