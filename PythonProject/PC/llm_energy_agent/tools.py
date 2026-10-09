"""工具层（Function Calling）—— 大模型唯一能"动手"的地方。

安全设计（务必读）：
    1) 所有数据库访问走【只读】连接，且 SQL 只允许单条 SELECT。
    2) 涉及下发到硬件的操作（改阈值 / 睡眠 / 唤醒 / 同步 RTC），本层
        **只生成待确认指令包，绝不直接发送**。真正的发送必须由人在
        GUI 上确认后触发，避免模型幻觉直接改设备状态。
    3) CRC16 与数据包格式完全复用用户上位机 swj.py 的实现，不重写协议。

数据包格式（与 swj.py 一致，head = 'R''T''C' = 52 54 43）：
    同步 RTC : 52 54 43 03  yy mm dd hh mi ss + CRC16(低,高)
    设置阈值 : 52 54 43 01  low high            + CRC16(低,高)   仅低10位有效(0~1000)
    睡眠     : 52 54 43 02  00                 + CRC16(低,高)
    唤醒     : 52 54 43 02  AA                 + CRC16(低,高)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import data_layer as dl

HEADER = (0x52, 0x54, 0x43)  # "RTC"

FORBIDDEN_SQL = (
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "attach", "detach", "pragma", "vacuum", "reindex", "trigger", "grant",
)


# ---------------------------------------------------------------- 协议（复用用户实现）


def crc16_modbus(data: bytes) -> int:
    """与上位机 swj.py 完全一致的 Modbus CRC16。"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def _pack(payload: bytes) -> str:
    crc = crc16_modbus(payload)
    full = payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    return full.hex(" ").upper()


def build_sync_rtc(when: datetime | None = None) -> str:
    when = when or datetime.now()
    payload = bytes(
        [*HEADER, 0x03, when.year - 2000, when.month, when.day,
         when.hour, when.minute, when.second]
    )
    return _pack(payload)


def build_threshold(value: int) -> str:
    if not 0 <= value <= 1000:
        raise ValueError("阈值必须是 0~1000 的十进制整数（与上位机 PW_TH 输入范围一致）")
    payload = bytes([*HEADER, 0x01, value & 0xFF, (value >> 8) & 0xFF])
    return _pack(payload)


def build_sleep() -> str:
    return _pack(bytes([*HEADER, 0x02, 0x00]))


def build_wake() -> str:
    return _pack(bytes([*HEADER, 0x02, 0xAA]))


# ---------------------------------------------------------------- SQL 安全


