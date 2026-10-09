"""ai_panel.py —— 把大模型分析接进能耗监控系统的 Tkinter 界面。

设计原则
--------
* **独立文件，不改 swj.py 的原有逻辑**。你只需要在 `create_gui()` 里加一行按钮。
* **AI 调用一律放在后台线程**，结果通过 queue + `after()` 回主线程刷新 —— 
  Tkinter 不是线程安全的，直接在子线程里操作控件会导致界面随机崩溃。
* **下发到硬件的指令必须人工确认**：模型只产出「待确认指令包」，
  面板上点「发送到节点」会先弹确认框，确认后才调用你上位机原有的 socket 发送。
* API Key 只保存在内存里（本次运行有效），不写入磁盘。也可用环境变量 ENGY_LLM_API_KEY。

接入方式（在 swj.py 的 create_gui() 里 control_frame 那一段加一行）
----------------------------------------------------------------
    from ai_panel import open_ai_panel
    ttk.Button(control_frame, text="AI 分析",
               command=lambda: open_ai_panel(root)).pack(side="left", padx=5, pady=10)

默认会自动从 `__main__` 里找 `client_conn` / `connected`（swj.py 直接运行时可用）。
若你的变量名不同，可显式传入：

    open_ai_panel(root, send_bytes=my_send, is_connected=lambda: my_flag)
"""

import json
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

import data_layer as dl
from agent import EnergyAgent
from config import CLOUD_PRESETS, apply_preset, load_config
from prompts import ANOMALY_TEMPLATE, DAILY_REPORT_TEMPLATE

UI_FONT = ("微软雅黑", 10)
UI_FONT_BOLD = ("微软雅黑", 10, "bold")
UI_FONT_SMALL = ("微软雅黑", 9)

PROVIDER_LABELS = {
    "mock": "离线自测（不用 Key）",
    "zhipu": "智谱 GLM-4-Flash（免费）",
    "deepseek": "DeepSeek",
    "dashscope": "通义千问",
    "kimi": "Kimi",
    "siliconflow": "硅基流动",
    "openai": "OpenAI",
    "local": "本地 Ollama",
}

# 快速提问按钮：(显示名, 提问内容, 是否调用大模型)
QUICK_ACTIONS = [
    ("生成简报", DAILY_REPORT_TEMPLATE, True),
    ("异常归因", ANOMALY_TEMPLATE, True),
    ("读数自洽性", "请检查这批数据里 INA219 的读数自洽性，"
                   "说明功率是否等于电压×电流，并给出结论与建议。", True),
    ("本地快检（秒出，不调用模型）", "__LOCAL_CONSISTENCY__", False),
]


def _payload_to_bytes(payload_hex: str) -> bytes:
    return bytes.fromhex(str(payload_hex).replace(" ", "").strip())


