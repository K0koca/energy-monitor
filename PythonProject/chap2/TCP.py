import socket
import threading

# 配置：和ESP8266连接的端口号一致
HOST = '0.0.0.0'  # 监听本机所有网卡
PORT = 8088       # 和ESP8266的AT指令端口号必须一致

# 全局变量，保存连接对象
client_conn = None

def receive_data():
    """ 接收ESP8266发来的数据 """
    global client_conn
    while True:
        try:
            data = client_conn.recv(1024)
            if not data:
                print("ESP8266 断开连接了")
                break
            print(f"收到ESP8266数据：{data.decode('utf-8', errors='ignore')}")
        except Exception as e:
            print(f"接收出错：{e}")
            break

def send_data():
    """ 从键盘输入数据，发送给ESP8266 """
    global client_conn
    while True:
        msg = input("请输入要发送给ESP8266的内容（输入exit退出）：\n")
        if msg.lower() == 'exit':
            client_conn.close()
            break
        try:
            # 加上换行符，方便单片机识别结束
            client_conn.sendall((msg + "\r\n").encode('utf-8'))
            print(f"已发送：{msg}")
        except Exception as e:
            print(f"发送失败：{e}，连接可能已断开")
            break

if __name__ == "__main__":
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"服务器已启动，端口：{PORT}，等待ESP8266连接...")
        print(f"提示：请在ESP8266端执行AT+CIPSTART=\"TCP\",\"电脑IP\",{PORT}")

        # 等待ESP8266连接
        client_conn, addr = s.accept()
        print(f"ESP8266 已连接！地址：{addr}")

        # 启动接收线程（后台运行，不影响发送）
        recv_thread = threading.Thread(target=receive_data, daemon=True)
        recv_thread.start()

        # 主线程负责发送数据
        send_data()

    print("服务器已关闭")