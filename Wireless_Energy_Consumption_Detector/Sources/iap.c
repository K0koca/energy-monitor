//<<AICUBE_USER_HEADER_REMARK_BEGIN>>
////////////////////////////////////////
// 在此添加用户文件头说明信息  
// 文件名称: iap.c
// 文件描述: 
// 文件版本: V1.0
// 修改记录:
//   1. (2026-05-03) 创建文件
////////////////////////////////////////
//<<AICUBE_USER_HEADER_REMARK_END>>


#include "config.h"


//<<AICUBE_USER_INCLUDE_BEGIN>>
// 在此添加用户头文件包含  
//<<AICUBE_USER_INCLUDE_END>>


//<<AICUBE_USER_GLOBAL_DEFINE_BEGIN>>
// 在此添加用户全局变量定义、用户宏定义以及函数声明  
//<<AICUBE_USER_GLOBAL_DEFINE_END>>



////////////////////////////////////////
// IAP初始化函数
// 入口参数: 无
// 函数返回: 无
////////////////////////////////////////
void IAP_Init(void)
{
    IAP_Enable();                       //使能EEPROM操作
    IAP_Idle();                         //设置EEPROM为空闲模式

    //<<AICUBE_USER_IAP_INITIAL_BEGIN>>
    // 在此添加用户初始化代码  
    //<<AICUBE_USER_IAP_INITIAL_END>>
}
////////////////////////////////////////
// EEPROM扇区擦除函数
// 入口参数: dwAddress (EEPROM目标扇区地址)
// 函数返回: 无
////////////////////////////////////////
void IAP_EraseSector(uint32_t dwAddress)
{
    IAP_SetAddress(dwAddress);          //设置EEPROM目标地址
    IAP_TriggerErase();                 //触发EEPROM扇区擦除
    IAP_Idle();                         //恢复EEPROM空闲模式
}

////////////////////////////////////////
// EEPROM字节编程函数
// 入口参数: dwAddress (EEPROM目标字节地址)
//           bData (待写入的字节数据)
// 函数返回: 无
////////////////////////////////////////
void IAP_ProgramByte(uint32_t dwAddress, uint8_t bData)
{
    IAP_SetAddress(dwAddress);          //设置EEPROM目标地址
    IAP_SetData(bData);                 //设置EEPROM数据
    IAP_TriggerProgram();               //触发EEPROM字节编程
    IAP_Idle();                         //恢复EEPROM空闲模式
}

////////////////////////////////////////
// EEPROM字节读取函数
// 入口参数: dwAddress (EEPROM目标字节地址)
// 函数返回: (读取的字节数据)
////////////////////////////////////////
uint8_t IAP_ReadByte(uint32_t dwAddress)
{
    uint8_t dat;

    IAP_SetAddress(dwAddress);          //设置EEPROM目标地址
    IAP_TriggerRead();                  //触发EEPROM字节读取
    dat = IAP_ReadData();               //保存EEPROM数据
    IAP_Idle();                         //恢复EEPROM空闲模式

    return dat;                         //返回读取的数据
}



//<<AICUBE_USER_FUNCTION_IMPLEMENT_BEGIN>>
//========================================================================
// 函数: void EEPROM_read_n(u32 EE_address,u8 *DataAddress,u16 number)
// 描述: 从指定EEPROM首地址读出n个字节放指定的缓冲.
// 参数: EE_address:  读出EEPROM的首地址.
//       DataAddress: 读出数据放缓冲的首地址.
//       number:      读出的字节长度.
// 返回: non.
// 版本: V1.0, 2012-10-22
//========================================================================
void EEPROM_read_n(u32 EE_address,u8 *DataAddress,u16 number)
{
	do
	{
		*DataAddress = IAP_ReadByte(EE_address);            //读出的数据送往
		EE_address++;
		DataAddress++;
	}while(--number);

}

//========================================================================
// 函数: void EEPROM_write_n(u32 EE_address,u8 *DataAddress,u16 number)
// 描述: 把缓冲的n个字节写入指定首地址的EEPROM.
// 参数: EE_address:  写入EEPROM的首地址.
//       DataAddress: 写入源数据的缓冲的首地址.
//       number:      写入的字节长度.
// 返回: non.
// 版本: V1.0, 2012-10-22
//========================================================================
void EEPROM_write_n(u32 EE_address,u8 *DataAddress,u16 number)
{
	do
	{
		IAP_ProgramByte(EE_address, *DataAddress);
		EE_address++;                     //下一个地址
		DataAddress++;                    //下一个数据
	}while(--number);                   //直到结束
}
//<<AICUBE_USER_FUNCTION_IMPLEMENT_END>>


