
#include "config.h"

float bus_volt =0 ;
float shunt_volt =0;
float current =0;
float power_w =0;
u8 buf[32];

//向INA219寄存器写入16位数据

static void INA219_WriteReg(uint8_t reg_addr, uint16_t dat)
{
    while (I2C_CheckMasterBusy());  // 等待I2C总线空闲
    I2C_ClearMasterFlag();          // 清除完成标志
    
    // 发送I2C起始信号+设备写地址
    I2C_MasterStartSendByte(INA219_I2C_ADDR << 1);
    // 发送寄存器地址
    I2C_MasterSendByte(reg_addr);
    // 发送高8位数据
    I2C_MasterSendByte((dat >> 8) & 0xFF);
    // 发送低8位数据
    I2C_MasterSendByte(dat & 0xFF);
    
    I2C_MasterStop();               // 发送停止信号
}

//从INA219寄存器读取16位数据

static uint16_t INA219_ReadReg(uint8_t reg_addr)
{
    uint16_t dat = 0;
    
    while (I2C_CheckMasterBusy()); 
    I2C_ClearMasterFlag();
    I2C_MasterStartSendByte(INA219_I2C_ADDR << 1);
    I2C_MasterSendByte(reg_addr);
    
    // 发送重复起始信号+设备读地址
    I2C_MasterStartSendByte((INA219_I2C_ADDR << 1) | 0x01);
    // 读取高8位（发送ACK）
    dat = (uint16_t)I2C_MasterReadByte(0) << 8;
    // 读取低8位（发送NAK）
    dat |= (uint16_t)I2C_MasterReadByte(1);
    
    I2C_MasterStop();  // 发送停止信号
    
    return dat;
}

//初始化INA219芯片
void INA219_Init(void)
{
    INA219_WriteReg(INA219_REG_CONFIG, 0x07FF); // 0x07FF = 0000 0111 1111 1111
    INA219_WriteReg(INA219_REG_CALIBRATION, INA219_CALIBRATION_VAL);
}

//读取INA219分流电压（mV）

float INA219_ReadShuntVoltage(void)
{
    int16_t voltage = (int16_t)INA219_ReadReg(INA219_REG_SHUNTVOLT);
    // 分流电压LSB = 10uV，转换为mV需除以100
    return (voltage * 0.01f);
}

//读取INA219总线电压（V）
float INA219_ReadBusVoltage(void)
{
    uint16_t voltage = INA219_ReadReg(INA219_REG_BUSVOLT);
    // 总线电压LSB = 4mV，需右移3位舍弃状态位后乘以4
    
    return ((voltage >> 3) * 0.004f);
}

//读取INA219电流值（mA）

float INA219_ReadCurrent(void)
{
    // 电流LSB由校准值决定，示例中校准值4096对应1mA/LSB
    int16_t raw = (int16_t)INA219_ReadReg(INA219_REG_CURRENT);
    return raw * INA219_CURRENT_LSB *1004;
}

//读取INA219功率值（mW）

float INA219_ReadPower(void)
{
    // 功率LSB = 20*电流LSB（示例中为20mW/LSB）
    uint16_t raw = INA219_ReadReg(INA219_REG_POWER);
    return raw * INA219_POWER_LSB *994;
}


// 串口1输出INA219采集数据
void INA219_SendDataToUART4(void)
{

	bus_volt = INA219_ReadBusVoltage();
	shunt_volt = INA219_ReadShuntVoltage();
	current = INA219_ReadCurrent();
	power_w = INA219_ReadPower();

    
//格式化输出
	printf("RTC Time: %04d-%02d-%02d %02d:%02d:%02d\r\n", 
	2000 + RTC_ReadYear(), RTC_ReadMonth(), RTC_ReadDay(), 
	RTC_ReadHour(), RTC_ReadMinute(), RTC_ReadSecond());
    printf("INA219 Data:\r\n");
    printf("Bus Voltage: %.3f V\r\n", bus_volt);
    printf("Shunt Voltage: %.3f mV\r\n", shunt_volt);
    printf("Current: %.3f mA\r\n", current);
    printf("Power_w: %.3f mW\r\n\r\n", power_w);
	
	
	if( (uint16_t)power_w > CanShu[0] )
	{
		B_AVA_LM =1;
	}
}