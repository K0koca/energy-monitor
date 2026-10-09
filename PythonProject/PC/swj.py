import os
import sys
# 让 swj.py 能找到 llm_energy_agent 子目录里的模块
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_energy_agent")
)

from ai_panel import open_ai_panel
import socket
import threading
import tkinter as tk
from tkinter import ttk, messagebox,simpledialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.ticker as ticker
import numpy as np
import time
import queue
import datetime
from collections import deque
from db_module import EnergyDataDB

#全局设置
connected = False
data_queue = queue.Queue()
db = EnergyDataDB()
v_list = deque(maxlen=30)
i_list = deque(maxlen=30)
p_list = deque(maxlen=30)
t_list = deque(maxlen=30)

temp_value = 0.0
humi_value = 0.0

root = None
btn = None
lbl_v = None
lbl_i = None
lbl_p = None
lbl_temp = None
lbl_humi = None
canvas = None
fig = None
ax_v = None
ax_i = None
ax_p = None
entry = None
server = None
client = None
PORT = 8088
client_conn = None

line_v = None
line_i = None
line_p = None

#TCP服务器线程
def wifi_server():
    global connected, server, client, client_conn
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(1)
    server.bind(("0.0.0.0", PORT))
    server.listen(1)
    print("等待 ESP8266 连接...")

    try:
        while connected:
            try:
                client, addr = server.accept()
                client_conn = client
                print(f"ESP8266 已连接：{addr}")
                break
            except socket.timeout:
                continue

        # 接收数据
        while connected and client:
            data = client.recv(1024).decode('UTF-8', errors='ignore').strip()
            if not data:
                break
            print(f"{data}")

            if "INA219 Data:" in data:
                try:
                    v_start = data.find("Bus Voltage:") + len("Bus Voltage:")
                    v_end = data.find("V", v_start)
                    voltage = float(data[v_start:v_end].strip())

                    i_start = data.find("Current:") + len("Current:")
                    i_end = data.find("mA", i_start)
                    current= float(data[i_start:i_end].strip())

                    p_start = data.find("Power_w:") + len("Power_w:")
                    p_end = data.find("mW", p_start)
                    power = float(data[p_start:p_end].strip())
                  #  print(f"解析成功 → 电压:{voltage:.3f}V 电流:{current:.3f}mA 功率:{power:.3f}mW")
                    data_queue.put((voltage, current, power))
                    db.save_energy(voltage, current, power)
                except Exception as e:
                    print(f"解析失败: {e}")
            if "DHT11 Data:" in data:
                try:
                    t_start = data.find("Temperature:") + len("Temperature:")
                    t_end = data.find("℃", t_start)
                    temp = float(data[t_start:t_end].strip())
                    global temp_value
                    temp_value = temp

                    h_start = data.find("Humidity:")  + len("Humidity:")
                    h_end = data.find("%", h_start)
                    humi = float(data[h_start:h_end].strip())
                    global humi_value
                    humi_value = humi
                #    print(f"温度:{temp}℃ 湿度:{humi}%")
                except:
                    print(f"收到ESP8266反馈: {data}")
    except Exception as e:
            print("网络异常：", e)
    finally:
            connected = False
            if client:
                client.close()
            if server:
                server.close()
            client_conn = None
            if btn:
                btn.config(text="启动无线")

#启动/停止服务
def start_server():
    global connected
    if not connected:
        connected = True
        btn.config(text="停止服务")
        threading.Thread(target=wifi_server, daemon=True).start()
    else:
        connected = False
        btn.config(text="启动无线")

#发送指令函数
def send_command(event=None):
    global client_conn
    if not connected or client_conn is None:
        messagebox.showwarning("警告", "请先启动无线！")
        return

    msg = entry.get().strip()
    if not msg:
        return

    try:
        client_conn.sendall((msg + "\r\n").encode('utf-8'))
        print(f"已发送：{msg}")
        entry.delete(0, tk.END)
    except Exception as e:
        messagebox.showerror("错误", f"发送失败：{e}\n连接可能已断开")

