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

# from db_module import EnergyDataDB  # 取消注释使用真实数据库

# 全局设置
connected = False
data_queue = queue.Queue()
db_queue = queue.Queue()  # 数据库专用队列
# db = EnergyDataDB()

# 数据缓存（自动保留最近30个点，0.5秒1个=15秒历史，可根据需要调整maxlen）
v_list = deque(maxlen=30)
i_list = deque(maxlen=30)
p_list = deque(maxlen=30)
t_list = deque(maxlen=30)

temp_value = 0.0
humi_value = 0.0
last_plot_time = 0
# 核心调整：绘图间隔与数据频率完全同步（0.5秒）
DATA_INTERVAL = 0.5
PLOT_INTERVAL = DATA_INTERVAL

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

# Matplotlib线条对象（仅初始化一次）
line_v = None
line_i = None
line_p = None


# -------------------------- 数据库异步保存线程 --------------------------
def db_worker():
    """单独线程处理数据库保存，彻底不阻塞网络和GUI"""
    while True:
        try:
            v, i, p = db_queue.get(block=True)
            # db.save_energy(v, i, p)
            db_queue.task_done()
        except:
            time.sleep(0.1)
            continue


# 启动数据库线程（后台静默运行）
threading.Thread(target=db_worker, daemon=True).start()


# -------------------------- TCP服务器线程（全速接收不丢包） --------------------------
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

        # 全速接收数据，绝不阻塞，确保每个0.5秒的数据包都被完整接收
        while connected and client:
            data = client.recv(1024).decode('UTF-8', errors='ignore').strip()
            if not data:
                break
            print(f"收到数据：{data}")

            if "INA219 Data:" in data:
                try:
                    v_start = data.find("Bus Voltage:") + len("Bus Voltage:")
                    v_end = data.find("V", v_start)
                    voltage = float(data[v_start:v_end].strip())

                    i_start = data.find("Current:") + len("Current:")
                    i_end = data.find("mA", i_start)
                    current = float(data[i_start:i_end].strip())

                    p_start = data.find("Power_w:") + len("Power_w:")
                    p_end = data.find("mW", p_start)
                    power = float(data[p_start:p_end].strip())

                    # 立即放入GUI队列和数据库队列
                    data_queue.put((voltage, current, power))
                    db_queue.put((voltage, current, power))
                except Exception as e:
                    print(f"解析失败: {e}")
            if "DHT11 Data:" in data:
                try:
                    t_start = data.find("Temperature:") + len("Temperature:")
                    t_end = data.find("℃", t_start)
                    temp = float(data[t_start:t_end].strip())
                    global temp_value
                    temp_value = temp

                    h_start = data.find("Humidity:") + len("Humidity:")
                    h_end = data.find("%", h_start)
                    humi = float(data[h_start:h_end].strip())
                    global humi_value
                    humi_value = humi
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
            btn.config(text="启动WiFi")


# -------------------------- 业务功能函数 --------------------------
def start_server():
    global connected
    if not connected:
        connected = True
        btn.config(text="停止服务")
        threading.Thread(target=wifi_server, daemon=True).start()
    else:
        connected = False
        btn.config(text="启动WiFi")


def send_command(event=None):
    global client_conn
    if not connected or client_conn is None:
        messagebox.showwarning("警告", "请先启动WiFi！")
        return

    msg = entry.get().strip()
    if not msg:
        return

    try:
        client_conn.sendall((msg + "\r\n").encode('utf-8'))
        print(f"已发送指令：{msg}")
        entry.delete(0, tk.END)
    except Exception as e:
        messagebox.showerror("错误", f"发送失败：{e}\n连接可能已断开")

#RTC 同步
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
        messagebox.showwarning("警告", "请先启动WiFi！")
        return

    now = datetime.datetime.now()
    data_packet = bytes([
        ord('R'), ord('T'), ord('C'), 3,
        now.year - 2000, now.month, now.day,
        now.hour, now.minute, now.second
    ])
    crc_val = crc16_modbus(data_packet)
    send_data = data_packet + bytes([crc_val & 0xFF, (crc_val >> 8) & 0xFF])

    try:
        client_conn.sendall(send_data)
        messagebox.showinfo("成功", "RTC时间同步指令发送完成！")
    except Exception as e:
        messagebox.showerror("错误", f"发送失败：{e}")


