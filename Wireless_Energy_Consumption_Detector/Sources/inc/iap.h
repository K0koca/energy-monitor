//<<AICUBE_USER_HEADER_REMARK_BEGIN>>
////////////////////////////////////////
// 在此添加用户文件头说明信息  
// 文件名称: iap.h
////////////////////////////////////////
//<<AICUBE_USER_HEADER_REMARK_END>>


#ifndef __IAP_H__
#define __IAP_H__


//<<AICUBE_USER_DEFINE_BEGIN>>
// 在此添加用户宏定义  
//<<AICUBE_USER_DEFINE_END>>


#define IAP_OFFSET              0xfc00  //定义EEPROM起始地址


void IAP_Init(void);
void IAP_EraseSector(uint32_t dwAddress);
void IAP_ProgramByte(uint32_t dwAddress, uint8_t bData);
uint8_t IAP_ReadByte(uint32_t dwAddress);
void EEPROM_read_n(u32 EE_address,u8 *DataAddress,u16 number);
void EEPROM_write_n(u32 EE_address,u8 *DataAddress,u16 number);



//<<AICUBE_USER_EXTERNAL_DECLARE_BEGIN>>
// 在此添加用户外部函数和外部变量声明  
//<<AICUBE_USER_EXTERNAL_DECLARE_END>>


#endif