def crc16_modbus(data: bytes) -> int:
    crc_modbus1 = 0xFFFF
    for byte in data:
        crc_modbus1 ^= byte
        for _ in range(8):
            if crc_modbus1 & 0x0001:
                crc_modbus1 = (crc_modbus1 >> 1) ^ 0xA001
            else:
                crc_modbus1 >>= 1
    return crc_modbus1 & 0xFFFF

def sync_rtc():
    global client_conn
    if not connected or client_conn is None:
        messagebox.showwarning("警告", "请先启动无线！")
        return

    now = datetime.datetime.now()
    header1 = ord('R')
    header2 = ord('T')
    header3 = ord('C')
    header4 = 3
    year = now.year - 2000
    month = now.month
    day = now.day
    hour = now.hour
    minute = now.minute
    second = now.second
    data_packet = (bytes
    ([
        header1,
        header2,
        header3,
        header4,
        year,
        month,
        day,
        hour,
        minute,
        second
    ]))

    crc_val = crc16_modbus(data_packet)
    crc_low = crc_val & 0xFF
    crc_high = (crc_val >> 8) & 0xFF
    send_data = data_packet + bytes([crc_low, crc_high])

    try:
        client_conn.sendall(send_data)
        messagebox.showinfo("成功", "RTC时间同步指令发送完成！")
    except Exception as e:
        messagebox.showerror("错误", f"发送失败：{e}")


def PW_TH():
    global client_conn
    if not connected or client_conn is None:
        messagebox.showwarning("警告", "请先启动无线！")
        return

    value = simpledialog.askinteger("输入参数", "请输入十进制参数（0 ~ 1000）：", minvalue=0, maxvalue=1000)
    if value is None:
        return

    low_byte = value & 0xFF
    high_byte = (value >> 8) & 0xFF
    data_packet = bytes([0x52, 0x54, 0x43, 0x01, low_byte, high_byte])
    crc_val = crc16_modbus(data_packet)
    crc_low = crc_val & 0xFF
    crc_high = (crc_val >> 8) & 0xFF
    send_data = data_packet + bytes([crc_low, crc_high])

    print(f"输入十进制：{value}")
    print(f"低位: {low_byte:02X}  高位: {high_byte:02X}")
    print(f"发送数据包：{send_data.hex(' ').upper()}")

    try:
        client_conn.sendall(send_data)
        messagebox.showinfo("发送成功",
                           f"输入值：{value}\n"
                           f"低位：0x{low_byte:02X}\n"
                           f"高位：0x{high_byte:02X}\n\n"
                           f"数据包：{send_data.hex(' ').upper()}")
    except Exception as e:
        messagebox.showerror("错误", f"发送失败：{str(e)}")

def wifi_sl():
    global client_conn
    if not connected or client_conn is None:
        messagebox.showwarning("警告", "请先启动无线！")
        return
    data_packet = bytes([0x52, 0x54, 0x43, 0x02, 0x00])
    crc_val = crc16_modbus(data_packet)
    crc_low = crc_val & 0xFF
    crc_high = (crc_val >> 8) & 0xFF
    send_data = data_packet + bytes([crc_low, crc_high])
    try:
        client_conn.sendall(send_data)
        messagebox.showinfo("成功", "睡觉")
    except Exception as e:
        messagebox.showerror("错误", f"发送失败：{e}")

def wifi_wk():
    global client_conn
    if not connected or client_conn is None:
        messagebox.showwarning("警告", "请先启动无线！")
        return
    data_packet = bytes([0x52, 0x54, 0x43, 0x02, 0xAA])
    crc_val = crc16_modbus(data_packet)
    crc_low = crc_val & 0xFF
    crc_high = (crc_val >> 8) & 0xFF
    send_data = data_packet + bytes([crc_low , crc_high])
    try:
        client_conn.sendall(send_data)
        messagebox.showinfo("成功", "起床")
    except Exception as e:
        messagebox.showerror("错误", f"发送失败：{e}")

