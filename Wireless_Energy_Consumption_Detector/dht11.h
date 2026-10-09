#ifndef __DHT11_H
#define __DHT11_H


/* 数据结构体 */
typedef struct {
    unsigned char humi_int;
    unsigned char humi_dec;
    unsigned char temp_int;
    unsigned char temp_dec;
    unsigned char check;
} DHT11_Data_TypeDef;

/* 函数声明 */
void DHT11_Init(void);
unsigned char DHT11_ReadData(DHT11_Data_TypeDef *dat);
void DHT11_SendDataToUART4(void);

extern float temp;
extern float humi;
extern	uint8_t read_ok ;

#endif