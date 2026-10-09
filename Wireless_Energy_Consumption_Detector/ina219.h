//<<AICUBE_USER_HEADER_REMARK_BEGIN>>
////////////////////////////////////////
// 自定义文件头说明信息  
// 文件名: ina219.h
// 文件版本: V1.0
// 修改记录:
//   1. (2026-05-01) 创建文件
////////////////////////////////////////
//<<AICUBE_USER_HEADER_REMARK_END>>

#ifndef __INA219_H__
#define __INA219_H__


//<<AICUBE_USER_DEFINE_BEGIN>>
// INA219 设备地址（可根据A0/A1引脚配置修改）
#define INA219_I2C_ADDR         0x40    // 默认I2C地址: 01000000
// INA219 寄存器地址
#define INA219_REG_CONFIG       0x00    // 配置寄存器
#define INA219_REG_SHUNTVOLT    0x01    // 分流电压寄存器
#define INA219_REG_BUSVOLT      0x02    // 总线电压寄存器
#define INA219_REG_POWER        0x03    // 功率寄存器
#define INA219_REG_CURRENT      0x04    // 电流寄存器
#define INA219_REG_CALIBRATION  0x05    // 校准寄存器


// 硬件参数配置
#define INA219_R_SHUNT          0.1f    // 分流电阻值，单位Ω
#define INA219_MAX_EXPECTED_CURRENT  0.4  // 最大预期电流，单位A

// 自动计算LSB和校准值
#define INA219_CURRENT_LSB      ((float)INA219_MAX_EXPECTED_CURRENT / 32768.0f)
#define INA219_CALIBRATION_VAL  (uint16_t)(0.04096f / (INA219_CURRENT_LSB * INA219_R_SHUNT))
#define INA219_POWER_LSB        (20.0f * INA219_CURRENT_LSB)

// 校准值
//#define INA219_CALIBRATION_VAL  0x1000    // 对应最大电流3.2A，0.1Ω分流电阻
//<<AICUBE_USER_DEFINE_END>>

/**
 * @brief 初始化INA219芯片
 * @param 无
 * @retval 无
 */
void INA219_Init(void);

/**
 * @brief 读取INA219分流电压（mV）
 * @param 无
 * @retval 分流电压值，单位：mV
 */
float INA219_ReadShuntVoltage(void);

/**
 * @brief 读取INA219总线电压（V）
 * @param 无
 * @retval 总线电压值，单位：V（放大1000倍，如5.000V返回5000）
 */
float INA219_ReadBusVoltage(void);

/**
 * @brief 读取INA219电流值（mA）
 * @param 无
 * @retval 电流值，单位：mA
 */
float INA219_ReadCurrent(void);

/**
 * @brief 读取INA219功率值（mW）
 * @param 无
 * @retval 功率值，单位：mW
 */
float INA219_ReadPower(void);

//<<AICUBE_USER_EXTERNAL_DECLARE_BEGIN>>
// 自定义外部声明/外部函数声明  
//<<AICUBE_USER_EXTERNAL_DECLARE_END>>
void INA219_SendDataToUART4(void);

//<<AICUBE_USER_GLOBAL_DEFINE_BEGIN>>
extern float bus_volt ;
extern float shunt_volt ;
extern float current ;
extern float power_w ;
extern u8 buf[32];
//<<AICUBE_USER_GLOBAL_DEFINE_END>>


#endif