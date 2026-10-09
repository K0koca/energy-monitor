import subprocess
import sys
import ctypes


def is_admin():
    """检查是否以管理员身份运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_cmd(cmd):
    """执行系统命令，解决编码报错"""
    try:
        # 关键修改：不指定编码，直接读取字节流，避免gbk解码错误
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=False  # 不自动解码，保持原始字节
        )
        # 优先用utf-8解码，失败则用gbk兜底
        try:
            stdout = result.stdout.decode("utf-8").strip()
        except UnicodeDecodeError:
            stdout = result.stdout.decode("gbk", errors="replace").strip()

        if stdout:
            print("输出信息:", stdout)

        if result.stderr:
            try:
                stderr = result.stderr.decode("utf-8").strip()
            except UnicodeDecodeError:
                stderr = result.stderr.decode("gbk", errors="replace").strip()
            print("错误信息:", stderr)

        return result
    except Exception as e:
        print("执行失败:", e)


def start_hotspot(ssid="MyPCHotspot", password="12345678"):
    """开启热点"""
    print(f"正在创建热点：{ssid}，密码：{password}")
    run_cmd(f'netsh wlan set hostednetwork mode=allow ssid={ssid} key={password}')
    print("正在启动热点...")
    run_cmd('netsh wlan start hostednetwork')


def stop_hotspot():
    """关闭热点"""
    print("正在关闭热点...")
    run_cmd('netsh wlan stop hostednetwork')


if __name__ == "__main__":
    # 自动提权为管理员
    if not is_admin():
        print("正在请求管理员权限...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        sys.exit()

    # ================== 你只需要改这里 ==================
    WIFI_NAME = "DKNWIFI"  # 热点名称
    WIFI_PWD = "76904936100"  # 密码（必须 ≥8位）
    # ===================================================

    print("===== Windows 本地热点工具 =====")
    print("1. 开启热点")
    print("2. 关闭热点")
    choice = input("请输入选项(1/2)：")

    if choice == "1":
        start_hotspot(WIFI_NAME, WIFI_PWD)
    elif choice == "2":
        stop_hotspot()
    else:
        print("输入错误！")

    input("\n按回车退出...")