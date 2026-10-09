#include "config.h"

/*
函数：SendCmdAndWaitOk
功能：发送指令，等待"ok"响应
参数：cmd -> 要发送的指令字符串
返回：1 = 成功收到ok  |  0 = 超时失败
*/

static uint8_t CheckString(const uint8_t *buf, const char *target)
{
    uint16_t i, j;
    uint16_t buf_len = strlen((char *)buf);
    uint16_t tar_len = strlen(target);

    if (tar_len == 0 || buf_len < tar_len)
        return 0;

    for (i = 0; i <= buf_len - tar_len; i++)
    {
        for (j = 0; j < tar_len; j++)
        {
            if (buf[i + j] != target[j])
                break;
        }
        if (j == tar_len)
            return 1; // 找到目标字符串
    }
    return 0; // 未找到
}

uint8_t SendCmdAndWaitOk(const char *cmd)
{
    uint32_t timeout;
    uint8_t  i;
    uint8_t  retry_cnt = 0;    // 重试计数器
    const uint8_t max_retry = 3; 
    while(retry_cnt < max_retry)
    {
        u8UART1RxCount = 0;
        for(i = 0; i < 128; i++)
        {
            pu8UART1RxBuffer[i] = 0x00;
        }
        printf("%s", cmd);

        timeout = 0;
        while(timeout < CMD_TIMEOUT)
        {
            timeout++;
            delay_ms(20);
            if(CheckString(pu8UART1RxBuffer, "OK"))
            {
                return 1;   // 成功，直接返回
            }
        }
        retry_cnt++;
    }
    return 0;
}