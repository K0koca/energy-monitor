"""数据摘要层 —— 所有数值计算都在这里完成。

设计原则（重要）：
    算术归 Python，语义归大模型。
    原始时序数据（240 条 × 秒级）绝不直接塞进模型上下文，
    这里先聚合出「统计特征 + 状态分布 + 异常事件」，产出几百 token 的摘要。

针对本项目真实数据的三个坑，在此统一处理：
    1) 电流原始值为负（INA219 分流方向导致），统一取绝对值，对外只谈 |I|。
    2) 存在 voltage≈0.4V / current=0 / power=0 的无效采样（掉线或上电瞬间），
       按 MIN_VALID_VOLTAGE_V 过滤，并单独统计丢弃条数。
    3) 温湿度没有入库（上位机只放在全局变量里），本层不提供，切勿编造。

数据库以【只读】方式打开，绝不写入用户工程目录。
"""

import sqlite3
import statistics
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- 常量与口径

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# 低于此电压视为无效采样（正常节点供电 3.2~3.3V）
MIN_VALID_VOLTAGE_V = 1.0

# 采样间隔上限：超过此值的相邻点视为离线断档，不计入能耗积分
MAX_GAP_S = 60

# 聚类间隔：相邻点间隔超过此值，判为两个独立的采集时段（session）
CLUSTER_GAP_S = 600

# 读数自洽性容差：INA219 满足 P = V×I，偏差超过此值即判为不自洽（疑似寄存器非同时读取）
CONSISTENCY_TOLERANCE_MW = 5.0

PHYSICAL = {
    "voltage": {"unit": "V", "desc": "节点供电电压"},
    "current": {"unit": "mA", "desc": "负载电流，本模块统一取绝对值"},
    "power": {"unit": "mW", "desc": "功率，恒为正"},
}

# 基线口径：来自论文 5.4 节实测（ESP-01S @ 3.3V / 25℃）
BASELINE = {
    "node": "ESP-01S",
    "nominal_voltage_v": 3.3,
    "comm_current_ma": (68.0, 73.0),      # 通信态稳定后实测区间
    "comm_power_mw": (220.0, 235.0),      # 通信态稳定后实测区间
    "sleep_current_ma": 9.9,              # 睡眠态实测
    "sleep_power_mw": 32.0,               # 睡眠态实测
    "datasheet_current_ma": (50.0, 170.0),  # 数据手册典型值
}

# 状态判定阈值（按 |I| 划分）
COMM_THRESHOLD_MA = 50.0
SLEEP_THRESHOLD_MA = 15.0


def classify_state(current_abs_ma: float) -> str:
    if current_abs_ma >= COMM_THRESHOLD_MA:
        return "通信态"
    if current_abs_ma <= SLEEP_THRESHOLD_MA:
        return "睡眠态"
    return "过渡态"


# ---------------------------------------------------------------- 读取与清洗