def run_readonly_sql(db_path: str, sql: str, max_rows: int = 500) -> dict:
    """执行只读 SELECT。三重防护：语句白名单 + 强制 LIMIT + 连接只读。"""
    raw = (sql or "").strip().rstrip(";")
    if not raw:
        return {"error": "SQL 为空"}
    if ";" in raw:
        return {"error": "只允许单条语句（检测到分号）"}

    lowered = raw.lower()
    if not lowered.startswith(("select", "with")):
        return {"error": "只允许 SELECT 查询"}
    for word in FORBIDDEN_SQL:
        if word in lowered:
            return {"error": f"SQL 含被禁止的关键字: {word}"}
    if "sqlite_master" in lowered or "sqlite_sequence" in lowered:
        return {"error": "不允许访问系统表"}
    if "energy_record" not in lowered:
        return {"error": "只允许查询 energy_record 表"}

    if "limit" not in lowered:
        raw = f"{raw} LIMIT {int(max_rows)}"

    posix = Path(db_path).as_posix()
    try:
        with sqlite3.connect(f"file:{posix}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(raw)
            rows = [dict(r) for r in cur.fetchall()]
    except sqlite3.Error as e:
        return {"error": f"SQL 执行失败: {e}"}

    return {
        "sql": raw,
        "row_count": len(rows),
        "truncated": len(rows) >= max_rows,
        "rows": rows,
    }


# ---------------------------------------------------------------- 工具实现


def tool_get_summary(db_path: str, start: str | None = None, end: str | None = None) -> dict:
    """取某个时间范围的结构化摘要（最常用，优先调它）。"""
    records, quality = dl.load_records(db_path, start=start, end=end)
    summary = dl.summarize(records, quality)
    return {
        "summary_text": dl.format_summary(summary),
        "raw": summary,
    }


def tool_calc_stats(db_path: str, metric: str, start: str, end: str) -> dict:
    """精确统计（真正的算术在这里，不要让模型自己算）。"""
    return dl.calc_stats(db_path, metric, start, end)


def tool_list_periods(db_path: str) -> dict:
    """列出有哪些采集时段，便于模型先确认时间范围再分析。"""
    records, _ = dl.load_records(db_path)
    clusters = dl._cluster(records)
    return {
        "periods": [
            {
                "start": c[0]["time_str"],
                "end": c[-1]["time_str"],
                "samples": len(c),
            }
            for c in clusters
        ],
        "note": "数据仅在以上时段内存在，时段之间有断档，不可跨时段做「连续时长」推断。",
    }


def tool_check_consistency(db_path: str, start: str | None = None, end: str | None = None) -> dict:
    """检查 INA219 读数自洽性（功率是否等于电压×电流）。

    当用户问「峰值/异常是否可信」「测量准不准」时必须调用。
    """
    records, _ = dl.load_records(db_path, start=start, end=end)
    if not records:
        return {"error": "该时间范围内没有有效数据"}
    return dl.detect_inconsistent_readings(records)


def tool_propose_threshold(value: int) -> dict:
    """生成待确认的阈值指令（不发送）。"""
    packet = build_threshold(value)
    text = f"{value} mW" if value else f"{value}（原始十进制，0~1000）"
    return {
        "status": "待人工确认",
        "action": "set_power_threshold",
        "value": value,
        "payload_hex": packet,
        "human_readable": f"把下位机功率报警阈值改为 {text}",
        "warning": "该指令会改变硬件报警行为，必须由人工确认后发送。",
    }


def tool_propose_sleep() -> dict:
    return {
        "status": "待人工确认",
        "action": "node_sleep",
        "payload_hex": build_sleep(),
        "human_readable": "让被测无线节点进入睡眠",
        "warning": "会让节点停止正常通信，必须由人工确认后发送。",
    }


def tool_propose_wake() -> dict:
    return {
        "status": "待人工确认",
        "action": "node_wake",
        "payload_hex": build_wake(),
        "human_readable": "唤醒被测无线节点",
        "warning": "会恢复节点通信，必须由人工确认后发送。",
    }


def tool_propose_sync_rtc() -> dict:
    now = datetime.now()
    return {
        "status": "待人工确认",
        "action": "sync_rtc",
        "payload_hex": build_sync_rtc(now),
        "human_readable": f"把下位机 RTC 同步为 {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "warning": "会修改下位机时间，必须由人工确认后发送。",
    }


# ---------------------------------------------------------------- 工具注册表

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_summary",
            "description": (
                "获取指定时间范围内能耗数据的结构化摘要（统计特征、状态分布、超限事件）。"
                "这是最常用的工具，回答任何关于数据的问题前都应先调用它。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "起始时间，格式 YYYY-MM-DD HH:MM:SS，可省略表示不限"},
                    "end": {"type": "string", "description": "结束时间，格式 YYYY-MM-DD HH:MM:SS，可省略表示不限"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_stats",
            "description": "对指定范围内的电压/电流/功率做精确统计与能耗积分。数值计算一律用本工具，不要自己估算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": ["voltage", "current", "power"]},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["metric", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_periods",
            "description": "列出数据库中存在数据的采集时段。当不确定数据分布时必须先调用，避免跨断档做错误推断。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_reading_consistency",
            "description": (
                "检查 INA219 读数自洽性：功率寄存器是否等于 电压×电流。"
                "当用户询问功率峰值/异常是否可信、测量精度、数据质量时，必须调用本工具，"
                "以区分「真实功耗突变」与「寄存器非同时读取造成的读数错配」。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "起始时间 YYYY-MM-DD HH:MM:SS，可省略"},
                    "end": {"type": "string", "description": "结束时间 YYYY-MM-DD HH:MM:SS，可省略"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_energy_db",
            "description": "对 energy_record 表执行只读 SELECT 查询，用于获取原始明细行。仅允许单条 SELECT。",
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string", "description": "一条 SELECT 语句"}},
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_set_threshold",
            "description": (
                "生成「修改功率报警阈值」的待确认指令，不会真正下发。"
                "仅当用户明确要求调整阈值时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "integer", "description": "阈值，0~1000 的十进制整数"}
                },
                "required": ["value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_node_sleep",
            "description": "生成「让节点睡眠」的待确认指令，不会真正下发。仅当用户明确要求时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_node_wake",
            "description": "生成「唤醒节点」的待确认指令，不会真正下发。仅当用户明确要求时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_sync_rtc",
            "description": "生成「同步下位机 RTC 时间」的待确认指令，不会真正下发。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


class ToolRunner:
    """把模型发来的工具名+参数，分发到上面的实现。"""

    def __init__(self, db_path: str, max_sql_rows: int = 500):
        self.db_path = db_path
        self.max_sql_rows = max_sql_rows
        # 本次会话中模型生成的待确认指令
        self.pending: list[dict] = []

    def dispatch(self, name: str, args: dict) -> str:
        """执行工具并返回 JSON 字符串（作为 tool 消息回给模型）。"""
        args = args or {}
        try:
            if name == "get_summary":
                result = tool_get_summary(self.db_path, args.get("start"), args.get("end"))
            elif name == "calc_stats":
                result = tool_calc_stats(
                    self.db_path,
                    args.get("metric", "power"),
                    args.get("start"),
                    args.get("end"),
                )
            elif name == "list_periods":
                result = tool_list_periods(self.db_path)
            elif name == "check_reading_consistency":
                result = tool_check_consistency(
                    self.db_path, args.get("start"), args.get("end")
                )
            elif name == "query_energy_db":
                result = run_readonly_sql(self.db_path, args.get("sql", ""), self.max_sql_rows)
            elif name == "propose_set_threshold":
                result = tool_propose_threshold(int(args.get("value")))
                self.pending.append(result)
            elif name == "propose_node_sleep":
                result = tool_propose_sleep()
                self.pending.append(result)
            elif name == "propose_node_wake":
                result = tool_propose_wake()
                self.pending.append(result)
            elif name == "propose_sync_rtc":
                result = tool_propose_sync_rtc()
                self.pending.append(result)
            else:
                result = {"error": f"未知工具 {name}"}
        except Exception as e:  # 工具报错也要回给模型，让它自己纠正
            result = {"error": f"{type(e).__name__}: {e}"}

        return json.dumps(result, ensure_ascii=False, default=str)