def clear_db_btn_click():
    res = messagebox.askyesno("确认", "确定要清空所有历史数据吗？\n清空后不可恢复！")
    if res:
        if db.clear_all_data():
            messagebox.showinfo("成功", "历史数据已全部清空！")
        else:
            messagebox.showerror("失败", "清空数据库出错！")

#平滑滤波
def auto_scale_y(ax, data_list, type="voltage"):
    if not data_list:
        return

    if type == "voltage":
        ax.set_ylim(2.500, 3.500)
    elif type == "current":
        ax.set_ylim(-200.000, -0.000)
    elif type == "power":
        ax.set_ylim(20.000, 550.000)
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter('%.3f'))

def moving_average(data, window=5):
    if len(data) < window:
        return data
    return [sum(data[i:i+window])/window for i in range(len(data)-window+1)]

#GUI 刷新
def update_gui():
    global v_list, i_list, p_list, t_list
    global line_v, line_i, line_p

    lbl_temp.config(text=f"温度：{temp_value:.1f} ℃")
    lbl_humi.config(text=f"湿度：{humi_value:.1f} %RH")

    if not connected:
        root.after(200, update_gui)
        return

    has_new = False
    while not data_queue.empty():
        v, i, p = data_queue.get_nowait()
        has_new = True

        lbl_v.config(text=f"电压：{v:.3f} V")
        lbl_i.config(text=f"电流：{i:.3f} mA")
        lbl_p.config(text=f"功率：{p:.3f} mW")

        v_list.append(v)
        i_list.append(i)
        p_list.append(p)
        t_list.append(time.strftime("%H:%M:%S"))

    if has_new:
        # 不clear，只更新数据
        line_v.set_data(list(range(len(v_list))), v_list)
        line_i.set_data(list(range(len(i_list))), i_list)
        line_p.set_data(list(range(len(p_list))), p_list)
        auto_scale_y(ax_v, v_list, "voltage")
        auto_scale_y(ax_i, i_list, "current")
        auto_scale_y(ax_p, p_list, "power")

        for idx, ax in enumerate([ax_v, ax_i, ax_p]):
            ax.relim()
            ax.autoscale_view(scalex=True, scaley=False)
            if len(t_list) > 0:
                num = min(6, len(t_list))
                ids = np.linspace(0, len(t_list)-1, num, dtype=int)
                ax.set_xticks(ids)
                ax.set_xticklabels([t_list[j] for j in ids], rotation=30, fontsize=8)

        canvas.draw()  # 轻量重绘

    root.after(100, update_gui)


#关闭窗口
def on_closing():
    global connected
    connected = False
    if client:
        client.close()
    if server:
        server.close()
    root.quit()
    root.destroy()


