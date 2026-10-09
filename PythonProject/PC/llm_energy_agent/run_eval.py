"""评估集跑分：改完提示词或换模型后跑一遍，立刻看出有没有退化。

检查项：
    schema_ok        输出是约定的 JSON 结构（answer/evidence/suggestions/confidence/data_limitations）
    tools_ok         调用了期望的工具（expect_tools 至少命中一个）
    no_hallucination 未出现 forbidden 里的越界/幻觉表述
    evidence_ok      有数据类问题时，evidence 非空（不能空口给结论）
    pending_ok       控制类指令必须进「待确认」队列，且未声称已执行

用法：
    python run_eval.py                      # 用 config.json 的 provider
    python run_eval.py --provider mock       # 离线自检
    python run_eval.py --only Q09,Q21        # 只跑指定用例
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 同 cli.py：避免 Windows 中文环境重定向输出时乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from agent import EnergyAgent
from config import CLOUD_PRESETS, apply_preset, load_config

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL_PATH = os.path.join(HERE, "eval_set.json")


def check_one(res: dict, case: dict) -> dict:
    r = res["result"]
    blob = json.dumps(r, ensure_ascii=False)
    called = {t["tool"] for t in res["trace"] if t["tool"]}

    schema_ok = all(
        k in r for k in ("answer", "evidence", "suggestions", "confidence", "data_limitations")
    ) and bool(str(r.get("answer", "")).strip())

    expect = case.get("expect_tools") or []
    tools_ok = (not expect) or bool(called & set(expect))

    forbidden_hit = [f for f in (case.get("forbidden") or []) if f in blob]
    no_hallu = not forbidden_hit

    evidence_ok = (not case.get("require_evidence")) or bool(r.get("evidence"))

    pending_ok = True
    if case["category"].startswith("控制"):
        pending_ok = bool(res["pending_commands"])

    passed = schema_ok and tools_ok and no_hallu and evidence_ok and pending_ok
    return {
        "passed": passed,
        "schema_ok": schema_ok,
        "tools_ok": tools_ok,
        "no_hallucination": no_hallu,
        "evidence_ok": evidence_ok,
        "pending_ok": pending_ok,
        "called": sorted(called),
        "forbidden_hit": forbidden_hit,
        "answer": str(r.get("answer", ""))[:60].replace("\n", " "),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["cloud", "local", "mock"])
    ap.add_argument("--preset", choices=sorted(CLOUD_PRESETS),
                    help="一键切换到某个云端服务商")
    ap.add_argument("--config")
    ap.add_argument("--only", help="逗号分隔的用例 id，如 Q09,Q21")
    ap.add_argument("--limit", type=int, help="只跑前 N 个用例")
    ap.add_argument("--out", help="把报告同时写入指定文件（便于留档 / 规避终端编码问题）")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.preset:
        apply_preset(cfg, args.preset)
    if args.provider:
        cfg["provider"] = args.provider

    with open(EVAL_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)["cases"]

    if args.only:
        want = {s.strip() for s in args.only.split(",")}
        cases = [c for c in cases if c["id"] in want]
    if args.limit:
        cases = cases[: args.limit]

    lines: list[str] = []

    def emit(text: str = "") -> None:
        print(text, flush=True)
        lines.append(text)

    emit(f"provider = {cfg['provider']}    模型 = {cfg.get(cfg['provider'], {}).get('model', '-')}"
         f"    用例数 = {len(cases)}")
    emit("-" * 78)

    results = []
    for c in cases:
        agent = EnergyAgent(cfg)
        try:
            res = agent.ask(c["question"])
            chk = check_one(res, c)
        except Exception as e:
            chk = {"passed": False, "error": f"{type(e).__name__}: {e}",
                   "answer": "", "called": [], "forbidden_hit": []}
        results.append((c, chk))

        flag = "PASS" if chk["passed"] else "FAIL"
        emit(f"[{flag}] {c['id']:<4} {c['category']:<10} {c['question'][:34]:<36} "
             f"tools={','.join(chk.get('called') or []) or '-'}")
        if not chk["passed"]:
            for k in ("schema_ok", "tools_ok", "no_hallucination", "evidence_ok", "pending_ok"):
                if k in chk and not chk[k]:
                    emit(f"        x {k}")
            if chk.get("forbidden_hit"):
                emit(f"        x 命中越界表述: {chk['forbidden_hit']}")
            if chk.get("error"):
                emit(f"        x {chk['error']}")
            if chk.get("answer"):
                emit(f"        回答: {chk['answer']}")

    total = len(results)
    passed = sum(1 for _, c in results if c["passed"])
    emit("-" * 78)
    emit(f"通过 {passed}/{total}  ({100.0 * passed / total:.1f}%)" if total else "无用例")

    failed = [c["id"] for c, r in results if not r["passed"]]
    if failed:
        emit("未通过: " + ", ".join(failed))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
