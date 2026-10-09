
#include	"config.h"

//===========================16位数组转存8位数组中=============================================
void convert16to8(int16 *input, u8 *output, u16 length) 
{
  u16 i, j;
    
    // 确保输入参数有效
    if(input == NULL || output == NULL) {
        return;
    }
    
    for(i = 0, j = 0; i < length; i++, j += 2)
    {
        output[j]   = (input[i] & 0x00FF);       // 最低字节
        output[j+1] = (input[i] & 0xFF00) >> 8;  // 次低字节
    }
}

//===========================8位数组转存16位数组中=============================================
void convert8to16(u8 *input, int16 *output, u16 length) 
{
   u16 i, j;
    // 确保输入长度是4的倍数
    if(length % 2 != 0) {
        return; // 或者处理错误
    }
    
    for(i = 0, j = 0; i < length; i += 2, j++) 
    {
        output[j] = ( (int16)input[i]) | 
										( (int16)input[i+1] << 8);
    }
}

//===========================32位数组转存8位数组中=============================================
void convert32to8(int32 *input, u8 *output, u16 length)
{
    u16 i, j;
    
    // 确保输入参数有效
    if(input == NULL || output == NULL) {
        return;
    }
    
    for(i = 0, j = 0; i < length; i++, j += 4)
    {
        output[j]   = (input[i] & 0x000000FF);       // 最低字节
        output[j+1] = (input[i] & 0x0000FF00) >> 8;  // 次低字节
        output[j+2] = (input[i] & 0x00FF0000) >> 16; // 次高字节
        output[j+3] = (input[i] & 0xFF000000) >> 24; // 最高字节
    }
}
//===========================8位数组转存32位数组中=============================================
void convert8to32(u8 *input, int32 *output, u16 length) 
{
    u16 i, j;
    
    // 确保输入长度是4的倍数
    if(length % 4 != 0) {
        return; // 或者处理错误
    }
    
    for(i = 0, j = 0; i < length; i += 4, j++) 
    {
        output[j] = ( (int32)input[i]) | 
										( (int32)input[i+1] << 8) | 
										( (int32)input[i+2] << 16)  | 
										( (int32)input[i+3] << 24);
    }
}