def PW_TH():
    global client_conn
    if not connected or client_conn is None:
        messagebox.showwarning("警告", "请先启动WiFi！")
        return

    value = simpledialog.askinteger("输入参数", "请输入十进制参数（0 ~ 1000）：", minvalue=0, maxvalue=1000)
    if value is None:
        return

    low_byte = value & 0xFF
    high_byte = (value >> 8) & 0xFF
    data_packet = bytes([0x52, 0x54, 0x43, 0x01, low_byte, high_byte])
    crc_val = crc16_modbus(data_packet)
    send_data = data_packet + bytes([crc_val & 0xFF, (crc_val >> 8) & 0xFF])

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


def clear_db_btn_click():
    res = messagebox.askyesno("确认", "确定要清空所有历史数据吗？\n清空后不可恢复！")
    if res:
        # if db.clear_all_data():
        #     messagebox.showinfo("成功", "历史数据已全部清空！")
        # else:
        #     messagebox.showerror("失败", "清空数据库出错！")
        messagebox.showinfo("提示", "数据库操作已模拟")


def auto_scale_y(ax, data_list, type="voltage"):
    if not data_list:
        return
    if type == "voltage":
        ax.set_ylim(2.500, 3.500)
    elif type == "current":
        ax.set_ylim(-200.000, -50.000)
    elif type == "power":
        ax.set_ylim(80.000, 500.000)
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter('%.3f'))


# -------------------------- GUI刷新（数据与绘图1:1同步） --------------------------
def update_gui():
    global v_list, i_list, p_list, t_list, line_v, line_i, line_p, last_plot_time

    # 立即更新温湿度标签（无延迟）
    lbl_temp.config(text=f"温度：{temp_value:.1f} ℃")
    lbl_humi.config(text=f"湿度：{humi_value:.1f} %RH")

    if not connected:
        root.after(100, update_gui)  # 保持100ms快速检查连接状态
        return

    has_new_data = False
    while not data_queue.empty():
        v, i, p = data_queue.get_nowait()
        has_new_data = True

        lbl_v.config(text=f"电压：{v:.3f} V")
        lbl_i.config(text=f"电流：{i:.3f} mA")
        lbl_p.config(text=f"功率：{p:.3f} mW")

        # 添加到缓存（deque自动弹出最旧数据）
        v_list.append(v)
        i_list.append(i)
        p_list.append(p)
        t_list.append(datetime.strftime("%H:%M:%S.%f"))  # 显示毫秒，验证0.5秒间隔

    # 核心：只有当有新数据且达到绘图间隔时才绘图（与数据频率完全同步）
    current_time = time.time()
    if has_new_data and (current_time - last_plot_time >= PLOT_INTERVAL):
        last_plot_time = current_time

        # 仅更新线条数据，不重新创建整个图表（性能核心）
        line_v.set_ydata(list(v_list))
        line_v.set_xdata(list(range(len(v_list))))

        line_i.set_ydata(list(i_list))
        line_i.set_xdata(list(range(len(i_list))))

        line_p.set_ydata(list(p_list))
        line_p.set_xdata(list(range(len(p_list))))

        # 更新X轴刻度
        for idx, ax in enumerate([ax_v, ax_i, ax_p]):
            ax.relim()
            ax.autoscale_view(scalex=True, scaley=False)  # Y轴固定范围，X轴自动缩放

            if len(t_list) > 0:
                num = min(6, len(t_list))
                ids = np.linspace(0, len(t_list) - 1, num, dtype=int)
                ax.set_xticks(ids)
                ax.set_xticklabels([t_list[j] for j in ids], rotation=30, fontsize=8)

        # 增量重绘，只更新变化的区域（比全图重绘快10倍）
        canvas.draw_idle()

    root.after(100, update_gui)  # 保持100ms快速检查数据


# -------------------------- 窗口关闭 --------------------------
def on_closing():
    global connected
    connected = False
    if client:
        client.close()
    if server:
        server.close()
    root.quit()
    root.destroy()