def _connect_ro(db_path: str) -> sqlite3.Connection:
    """以只读方式打开 SQLite，保证不修改用户工程里的数据文件。"""
    posix = Path(db_path).as_posix()
    uri = f"file:{posix}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def load_records(db_path: str, start: str | None = None, end: str | None = None):
    """读取并清洗数据。

    返回 (records, quality)。
    records 为按时间升序的 dict 列表，字段：
        time(datetime) / time_str / voltage / current_ma(绝对值) / power_mw / state
    quality 为数据质量统计，用于向模型说明"有多少脏数据被剔除"。
    """
    quality = {
        "rows_raw": 0,
        "dropped_invalid_voltage": 0,
        "dropped_bad_time": 0,
        "rows_used": 0,
    }
    records: list[dict] = []
    with _connect_ro(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT record_time, voltage, current, power FROM energy_record ORDER BY record_time"
        )
        rows = cur.fetchall()

    quality["rows_raw"] = len(rows)

    for t_str, voltage, current, power in rows:
        if t_str is None or voltage is None or current is None or power is None:
            quality["dropped_bad_time"] += 1
            continue
        try:
            t = datetime.strptime(str(t_str).strip(), TIME_FMT)
        except ValueError:
            quality["dropped_bad_time"] += 1
            continue

        if start is not None and t < datetime.strptime(start, TIME_FMT):
            continue
        if end is not None and t > datetime.strptime(end, TIME_FMT):
            continue

        if float(voltage) < MIN_VALID_VOLTAGE_V:
            quality["dropped_invalid_voltage"] += 1
            continue

        cur_abs = abs(float(current))
        v = float(voltage)
        p = float(power)
        vi_mw = v * cur_abs
        records.append(
            {
                "time": t,
                "time_str": t.strftime(TIME_FMT),
                "voltage": v,
                "current_ma": cur_abs,
                "power_mw": p,
                "state": classify_state(cur_abs),
                # INA219 应满足 P = V×I；偏差过大说明电流与功率寄存器不是同一转换窗口
                "vi_mw": round(vi_mw, 3),
                "power_dev_mw": round(abs(vi_mw - p), 3),
                "consistent": abs(vi_mw - p) <= CONSISTENCY_TOLERANCE_MW,
            }
        )

    records.sort(key=lambda r: r["time"])
    quality["rows_used"] = len(records)
    quality["sampling_interval_s"] = _median_interval_s(records)

    # 读数自洽性：统计 |V×I| 与功率寄存器偏差过大的行
    inconsistent = [r for r in records if not r["consistent"]]
    quality["inconsistent_readings"] = len(inconsistent)
    quality["inconsistent_pct"] = (
        round(100.0 * len(inconsistent) / len(records), 1) if records else 0.0
    )
    if inconsistent:
        worst = max(inconsistent, key=lambda r: r["power_dev_mw"])
        quality["worst_inconsistency"] = {
            "time": worst["time_str"],
            "voltage": worst["voltage"],
            "current_ma": worst["current_ma"],
            "power_mw": worst["power_mw"],
            "vi_mw": worst["vi_mw"],
            "deviation_mw": worst["power_dev_mw"],
        }
    return records, quality


def _median_interval_s(records: list[dict]) -> float | None:
    if len(records) < 2:
        return None
    diffs = [
        (records[i + 1]["time"] - records[i]["time"]).total_seconds()
        for i in range(len(records) - 1)
    ]
    diffs = [d for d in diffs if d > 0]
    return round(statistics.median(diffs), 1) if diffs else None


def _cluster(records: list[dict], gap_s: int = CLUSTER_GAP_S) -> list[list[dict]]:
    """按时间间隔把记录切成若干采集时段。

    本项目数据只集中在几天（05-22 / 06-02 / 06-08），不是连续采集。
    如果不做这层切分，模型会把「时间跨度 16 天」误当成「连续采集 16 天」。
    """
    if not records:
        return []
    clusters = [[records[0]]]
    for prev, cur in zip(records, records[1:]):
        if (cur["time"] - prev["time"]).total_seconds() > gap_s:
            clusters.append([])
        clusters[-1].append(cur)
    return clusters


def _coverage(records: list[dict]) -> tuple[float, float]:
    """返回 (实际覆盖时长分钟, 覆盖率%)。

    覆盖时长只累计相邻间隔 <= MAX_GAP_S 的部分，反映「真正有数据」的时长。
    """
    if len(records) < 2:
        return 0.0, 0.0
    span = (records[-1]["time"] - records[0]["time"]).total_seconds()
    covered = sum(
        dt
        for prev, cur in zip(records, records[1:])
        if 0 < (dt := (cur["time"] - prev["time"]).total_seconds()) <= MAX_GAP_S
    )
    return round(covered / 60.0, 2), round(100.0 * covered / span, 1) if span > 0 else 0.0


# ---------------------------------------------------------------- 统计工具


def _pct(values: list[float], q: float) -> float | None:
    """简单百分位（线性插值），避免引入 numpy 依赖。"""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 3)
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return round(s[lo] + (s[hi] - s[lo]) * frac, 3)