#GUI 创建
def create_gui():
    global root, btn, lbl_v, lbl_i, lbl_p,lbl_temp, lbl_humi, canvas, fig, ax_v, ax_i, ax_p, entry
    global line_v, line_i, line_p

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False

    root = tk.Tk()
    root.title("能耗监控系统")
    root.geometry("1100x700")
    root.protocol("WM_DELETE_WINDOW", on_closing)

    main_frame = tk.Frame(root, bg="#f5f6fa")
    main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    #控制面板
    control_frame = ttk.LabelFrame(main_frame, text="控制与交互")
    control_frame.pack(fill=tk.X, pady=5)
    #启动按钮
    btn = ttk.Button(control_frame, text="启动透传", command=start_server)
    btn.pack(side=tk.LEFT, padx=10, pady=10)
    btn_rtc = ttk.Button(control_frame, text="同步RTC时间", command=sync_rtc)
    btn_rtc.pack(side="left", padx=5, pady=10)

    #功率阈值指令
    btn_pw = ttk.Button(control_frame, text="发送PW参数", command=PW_TH)
    btn_pw.pack(side="left", padx=5, pady=10)

    btn_sl = ttk.Button(control_frame, text="无线睡眠", command=wifi_sl)
    btn_sl.pack(side="left", padx=5, pady=10)

    btn_wk = ttk.Button(control_frame, text="无线醒来", command=wifi_wk)
    btn_wk.pack(side="left", padx=5, pady=10)

    btn_clear_db = ttk.Button(control_frame, text="清空历史数据", command=clear_db_btn_click)
    btn_ai = ttk.Button(control_frame, text="AI 分析",command=lambda: open_ai_panel(root))
    btn_ai.pack(side="left", padx=5, pady=10)
    btn_clear_db.pack(side="left", padx=5, pady=10)
    #分隔符
    ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side="left", fill=tk.Y, padx=10, pady=5)
    #指令输入标签
    tk.Label(control_frame, text="发送数据:", bg="#f5f6fa").pack(side="left", padx=(10, 0))
    #指令输入框
    entry = ttk.Entry(control_frame, width=10)
    entry.pack(side="left", padx=5, pady=10)
    entry.bind('<Return>', send_command)
    #发送按钮
    btn_send = ttk.Button(control_frame, text="发送", command=send_command)
    btn_send.pack(side="left", padx=5, pady=10)

    #温度湿度
    temp_humi_frame = tk.Frame(control_frame, bg="#f5f6fa")
    temp_humi_frame.pack(side="right", padx=20)

    lbl_temp = tk.Label(temp_humi_frame, text="温度：0.0 ℃", font=("微软雅黑", 14), fg="black")
    lbl_temp.pack(anchor="e")
    lbl_humi = tk.Label(temp_humi_frame, text="湿度：0.0 %RH", font=("微软雅黑", 14), fg="black")
    lbl_humi.pack(anchor="e")
    #功耗
    data_frame = ttk.LabelFrame(main_frame, text="实时数据")
    data_frame.pack(fill="x", pady=5)
    inner = tk.Frame(data_frame)
    inner.pack(fill="x", pady=10)

    lbl_v = tk.Label(inner, text="电压：0.000 V", font=("微软雅黑", 16), fg="#e74c3c")
    lbl_v.pack(side=tk.LEFT, expand=True)
    lbl_i = tk.Label(inner, text="电流：0.000 mA", font=("微软雅黑", 16), fg="#3498db")
    lbl_i.pack(side=tk.LEFT, expand=True)
    lbl_p = tk.Label(inner, text="功率：0.000 mW", font=("微软雅黑", 16), fg="#2ecc71")
    lbl_p.pack(side=tk.LEFT, expand=True)

    #曲线
    plot_frame = ttk.LabelFrame(main_frame, text="实时曲线")
    plot_frame.pack(fill=tk.BOTH, expand=True, pady=5)
    fig = plt.Figure(figsize=(16, 4), dpi=100)

    ax_v = fig.add_subplot(131)
    ax_i = fig.add_subplot(132)
    ax_p = fig.add_subplot(133)
    fig.subplots_adjust(wspace=0.35)

    line_v, = ax_v.plot([], [], label="电压(V)", color="#e74c3c", marker=".", linewidth=2)
    line_i, = ax_i.plot([], [], label="电流(mA)", color="#3498db", marker=".", linewidth=2)
    line_p, = ax_p.plot([], [], label="功率(mW)", color="#2ecc71", marker=".", linewidth=2)

    for idx, ax in enumerate([ax_v, ax_i, ax_p]):
        ax.set_title(["电压", "电流", "功率"][idx] + "实时曲线", fontsize=10)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, linestyle="--", alpha=0.5)
        auto_scale_y(ax, [], ["voltage", "current", "power"][idx])

    ax_v.set_xlabel("电压", fontsize=10, labelpad=10)
    ax_i.set_xlabel("电流", fontsize=10, labelpad=10)
    ax_p.set_xlabel("功率", fontsize=10, labelpad=10)
    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    update_gui()
    root.mainloop()

if __name__ == "__main__":
    create_gui()