class AIPanel(tk.Toplevel):
    def __init__(self, master, send_bytes=None, is_connected=None, config_path=None):
        super().__init__(master)
        self.title("AI 能耗分析助手")
        self.geometry("980x720")
        self.minsize(760, 560)

        self.send_bytes = send_bytes or self._default_send
        self.is_connected = is_connected or self._default_is_connected
        self.config_path = config_path

        self.cfg = None
        self.agent = None
        self.result_queue: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_result = None
        self.busy = False

        self._build_ui()
        self._load_config_into_ui()
        self.after(120, self._poll_queue)

    # ------------------------------------------------------------ 与上位机对接

    @staticmethod
    def _swj_module():
        return sys.modules.get("__main__")

    def _default_is_connected(self) -> bool:
        mod = self._swj_module()
        return bool(getattr(mod, "connected", False))

    def _default_send(self, payload_hex: str) -> None:
        """默认发送实现：复用上位机 swj.py 里已有的 socket 连接。"""
        mod = self._swj_module()
        conn = getattr(mod, "client_conn", None)
        if not getattr(mod, "connected", False) or conn is None:
            raise RuntimeError("上位机未连接到节点。请先点主界面的「启动透传」并等 ESP8266 连上。")
        conn.sendall(_payload_to_bytes(payload_hex))

    # ------------------------------------------------------------ 界面

    def _build_ui(self) -> None:
        pad = dict(padx=8, pady=5)

        top = ttk.LabelFrame(self, text="模型设置")
        top.pack(fill="x", **pad)

        ttk.Label(top, text="服务商:").pack(side="left", padx=(10, 4), pady=8)
        self.provider_var = tk.StringVar(value="mock")
        self.provider_box = ttk.Combobox(
            top, state="readonly", width=28, textvariable=self.provider_var,
            values=[f"{k} — {v}" for k, v in PROVIDER_LABELS.items()],
        )
        self.provider_box.pack(side="left", pady=8)
        self.provider_box.bind("<<ComboboxSelected>>", lambda e: self._on_provider_change())

        ttk.Label(top, text="API Key:").pack(side="left", padx=(14, 4), pady=8)
        self.key_var = tk.StringVar()
        self.key_entry = ttk.Entry(top, textvariable=self.key_var, width=34, show="*")
        self.key_entry.pack(side="left", pady=8)

        ttk.Label(top, text="（仅存内存，不写盘）", font=UI_FONT_SMALL,
                  foreground="#888780").pack(side="left", padx=6)

        ask = ttk.LabelFrame(self, text="提问")
        ask.pack(fill="x", **pad)

        self.question_var = tk.StringVar()
        self.question_entry = ttk.Entry(ask, textvariable=self.question_var)
        self.question_entry.pack(side="left", fill="x", expand=True, padx=(10, 6), pady=8)
        self.question_entry.bind("<Return>", lambda e: self._on_ask())

        self.ask_btn = ttk.Button(ask, text="提问", command=self._on_ask)
        self.ask_btn.pack(side="left", padx=(0, 10), pady=8)

        quick = ttk.Frame(self)
        quick.pack(fill="x", padx=8)
        self.quick_btns = []
        for label, payload, use_llm in QUICK_ACTIONS:
            b = ttk.Button(quick, text=label,
                           command=lambda p=payload: self._on_quick(p))
            b.pack(side="left", padx=(0, 6), pady=(0, 6))
            self.quick_btns.append(b)

        self.save_btn = ttk.Button(quick, text="保存报告", command=self._on_save)
        self.save_btn.pack(side="right", padx=(6, 0), pady=(0, 6))

        mid = ttk.LabelFrame(self, text="分析结果")
        mid.pack(fill="both", expand=True, **pad)

        self.text = scrolledtext.ScrolledText(
            mid, wrap="word", font=UI_FONT, state="disabled",
            background="#ffffff", relief="flat",
        )
        self.text.pack(fill="both", expand=True, padx=6, pady=6)
        self.text.tag_configure("h", font=UI_FONT_BOLD, spacing1=8, spacing3=4)
        self.text.tag_configure("body", font=UI_FONT, lmargin1=6, lmargin2=16)
        self.text.tag_configure("muted", font=UI_FONT_SMALL, foreground="#5F5E5A",
                                lmargin1=6, lmargin2=16)
        self.text.tag_configure("warn", font=UI_FONT_BOLD, foreground="#A32D2D")

        self.pending_frame = ttk.LabelFrame(self, text="待确认指令（不会自动下发）")
        # 有指令时才 pack 出来

        self.status_var = tk.StringVar(value="就绪。默认离线自测模式，不会产生任何费用。")
        ttk.Label(self, textvariable=self.status_var, font=UI_FONT_SMALL,
                  foreground="#5F5E5A", anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    # ------------------------------------------------------------ 配置

    def _load_config_into_ui(self) -> None:
        try:
            self.cfg = load_config(self.config_path)
        except Exception as e:
            self.status_var.set(f"配置读取失败：{e}")
            return
        try:
            self.provider_box.current(
                [k for k in PROVIDER_LABELS].index("mock")
            )
        except ValueError:
            pass
        env_key = os.environ.get("ENGY_LLM_API_KEY", "")
        if env_key:
            self.key_var.set(env_key)
            self.status_var.set("已从环境变量 ENGY_LLM_API_KEY 读取 Key。")
        self._on_provider_change()

    def _current_provider(self) -> str:
        return self.provider_box.get().split(" — ")[0]

    def _on_provider_change(self):
        provider = self._current_provider()
        need_key = provider not in ("mock", "local")
        self.key_entry.configure(state="normal" if need_key else "disabled")
        if provider == "mock":
            self.status_var.set("离线自测模式：不需要 Key、不联网，用于验证界面与链路。")
        elif provider == "local":
            self.status_var.set("本地 Ollama 模式：请确认已 `ollama serve` 且已拉取模型。")
        else:
            preset = CLOUD_PRESETS.get(provider, {})
            self.status_var.set(
                f"{PROVIDER_LABELS.get(provider, provider)}　模型 {preset.get('model', '?')}"
                f"　{preset.get('note', '')}"
            )

    def _build_agent(self, provider: str, api_key: str) -> EnergyAgent:
        """按指定服务商构造 Agent。

        注意：provider / api_key 必须由主线程读出后传进来，
        不能在后台线程里访问 Tk 变量（Tk 不是线程安全的）。
        """
        cfg = self.cfg or load_config(self.config_path)
        cfg = json.loads(json.dumps(cfg))  # 深拷贝，避免多次运行相互污染

        if provider in ("mock", "local"):
            cfg["provider"] = provider
        else:
            apply_preset(cfg, provider)
            if not api_key:
                raise RuntimeError(
                    f"使用 {PROVIDER_LABELS[provider]} 需要 API Key。\n"
                    "请在面板上方填入，或先设置环境变量 ENGY_LLM_API_KEY。"
                )
            cfg["cloud"]["api_key"] = api_key

        self.agent = EnergyAgent(cfg)
        return self.agent

    # ------------------------------------------------------------ 交互

    def _set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.ask_btn.configure(state=state)
        for b in self.quick_btns:
            b.configure(state=state)

    def _on_ask(self):
        q = self.question_var.get().strip()
        if not q:
            messagebox.showinfo("提示", "请先输入问题。", parent=self)
            return
        self._start(q)

    def _on_quick(self, payload):
        if payload == "__LOCAL_CONSISTENCY__":
            self._local_consistency()
            return
        self._start(payload)

    # ------------------------------------------------------------ 本地快检（不调用模型）

    def _local_consistency(self):
        """直接调用数据层做自洽性检查，秒出、零成本。"""
        self._write_clear("正在本地检查读数自洽性…")
        try:
            if not self.cfg or not self.cfg.get("db_path"):
                raise RuntimeError(
                    "配置里缺少 db_path，无法定位数据库。\n"
                    "请检查 config.json（应与 ai_panel.py 在同一目录）。"
                )
            records, _ = dl.load_records(self.cfg["db_path"])
            info = dl.detect_inconsistent_readings(records)
        except Exception as e:
            self._write_error(f"本地检查失败：{e}")
            return

        if info.get("inconsistent") is None:
            self._write_error(str(info))
            return

        lines = [
            ("h", "【本地快检】INA219 读数自洽性"),
            ("muted", "判据：功率寄存器应等于 电压 × 电流，容差 "
                      f"{info.get('tolerance_mw')} mW。此结果由本地 Python 直接算出，未调用大模型。"),
            ("body", f"检查 {info['checked']} 行，发现 {info['inconsistent']} 行不自洽"
                     f"（{info['inconsistent_pct']}%）。"),
            ("body", f"· 功率寄存器偏高、电流正常：{info['mode_power_high']['count']} 行"),
            ("body", f"· 电流寄存器偏高、功率正常：{info['mode_current_high']['count']} 行"),
            ("h", "偏差最大的几条"),
        ]
        for r in (info["mode_power_high"]["examples"][:3] +
                  info["mode_current_high"]["examples"][:3]):
            lines.append((
                "body",
                f"{r['time']}　V={r['voltage']} × I={r['current_ma']} mA = {r['vi_mw']} mW，"
                f"但功率寄存器记 {r['power_mw']} mW（偏差 {r['deviation_mw']} mW）",
            ))
        lines.append(("warn", info.get("interpretation", "")))
        self._write(lines)
        self.status_var.set(f"本地快检完成（未调用模型，无费用）。{info['inconsistent_pct']}% 的行不自洽。")
        self.last_result = {"result": {"answer": "（本地快检结果见上）", "evidence": [], "suggestions": [],
                                       "confidence": "high", "data_limitations": []},
                            "raw_content": json.dumps(info, ensure_ascii=False, indent=2),
                            "pending_commands": [], "trace": [], "model": "local(无模型)"}

    # ------------------------------------------------------------ 调用大模型

    def _start(self, question: str):
        if self.busy:
            return
        # 在主线程里读出 Tk 变量的值，再交给后台线程使用
        provider = self._current_provider()
        api_key = self.key_var.get().strip() if provider not in ("mock", "local") else ""

        self._set_busy(True)
        self._write_clear("正在分析…（后台线程调用，界面不会卡）")
        self.status_var.set("请求已发出，等待模型与工具返回…")
        self.worker = threading.Thread(
            target=self._worker, args=(question, provider, api_key), daemon=True
        )
        self.worker.start()

    def _worker(self, question: str, provider: str, api_key: str):
        """后台线程：只做计算与网络请求，绝不触碰任何 Tk 控件。"""
        try:
            agent = self._build_agent(provider, api_key)
            res = agent.ask(question)
            self.result_queue.put(("ok", res))
        except Exception as e:
            self.result_queue.put(("error", f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                self._set_busy(False)
                if kind == "ok":
                    self._render(payload)
                else:
                    self._write_error(payload)
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    # ------------------------------------------------------------ 渲染

    def _write_clear(self, text: str = ""):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if text:
            self.text.insert("end", text + "\n", "body")
        self.text.configure(state="disabled")

    def _write_error(self, msg: str):
        self._write_clear()
        self.text.configure(state="normal")
        self.text.insert("end", "分析失败\n", "warn")
        self.text.insert("end", msg + "\n", "body")
        self.text.configure(state="disabled")
        self.status_var.set("失败，请检查上面的错误信息。")

    def _write(self, blocks):
        self.text.configure(state="normal")
        for tag, content in blocks:
            self.text.insert("end", (content or "") + "\n", tag)
        self.text.configure(state="disabled")
        self.text.see("end")

    def _render(self, res: dict):
        self.last_result = res
        r = res.get("result") or {}

        blocks = [
            ("h", f"结论　（模型 {res.get('model', '?')}，共 {res.get('llm_calls', 0)} 次调用）"),
            ("body", str(r.get("answer", "")).strip()),
        ]

        if res.get("trace"):
            blocks.append(("h", "工具调用过程"))
            for t in res["trace"]:
                mark = "校验重试" if t["round"] == "json_retry" else f"第{t['round']}轮"
                if t["tool"]:
                    blocks.append(("muted",
                                   f"{mark}　{t['tool']}({json.dumps(t['arguments'], ensure_ascii=False)})"))
                else:
                    blocks.append(("muted", f"{mark}　{t['result_preview']}"))

        if r.get("evidence"):
            blocks.append(("h", "证据（均来自工具返回）"))
            blocks.extend(("body", f"· {e}") for e in r["evidence"])

        if r.get("suggestions"):
            blocks.append(("h", "建议"))
            blocks.extend(("body", f"· {s}") for s in r["suggestions"])

        blocks.append(("h", f"置信度　{r.get('confidence', '未给出')}"))

        if r.get("data_limitations"):
            blocks.append(("h", "数据局限"))
            blocks.extend(("muted", f"· {l}") for l in r["data_limitations"])

        self._write(blocks)
        self.status_var.set("分析完成。" + (
            f"有 {len(res['pending_commands'])} 条待确认指令。" if res.get("pending_commands") else ""
        ))

        self._render_pending(res.get("pending_commands") or [])

    def _render_pending(self, pending: list):
        for child in self.pending_frame.winfo_children():
            child.destroy()

        if not pending:
            self.pending_frame.pack_forget()
            return

        self.pending_frame.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(
            self.pending_frame,
            text="⚠ 以下指令【尚未发送】。点「发送到节点」会再次确认，确认后才通过上位机下发。",
            font=UI_FONT_BOLD, foreground="#A32D2D",
        ).pack(anchor="w", padx=10, pady=(8, 2))

        for i, p in enumerate(pending):
            row = ttk.Frame(self.pending_frame)
            row.pack(fill="x", padx=10, pady=3)

            ttk.Label(row, text=p.get("human_readable", ""), font=UI_FONT).pack(side="left")
            ttk.Label(row, text=f"　数据包 {p.get('payload_hex')}", font=UI_FONT_SMALL,
                      foreground="#5F5E5A").pack(side="left")

            ttk.Button(row, text="发送到节点",
                       command=lambda pp=p: self._confirm_send(pp)).pack(side="right", padx=4)
            ttk.Button(row, text="复制数据包",
                       command=lambda pp=p: self._copy(pp.get("payload_hex", ""))).pack(side="right", padx=4)

    def _copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set(f"已复制：{text}")

    def _confirm_send(self, cmd: dict):
        ok = messagebox.askyesno(
            "确认下发指令",
            f"即将向节点下发：\n\n{cmd.get('human_readable')}\n"
            f"数据包：{cmd.get('payload_hex')}\n\n"
            f"风险：{cmd.get('warning', '')}\n\n确定发送吗？",
            parent=self, icon="warning",
        )
        if not ok:
            self.status_var.set("已取消发送。")
            return
        try:
            self.send_bytes(cmd.get("payload_hex", ""))
            self.status_var.set(f"已发送：{cmd.get('human_readable')}")
            messagebox.showinfo("已发送", f"{cmd.get('human_readable')}\n已下发。", parent=self)
        except Exception as e:
            messagebox.showerror("发送失败", str(e), parent=self)
            self.status_var.set(f"发送失败：{e}")

    # ------------------------------------------------------------ 保存

    def _on_save(self):
        if not self.last_result:
            messagebox.showinfo("提示", "还没有分析结果可保存。", parent=self)
            return
        from tkinter import filedialog
        default = f"ai_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".md", initialfile=default,
            filetypes=[("Markdown", "*.md"), ("文本", "*.txt"), ("全部", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text.get("1.0", "end"))
            self.status_var.set(f"已保存到 {path}")
        except OSError as e:
            messagebox.showerror("保存失败", str(e), parent=self)
            self.status_var.set(f"保存失败：{e}")


def open_ai_panel(master, send_bytes=None, is_connected=None, config_path=None) -> AIPanel:
    """打开 AI 分析面板（单例：已打开则置顶）。"""
    existing = getattr(open_ai_panel, "_instance", None)
    if existing is not None and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        existing.focus_force()
        return existing

    panel = AIPanel(master, send_bytes=send_bytes, is_connected=is_connected,
                    config_path=config_path)
    open_ai_panel._instance = panel
    return panel


if __name__ == "__main__":
    # 单独运行本文件可先看界面效果（不会连节点，发送按钮会提示未连接）
    root = tk.Tk()
    root.title("独立预览")
    root.geometry("600x300")
    ttk.Button(root, text="打开 AI 分析面板",
               command=lambda: open_ai_panel(root)).pack(pady=40)
    ttk.Label(root, text="这是独立预览窗口。实际使用时请从 swj.py 里打开。").pack()
    root.mainloop()
