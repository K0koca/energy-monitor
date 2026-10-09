"""Agent 编排 —— Function Calling 循环 + JSON 输出校验重试。

流程：
    用户提问
      -> 模型决定调用哪些工具（list_periods / get_summary / calc_stats / ...）
      -> 由本地 Python 真正执行工具（数值计算都在这里）
      -> 工具结果回填给模型
      -> 模型输出结构化 JSON 结论
      -> 由本层校验 JSON；不合法则带着错误提示重试（8B 本地模型必须有的兜底）

另外维护 trace（每一步调用了什么工具、参数、结果摘要），便于演示与排查。
"""

import json

from config import active_endpoint, db_path
from llm_client import LLMClient, extract_json
from prompts import build_system_prompt, build_user_prompt
from tools import TOOL_SCHEMAS, ToolRunner


class EnergyAgent:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.endpoint = active_endpoint(cfg)
        self.client = LLMClient(self.endpoint)
        self.runner = ToolRunner(db_path(cfg), cfg.get("max_sql_rows", 500))
        self.system_prompt = build_system_prompt()
        self.max_rounds = cfg.get("max_tool_rounds", 6)
        self.json_retry = cfg.get("json_retry", 2)
        self.trace: list[dict] = []

    # ------------------------------------------------------------------

    def ask(self, question: str) -> dict:
        self.trace = []
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": build_user_prompt(question)},
        ]

        content = self._run_tool_loop(messages)
        content, parsed = self._ensure_json(messages, content)

        return {
            "question": question,
            "result": parsed,
            "raw_content": content,
            "pending_commands": list(self.runner.pending),
            "trace": self.trace,
            "model": f"{self.endpoint['provider']}:{self.endpoint['model']}",
            "llm_calls": self.client.call_count,
        }

    # ------------------------------------------------------------------

    def _run_tool_loop(self, messages: list[dict]) -> str | None:
        """执行工具调用循环，返回模型最终的自然语言/JSON 文本。"""
        content = None
        for round_no in range(1, self.max_rounds + 1):
            resp = self.client.chat(messages, tools=TOOL_SCHEMAS)
            content = resp.get("content")

            calls = resp.get("tool_calls") or []
            if not calls:
                return content

            messages.append(
                {
                    "role": "assistant",
                    "content": resp.get("content"),
                    "tool_calls": [
                        {
                            "id": c["id"],
                            "type": "function",
                            "function": {
                                "name": c["name"],
                                "arguments": json.dumps(c["arguments"], ensure_ascii=False),
                            },
                        }
                        for c in calls
                    ],
                }
            )

            for c in calls:
                result = self.runner.dispatch(c["name"], c["arguments"])
                self.trace.append(
                    {
                        "round": round_no,
                        "tool": c["name"],
                        "arguments": c["arguments"],
                        "result_preview": _preview(result),
                    }
                )
                messages.append(
                    {"role": "tool", "tool_call_id": c["id"], "content": result}
                )

        # 超过最大轮数：掐断工具，强制给结论
        messages.append(
            {
                "role": "user",
                "content": "已达到最大工具调用轮数。请立刻基于已获得的信息输出最终 JSON 结论。",
            }
        )
        resp = self.client.chat(messages, tools=None)
        return resp.get("content")

    def _ensure_json(self, messages: list[dict], content: str | None):
        """校验 JSON；不合法则重试。返回 (最终文本, 解析结果或降级结构)。"""
        parsed = extract_json(content or "")
        if parsed is not None:
            return content, parsed

        for attempt in range(1, self.json_retry + 1):
            messages.append({"role": "assistant", "content": content or ""})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "你的上一条输出不是合法 JSON。请只输出一个 JSON 对象，"
                        "结构为 {\"answer\":字符串, \"evidence\":字符串数组, "
                        "\"suggestions\":字符串数组, \"confidence\":\"high|medium|low\", "
                        "\"data_limitations\":字符串数组}，不要任何解释文字、不要 markdown 代码块。"
                    ),
                }
            )
            resp = self.client.chat(messages, tools=None)
            content = resp.get("content")
            parsed = extract_json(content or "")
            self.trace.append(
                {"round": "json_retry", "tool": None, "arguments": {"attempt": attempt},
                 "result_preview": "JSON 解析成功" if parsed else "JSON 仍解析失败"}
            )
            if parsed is not None:
                return content, parsed

        # 彻底失败：降级为纯文本结论，但明确标注
        return content, {
            "answer": (content or "").strip() or "(模型未返回内容)",
            "evidence": [],
            "suggestions": [],
            "confidence": "low",
            "data_limitations": ["模型未按约定返回 JSON，已降级展示原文，结论可靠性较低。"],
        }


def _preview(text: str, limit: int = 300) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + " …(截断)"
