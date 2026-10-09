"""命令行入口。

用法示例：
    python cli.py periods                      # 看有哪些采集时段（不调模型）
    python cli.py ask "最近一次功率有没有超限？"
    python cli.py daily                        # 生成最近时段简报
    python cli.py anomaly                      # 异常归因
    python cli.py --provider mock ask "测试"    # 离线验证链路，不需要 API Key
    python cli.py --json ask "..."             # 额外输出完整 JSON
"""

import argparse
import json
import sys

# Windows 中文环境下重定向输出（写日志/管道）时，默认用 cp936 编码会导致中文乱码，
# 这里强制 stdout/stderr 走 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from agent import EnergyAgent
from config import CLOUD_PRESETS, apply_preset, load_config
from prompts import ANOMALY_TEMPLATE, DAILY_REPORT_TEMPLATE
from tools import tool_list_periods


def _print_report(res: dict, show_json: bool = False, out_path: str | None = None) -> None:
    lines: list[str] = []

    def emit(text: str = "") -> None:
        print(text)
        lines.append(text)

    r = res["result"]
    emit("=" * 72)
    emit(f"模型: {res['model']}    模型调用次数: {res['llm_calls']}")
    emit("=" * 72)

    if res["trace"]:
        emit("\n[工具调用过程]")
        for t in res["trace"]:
            mark = "↻" if t["round"] == "json_retry" else f"{t['round']}"
            if t["tool"]:
                emit(f"  {mark}. {t['tool']}({json.dumps(t['arguments'], ensure_ascii=False)})")
            else:
                emit(f"  {mark}. JSON 校验重试 -> {t['result_preview']}")

    emit("\n[结论]")
    emit("  " + str(r.get("answer", "")).strip())

    ev = r.get("evidence") or []
    if ev:
        emit("\n[证据（均来自工具返回）]")
        for e in ev:
            emit(f"  · {e}")

    sug = r.get("suggestions") or []
    if sug:
        emit("\n[建议]")
        for s in sug:
            emit(f"  · {s}")

    emit(f"\n[置信度] {r.get('confidence', '未给出')}")

    lim = r.get("data_limitations") or []
    if lim:
        emit("\n[数据局限]")
        for l in lim:
            emit(f"  · {l}")

    pend = res.get("pending_commands") or []
    if pend:
        emit("\n" + "!" * 72)
        emit("⚠  以下指令【尚未发送】，必须由你在上位机人工确认后手动发送：")
        for p in pend:
            emit(f"   · {p['human_readable']}")
            emit(f"     数据包: {p['payload_hex']}")
            emit(f"     风险提示: {p['warning']}")
        emit("!" * 72)

    if show_json:
        blob = json.dumps(res, ensure_ascii=False, indent=2)
        emit("\n[完整 JSON]")
        emit(blob)

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\n报告已保存到: {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="通信节点能耗监控 · 大模型分析助手")
    parser.add_argument("command", choices=["ask", "daily", "anomaly", "periods", "presets"],
                        help="ask=自由提问 / daily=生成简报 / anomaly=异常归因 / "
                             "periods=列出采集时段 / presets=列出可选的云端预设")
    parser.add_argument("question", nargs="?", default="", help="ask 命令的问题")
    parser.add_argument("--provider", choices=["cloud", "local", "mock"],
                        help="覆盖 config.json 里的 provider")
    parser.add_argument("--preset", choices=sorted(CLOUD_PRESETS),
                        help="一键切换到某个云端服务商（含 base_url 与模型名）")
    parser.add_argument("--config", help="指定配置文件路径")
    parser.add_argument("--json", action="store_true", help="额外打印完整 JSON")
    parser.add_argument("--out", help="把报告写入指定文件（推荐，避免终端编码问题）")
    args = parser.parse_args()

    # presets 只列清单，不读配置、不调模型
    if args.command == "presets":
        print(f"{'名称':<12}{'模型':<18}说明")
        print("-" * 88)
        for name, p in CLOUD_PRESETS.items():
            print(f"{name:<12}{p['model']:<18}{p['note']}")
        print("\n用法：python cli.py --preset zhipu ask \"功率有没有超限？\"")
        return 0

    cfg = load_config(args.config)
    if args.preset:
        apply_preset(cfg, args.preset)
    if args.provider:
        cfg["provider"] = args.provider

    # periods 不需要调模型，直接查库
    if args.command == "periods":
        from config import db_path
        info = tool_list_periods(db_path(cfg))
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    question = {
        "ask": args.question,
        "daily": DAILY_REPORT_TEMPLATE,
        "anomaly": ANOMALY_TEMPLATE,
    }[args.command]

    if args.command == "ask" and not question.strip():
        parser.error("ask 命令需要提供问题，例如：python cli.py ask \"功率有没有超限？\"")

    agent = EnergyAgent(cfg)
    try:
        res = agent.ask(question)
    except Exception as e:
        print(f"\n[失败] {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    _print_report(res, show_json=args.json, out_path=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