# -------------------------- GUI创建 --------------------------
def create_gui():
    global root, btn, lbl_v, lbl_i, lbl_p, lbl_temp, lbl_humi, canvas, fig, ax_v, ax_i, ax_p, entry
    global line_v, line_i, line_p

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False

    root = tk.Tk()
    root.title("能耗监控系统")
    root.geometry("1100x650")
    root.protocol("WM_DELETE_WINDOW", on_closing)

    main_frame = tk.Frame(root, bg="#f5f6fa")
    main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # 控制面板
    control_frame = ttk.LabelFrame(main_frame, text="控制与交互")
    control_frame.pack(fill=tk.X, pady=5)

    btn = ttk.Button(control_frame, text="启动WiFi", command=start_server)
    btn.pack(side=tk.LEFT, padx=10, pady=10)

    btn_rtc = ttk.Button(control_frame, text="同步RTC时间", command=sync_rtc)
    btn_rtc.pack(side=tk.LEFT, padx=5, pady=10)

    btn_pw = ttk.Button(control_frame, text="发送PW参数", command=PW_TH)
    btn_pw.pack(side=tk.LEFT, padx=5, pady=10)

    btn_clear_db = ttk.Button(control_frame, text="清空历史数据", command=clear_db_btn_click)
    btn_clear_db.pack(side=tk.LEFT, padx=5, pady=10)

    ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=5)

    tk.Label(control_frame, text="指令:", bg="#f5f6fa").pack(side=tk.LEFT, padx=(10, 0))
    entry = ttk.Entry(control_frame, width=30)
    entry.pack(side=tk.LEFT, padx=5, pady=10)
    entry.bind('<Return>', send_command)
    btn_send = ttk.Button(control_frame, text="发送", command=send_command)
    btn_send.pack(side=tk.LEFT, padx=5, pady=10)

    # 温湿度显示
    temp_humi_frame = tk.Frame(control_frame, bg="#f5f6fa")
    temp_humi_frame.pack(side=tk.RIGHT, padx=20)
    lbl_temp = tk.Label(temp_humi_frame, text="温度：0.0 ℃", font=("微软雅黑", 14), fg="black")
    lbl_temp.pack(anchor="e")
    lbl_humi = tk.Label(temp_humi_frame, text="湿度：0.0 %RH", font=("微软雅黑", 14), fg="black")
    lbl_humi.pack(anchor="e")

    # 实时数据显示
    data_frame = ttk.LabelFrame(main_frame, text="实时数据")
    data_frame.pack(fill=tk.X, pady=5)
    inner = tk.Frame(data_frame)
    inner.pack(fill=tk.X, pady=10)
    lbl_v = tk.Label(inner, text="电压：0.000 V", font=("微软雅黑", 16), fg="#e74c3c")
    lbl_v.pack(side=tk.LEFT, expand=True)
    lbl_i = tk.Label(inner, text="电流：0.000 mA", font=("微软雅黑", 16), fg="#3498db")
    lbl_i.pack(side=tk.LEFT, expand=True)
    lbl_p = tk.Label(inner, text="功率：0.000 mW", font=("微软雅黑", 16), fg="#2ecc71")
    lbl_p.pack(side=tk.LEFT, expand=True)

    # 实时曲线
    plot_frame = ttk.LabelFrame(main_frame, text="实时曲线")
    plot_frame.pack(fill=tk.BOTH, expand=True, pady=5)
    fig = plt.Figure(figsize=(15, 4), dpi=100)

    # 初始化图表（仅执行一次）
    ax_v = fig.add_subplot(131)
    ax_i = fig.add_subplot(132)
    ax_p = fig.add_subplot(133)

    # 创建空线条并保存对象（后续仅更新数据）
    line_v, = ax_v.plot([], [], label="电压(V)", color="#e74c3c", marker=".", linewidth=2)
    line_i, = ax_i.plot([], [], label="电流(mA)", color="#3498db", marker=".", linewidth=2)
    line_p, = ax_p.plot([], [], label="功率(mW)", color="#2ecc71", marker=".", linewidth=2)

    # 图表初始化设置（仅执行一次）
    for idx, ax in enumerate([ax_v, ax_i, ax_p]):
        ax.set_title(["电压", "电流", "功率"][idx] + "实时曲线", fontsize=10)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, linestyle="--", alpha=0.5)
        types = ["voltage", "current", "power"]
        auto_scale_y(ax, [], types[idx])  # 初始化固定Y轴范围

    fig.tight_layout()  # 布局仅执行一次

    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    update_gui()
    root.mainloop()


if __name__ == "__main__":
    create_gui()