def _metric_stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "std": round(statistics.pstdev(values), 3) if len(values) > 1 else 0.0,
        "p95": _pct(values, 0.95),
    }


def integrate_energy_mwh(records: list[dict]) -> float:
    """按梯形法积分估算总能耗（mWh）。断档超过 MAX_GAP_S 的区间不计入。"""
    if len(records) < 2:
        return 0.0
    total = 0.0
    for a, b in zip(records, records[1:]):
        dt = (b["time"] - a["time"]).total_seconds()
        if dt <= 0 or dt > MAX_GAP_S:
            continue
        total += 0.5 * (a["power_mw"] + b["power_mw"]) * dt / 3600.0
    return round(total, 4)


def detect_events(records: list[dict], threshold_mw: float | None = None) -> list[dict]:
    """找出功率超过基线上限的连续时段（超限事件）。"""
    if threshold_mw is None:
        threshold_mw = BASELINE["comm_power_mw"][1]

    events: list[dict] = []
    current: list[dict] = []
    for r in records:
        if r["power_mw"] > threshold_mw:
            current.append(r)
        elif current:
            events.append(_pack_event(current, threshold_mw))
            current = []
    if current:
        events.append(_pack_event(current, threshold_mw))

    events.sort(key=lambda e: e["max_power_mw"], reverse=True)
    return events


def _pack_event(group: list[dict], threshold_mw: float) -> dict:
    powers = [r["power_mw"] for r in group]
    return {
        "start": group[0]["time_str"],
        "end": group[-1]["time_str"],
        "samples": len(group),
        "duration_min": round(
            (group[-1]["time"] - group[0]["time"]).total_seconds() / 60.0, 2
        ),
        "max_power_mw": round(max(powers), 3),
        "mean_power_mw": round(statistics.fmean(powers), 3),
        "threshold_mw": threshold_mw,
    }


def detect_inconsistent_readings(records: list[dict], top_n: int = 8) -> dict:
    """检查 INA219 读数自洽性：功率寄存器应等于 电压 × 电流。

    实测本项目 231 行中有 75 行（32.5%）不自洽，且存在两种失效模式：
        · 功率寄存器虚高而电流正常（如 404.8 mW vs V×I=237.2 mW）
        · 电流寄存器虚高而功率正常（如 111.4 mA vs 对应功率仅 229.1 mW）
    最可能的原因是固件依次读取各寄存器、而负载在快速跳变（ESP8266 射频突发），
    导致电流与功率落在不同的转换窗口。**这不是真实功耗突变**，
    因此在报告功率峰值/异常前必须先把这些点区分出来。
    """
    if not records:
        return {"checked": 0, "inconsistent": 0}

    bad = [r for r in records if not r["consistent"]]
    bad.sort(key=lambda r: r["power_dev_mw"], reverse=True)

    # 区分两种失效模式
    power_side = [r for r in bad if r["power_mw"] > r["vi_mw"]]
    current_side = [r for r in bad if r["power_mw"] <= r["vi_mw"]]

    def pack(rows):
        return [
            {
                "time": r["time_str"],
                "voltage": r["voltage"],
                "current_ma": r["current_ma"],
                "power_mw": r["power_mw"],
                "vi_mw": r["vi_mw"],
                "deviation_mw": r["power_dev_mw"],
            }
            for r in rows[:top_n]
        ]

    return {
        "checked": len(records),
        "inconsistent": len(bad),
        "inconsistent_pct": round(100.0 * len(bad) / len(records), 1),
        "tolerance_mw": CONSISTENCY_TOLERANCE_MW,
        "mode_power_high": {
            "count": len(power_side),
            "meaning": "功率寄存器偏高、电流正常（功率疑似虚高）",
            "examples": pack(power_side),
        },
        "mode_current_high": {
            "count": len(current_side),
            "meaning": "电流寄存器偏高、功率正常（电流疑似虚高）",
            "examples": pack(current_side),
        },
        "interpretation": (
            "两种模式同时存在，说明不是单纯的量程或校准错误，而更像寄存器非同时读取造成的"
            "瞬时错配。建议在固件中修正读取顺序或做原子读取后再复测；"
            "本分析在给出功率峰值结论时会明确标注这一不确定性。"
        ),
    }


def _state_breakdown(records: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for name in ("通信态", "睡眠态", "过渡态"):
        group = [r for r in records if r["state"] == name]
        if not group:
            continue
        out[name] = {
            "samples": len(group),
            "share_pct": round(100.0 * len(group) / len(records), 1),
            "mean_current_ma": round(statistics.fmean([r["current_ma"] for r in group]), 3),
            "mean_power_mw": round(statistics.fmean([r["power_mw"] for r in group]), 3),
            "max_power_mw": round(max(r["power_mw"] for r in group), 3),
        }
    return out


def _trend(records: list[dict]) -> dict | None:
    """前后半段对比 + 斜率。

    注意：本项目数据有大量断档，跨断档比较功率趋势没有物理意义，
    因此趋势只在「最长的单个采集时段」内计算，并显式说明范围。
    斜率按样本序号（而非墙钟时间）计算，避免断档把斜率算歪。
    """
    if len(records) < 8:
        return None

    clusters = _cluster(records)
    main = max(clusters, key=len) if clusters else records
    target = main if len(main) >= 8 else records

    half = len(target) // 2
    first = statistics.fmean([r["power_mw"] for r in target[:half]])
    second = statistics.fmean([r["power_mw"] for r in target[half:]])
    delta = second - first

    if abs(delta) < 3.0:
        direction = "基本平稳"
    elif delta > 0:
        direction = "上升"
    else:
        direction = "下降"

    ys = [r["power_mw"] for r in target]
    xs = list(range(len(ys)))
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom if denom else 0.0

    return {
        "scope": f"{target[0]['time_str']} ~ {target[-1]['time_str']}（最长采集时段，{len(target)} 条）",
        "direction": direction,
        "first_half_mean_mw": round(first, 3),
        "second_half_mean_mw": round(second, 3),
        "delta_mw": round(delta, 3),
        "slope_mw_per_sample": round(slope, 4),
    }


# ---------------------------------------------------------------- 对外摘要
#
# ===== 以下为过渡实现，见文件末尾 _impl 覆盖 =====


def summarize(records: list[dict], quality: dict) -> dict:
    """把清洗后的记录聚合为可供模型使用的摘要结构。"""
    if not records:
        return {"empty": True, "quality": quality}

    powers = [r["power_mw"] for r in records]
    currents = [r["current_ma"] for r in records]
    voltages = [r["voltage"] for r in records]

    span_min = (records[-1]["time"] - records[0]["time"]).total_seconds() / 60.0
    cover_min, cover_pct = _coverage(records)
    clusters = _cluster(records)
    cluster_info = [
        {
            "start": c[0]["time_str"],
            "end": c[-1]["time_str"],
            "samples": len(c),
            "mean_power_mw": round(statistics.fmean([r["power_mw"] for r in c]), 3),
        }
        for c in clusters[:10]
    ]

    return {
        "empty": False,
        "quality": quality,
        "window": {
            "start": records[0]["time_str"],
            "end": records[-1]["time_str"],
            "samples": len(records),
            "span_min": round(span_min, 2),
            "coverage_min": cover_min,
            "coverage_pct": cover_pct,
            "cluster_count": len(clusters),
            "clusters": cluster_info,
        },
        "voltage_v": _metric_stats(voltages),
        "current_ma": _metric_stats(currents),
        "power_mw": _metric_stats(powers),
        "energy_mwh": integrate_energy_mwh(records),
        "states": _state_breakdown(records),
        "trend": _trend(records),
        "events": detect_events(records)[:5],
        "event_count": len(detect_events(records)),
        "consistency": {
            "inconsistent": quality.get("inconsistent_readings", 0),
            "pct": quality.get("inconsistent_pct", 0.0),
            "worst": quality.get("worst_inconsistency"),
        },
    }


def format_summary(summary: dict) -> str:
    """把摘要结构渲染成紧凑文本，供模型阅读（控制在几百 token）。"""
    if summary.get("empty"):
        return "【数据摘要】指定时间范围内没有有效采样点。"

    q = summary["quality"]
    w = summary["window"]
    lines = [
        "【数据摘要｜由 Python 预先算好，请直接引用，不要自行换算】",
        f"时间跨度: {w['start']} ~ {w['end']}（跨度 {w['span_min']} 分钟）",
        f"实际覆盖: 仅 {w['coverage_min']} 分钟有数据，占时间跨度的 {w['coverage_pct']}%"
        f"，共 {w['cluster_count']} 个独立采集时段 —— 数据不是连续采集的，"
        f"切勿把「跨度」当成「持续监测时长」",
        f"有效采样: {w['samples']} 条；原始 {q['rows_raw']} 条，"
        f"剔除电压<{MIN_VALID_VOLTAGE_V}V 的无效行 {q['dropped_invalid_voltage']} 条"
        + (f"，时间格式异常 {q['dropped_bad_time']} 条" if q.get("dropped_bad_time") else ""),
    ]
    for c in w.get("clusters", []):
        lines.append(
            f"  · 采集时段 {c['start']} ~ {c['end']}：{c['samples']} 条，"
            f"均功率 {c['mean_power_mw']} mW"
        )
    if q.get("sampling_interval_s"):
        lines.append(f"采样间隔中位数: {q['sampling_interval_s']} 秒")

    if q.get("inconsistent_readings"):
        worst = q.get("worst_inconsistency") or {}
        lines.append(
            f"⚠ 读数自洽性: {q['rows_used']} 行中有 {q['inconsistent_readings']} 行"
            f"（{q.get('inconsistent_pct')}%）的 |电压×电流| 与功率寄存器偏差 >"
            f"{CONSISTENCY_TOLERANCE_MW} mW，最大偏差 {worst.get('deviation_mw')} mW"
            f"（{worst.get('time')}: V={worst.get('voltage')} × I={worst.get('current_ma')} mA"
            f" = {worst.get('vi_mw')} mW，但功率寄存器记 {worst.get('power_mw')} mW）。"
            "这通常是 INA219 电流/功率寄存器非同一转换窗口读取造成的瞬时错配，"
            "属于测量链路问题、不是真实功耗突变；给出功率峰值结论时必须说明这一点。"
        )

    v, c, p = summary["voltage_v"], summary["current_ma"], summary["power_mw"]
    lines.append(
        f"电压(V): 均值 {v['mean']} / 最小 {v['min']} / 最大 {v['max']}"
    )
    lines.append(
        f"电流|I|(mA): 均值 {c['mean']} / 最小 {c['min']} / 最大 {c['max']} / "
        f"标准差 {c['std']} / P95 {c['p95']}"
    )
    lines.append(
        f"功率(mW): 均值 {p['mean']} / 最小 {p['min']} / 最大 {p['max']} / "
        f"标准差 {p['std']} / P95 {p['p95']}"
    )
    lines.append(f"累计能耗: {summary['energy_mwh']} mWh（按梯形法对断档区间跳过）")

    states = summary.get("states") or {}
    if states:
        parts = [
            f"{name} 占 {s['share_pct']}%（{s['samples']} 条，"
            f"均功率 {s['mean_power_mw']} mW，均电流 {s['mean_current_ma']} mA）"
            for name, s in states.items()
        ]
        lines.append("状态分布: " + "；".join(parts))

    trend = summary.get("trend")
    if trend:
        lines.append(
            f"趋势（仅在最长采集时段内可比）: {trend['direction']}，范围 {trend['scope']}；"
            f"前半段均 {trend['first_half_mean_mw']} → 后半段均 "
            f"{trend['second_half_mean_mw']} mW（差 {trend['delta_mw']} mW，"
            f"斜率 {trend['slope_mw_per_sample']} mW/样本）"
        )

    events = summary.get("events") or []
    if events:
        lines.append(
            f"超限事件: 共 {summary['event_count']} 起（阈值 {events[0]['threshold_mw']} mW），"
            f"最严重的 {len(events)} 起如下"
        )
        for e in events:
            lines.append(
                f"  · {e['start']} ~ {e['end']}，时长 {e['duration_min']} 分钟，"
                f"峰值 {e['max_power_mw']} mW，均值 {e['mean_power_mw']} mW"
            )
    else:
        lines.append("超限事件: 无（未超过基线上限）")

    return "\n".join(lines)


def describe_schema() -> str:
    """表结构与口径说明，注入 system prompt，避免模型靠猜。"""
    return (
        "数据库: SQLite，单表 energy_record\n"
        "列: id INTEGER 自增主键 | record_time TEXT(格式 'YYYY-MM-DD HH:MM:SS') | "
        "voltage REAL(单位 V) | current REAL(单位 mA，原始值为【负数】，"
        "绝对值才有物理意义) | power REAL(单位 mW，恒为正)\n"
        "注意: 表中【没有】温湿度列，温湿度不经数据库保存，不要编造温湿度数据。\n"
        "数据存在无效行: voltage 约 0.4V 且 current=0、power=0，属掉线或上电瞬间，"
        "统计时必须排除。\n"
        "另有个别行电压正常但 current≈0（如 0.098 mA）：这是发出睡眠指令后的过渡读数，"
        "属正常现象，不是脏数据。\n"
        "数据不是连续采集的，只集中在少数几天，相邻采集时段之间有小时级甚至天级断档；"
        "任何「单位时间」结论都必须先确认是否跨断档。\n"
        "读数自洽性: INA219 应满足 功率 = 电压 × 电流。本库实测有约三分之一的行不满足，"
        "表现为功率寄存器虚高或电流寄存器虚高（两种模式都有），"
        "推测为电流/功率寄存器非同一转换窗口读取。报告中涉及峰值/异常的结论必须先考虑这一点。"
    )


def describe_baseline() -> str:
    """基线口径，注入 system prompt，让模型做「对比」而不是「猜」。"""
    ct, cp = BASELINE["comm_current_ma"], BASELINE["comm_power_mw"]
    dt = BASELINE["datasheet_current_ma"]
    return (
        f"被测节点: {BASELINE['node']}，标称 {BASELINE['nominal_voltage_v']}V。\n"
        f"通信态（正常工作）实测: 电流 {ct[0]}~{ct[1]} mA，功率 {cp[0]}~{cp[1]} mW；"
        f"数据手册典型电流 {dt[0]}~{dt[1]} mA。\n"
        f"睡眠态实测: 电流约 {BASELINE['sleep_current_ma']} mA，"
        f"功率约 {BASELINE['sleep_power_mw']} mW。\n"
        "判定要点: 通信态功率超过 235 mW 属偏高；睡眠态功率高于 100 mW 属异常"
        "（说明未真正进入睡眠）。"
    )


def calc_stats(db_path: str, metric: str, start: str, end: str) -> dict:
    """供模型调用的统计入口（真正的算术在这里）。"""
    metric = (metric or "power").lower()
    if metric not in ("voltage", "current", "power"):
        return {"error": f"metric 必须是 voltage/current/power，收到 {metric!r}"}

    records, quality = load_records(db_path, start=start, end=end)
    if not records:
        return {"error": "该时间范围内没有有效数据", "range": [start, end]}

    key = {"voltage": "voltage", "current": "current_ma", "power": "power_mw"}[metric]
    stats = _metric_stats([r[key] for r in records])
    out = {
        "metric": metric,
        "unit": PHYSICAL[metric]["unit"],
        "range": [start, end],
        "samples_used": len(records),
        "samples_dropped": quality["dropped_invalid_voltage"],
        "stats": stats,
    }
    if metric == "power":
        out["energy_mwh"] = integrate_energy_mwh(records)
        out["events"] = detect_events(records)[:5]
    return out
