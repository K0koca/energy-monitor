"""大模型客户端 —— 纯标准库实现，云端 API 与本地 Ollama 通用。

为什么不用 openai SDK：本机/用户的 Python 环境里没装，而 OpenAI 兼容接口
就是一个普通的 HTTP POST。用 urllib 实现可以做到【零依赖】，拉起即跑。

支持的 provider：
    cloud / local  —— 任何 OpenAI 兼容的 /chat/completions 端点
    mock           —— 离线自测用的假模型，会模拟一轮真实的 Function Calling 流程，
                      便于在没有 API Key、没有网络的情况下验证整条链路。
"""

import json
import re
import socket
import time
import urllib.error
import urllib.request

# 可重试的 HTTP 状态码（限流与服务端临时故障）
RETRYABLE_STATUS = (429, 500, 502, 503, 504)


class LLMError(RuntimeError):
    pass


def extract_json(text: str) -> dict | None:
    """从模型输出里抠出 JSON。容忍 markdown 代码块与前后废话。"""
    if not text:
        return None
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(s[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


class LLMClient:
    def __init__(self, endpoint: dict):
        self.provider = endpoint["provider"]
        self.base_url = endpoint["base_url"].rstrip("/")
        self.api_key = endpoint.get("api_key", "")
        self.model = endpoint["model"]
        self.temperature = endpoint.get("temperature", 0.2)
        self.timeout = endpoint.get("timeout", 60)
        self.supports_tools = endpoint.get("supports_tools", True)
        self.network_retry = endpoint.get("network_retry", 3)
        self.retry_backoff = endpoint.get("retry_backoff", 1.5)
        self.call_count = 0
        self.retry_count = 0

    # ------------------------------------------------------------ 对外接口

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """返回 {"content": str|None, "tool_calls": [{id,name,arguments}], "usage": {...}}"""
        self.call_count += 1

        if self.provider == "mock":
            return self._mock_chat(messages, tools)

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools and self.supports_tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        raw = self._post("/chat/completions", payload)
        try:
            message = raw["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise LLMError(f"响应结构异常: {str(raw)[:500]}") from e

        calls = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function", {})
            calls.append(
                {
                    "id": tc.get("id") or f"call_{len(calls)}",
                    "name": fn.get("name"),
                    "arguments": _safe_json(fn.get("arguments")),
                }
            )

        return {
            "content": message.get("content"),
            "tool_calls": calls,
            "usage": raw.get("usage", {}),
        }

    # ------------------------------------------------------------ HTTP

    def _post(self, path: str, payload: dict) -> dict:
        """带指数退避重试的 POST。

        重试场景（实测中确实遇到过读超时）：
            · 读/连接超时、连接被重置
            · HTTP 429（限流）与 5xx（服务端临时故障）
        不重试：401/403（Key 错）、400（请求格式错）、404（模型名错）——重试没有意义。
        """
        url = f"{self.base_url}{path}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_error = None
        for attempt in range(1, self.network_retry + 1):
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="ignore")[:500]
                last_error = LLMError(
                    f"HTTP {e.code} 调用 {url} 失败：{detail}\n"
                    + ("（Key 无效或权限不足，请检查 ENGY_LLM_API_KEY）" if e.code in (401, 403) else "")
                    + ("（请求格式错误）" if e.code == 400 else "")
                    + ("（模型名不存在？请用 `python cli.py presets` 确认当前模型名）"
                       if e.code == 404 else "")
                )
                if e.code not in RETRYABLE_STATUS:
                    raise last_error from e
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
                reason = getattr(e, "reason", e)
                last_error = LLMError(f"无法连接 {url}（{reason}）")

            if attempt < self.network_retry:
                self.retry_count += 1
                time.sleep(self.retry_backoff ** attempt)
                continue
            break

        if isinstance(last_error, LLMError):
            raise last_error
        raise LLMError(f"调用 {url} 失败（已重试 {self.network_retry} 次）")

    # ------------------------------------------------------------ mock

    @staticmethod
    def _plan(question: str) -> list[tuple[str, dict]]:
        """离线假模型的「工具选择」逻辑：让 mock 也能演示控制类功能。

        注意：真模型由它自己判断意图，这里只是把常见问法映射成工具序列，
        所以要先区分「分析型提问」与「控制型指令」——否则
        「睡眠态占多少比例」会被误判成「让节点睡眠」。
        """
        q = question or ""

        # 出现这些词，说明是在问数据，不是在下指令
        analysis_markers = (
            "比例", "占比", "多少", "多久", "均值", "平均", "最大", "最小",
            "正常吗", "有没有", "是否", "为什么", "怎么样", "怎么", "多久",
            "分析", "总结", "建议", "预测", "波动", "稳定", "趋势", "对比", "哪个",
        )
        is_analysis = any(k in q for k in analysis_markers)

        if not is_analysis:
            if any(k in q for k in ("睡眠", "睡觉", "休眠")):
                return [("propose_node_sleep", {})]
            if any(k in q for k in ("唤醒", "醒来", "恢复通信")):
                return [("propose_node_wake", {})]
            if any(k in q for k in ("同步", "授时", "对时")):
                return [("propose_sync_rtc", {})]
            m = re.search(r"(?:阈值|报警值|门限)[^\d]{0,8}(\d+)", q) or re.search(r"改成\s*(\d+)", q)
            if m:
                return [("propose_set_threshold", {"value": int(m.group(1))})]

        if any(k in q for k in ("最高", "明细", "列出", "前5", "前 5", "几条记录")):
            return [(
                "query_energy_db",
                {"sql": "SELECT record_time, voltage, current, power FROM energy_record "
                        "ORDER BY power DESC"},
            )]

        if any(k in q for k in ("自洽", "可信", "可靠", "准不准", "准确", "测量误差", "真实负载")):
            return [("check_reading_consistency", {})]

        # 只在「问有哪些时段」时单独返回 list_periods，其余分析类先列表再取摘要
        if ("有哪些" in q or "哪些" in q) and ("时段" in q or "时间" in q):
            return [("list_periods", {})]

        return [("list_periods", {}), ("get_summary", {})]

    def _mock_chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        """离线假模型：按问题意图模拟一轮真实的多步工具调用，再输出结构化 JSON。

        它不"懂"内容，只复现调用时序，因此用途是：
            · 没有 API Key / 没有网络时验证整条链路能否跑通
            · 演示控制类功能（生成待确认指令）
        真正回答质量问题仍需接入真实模型。
        """
        tool_msgs = [m for m in messages if m.get("role") == "tool"]

        if tools:
            question = next(
                (m.get("content", "") for m in messages if m.get("role") == "user"), ""
            )
            plan = self._plan(question)
            step = len(tool_msgs)
            if step < len(plan):
                name, args = plan[step]
                if name == "get_summary" and not args:
                    args = self._summary_args_from(tool_msgs)
                return {
                    "content": None,
                    "tool_calls": [
                        {"id": f"mock_{step + 1}", "name": name, "arguments": args}
                    ],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                }

        return self._mock_answer(tool_msgs)

    @staticmethod
    def _summary_args_from(tool_msgs: list[dict]) -> dict:
        """从上一轮 list_periods 的结果里取出最近一个时段作为 get_summary 的参数。"""
        for msg in reversed(tool_msgs):
            try:
                data = json.loads(msg["content"])
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            periods = data.get("periods") if isinstance(data, dict) else None
            if periods:
                return {"start": periods[-1]["start"], "end": periods[-1]["end"]}
        return {}

    def _mock_answer(self, tool_msgs: list[dict]) -> dict:
        """把工具返回的内容拼成符合约定的 JSON 结论。"""
        evidence: list[str] = []
        for msg in tool_msgs:
            try:
                data = json.loads(msg["content"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            if data.get("summary_text"):
                evidence += [
                    ln for ln in data["summary_text"].splitlines() if ln.strip()
                ][:6]
            elif "inconsistent" in data:
                evidence.append(
                    f"读数自洽性检查: {data.get('checked')} 行中 {data.get('inconsistent')} 行"
                    f"（{data.get('inconsistent_pct')}%）的 |V×I| 与功率寄存器偏差 >"
                    f"{data.get('tolerance_mw')} mW"
                )
                evidence.append(
                    f"功率寄存器偏高 {data.get('mode_power_high', {}).get('count')} 行；"
                    f"电流寄存器偏高 {data.get('mode_current_high', {}).get('count')} 行"
                )
                if data.get("interpretation"):
                    evidence.append(data["interpretation"])
            elif data.get("periods"):
                evidence.append(
                    "采集时段: "
                    + "；".join(f"{p['start']}~{p['end']}({p['samples']}条)"
                                for p in data["periods"])
                )
            elif data.get("rows") is not None:
                top = data["rows"][:5]
                evidence.append(f"查询返回 {data.get('row_count')} 行，前 5 行：")
                evidence += [
                    "  " + json.dumps(r, ensure_ascii=False) for r in top
                ]
            elif data.get("stats"):
                evidence.append(f"{data.get('metric')} 统计: " + json.dumps(
                    data["stats"], ensure_ascii=False))

        pending = self._mock_pending(tool_msgs)

        if pending:
            answer = (
                f"（离线 mock 模式）已生成「{pending['human_readable']}」的待确认指令，"
                f"数据包 {pending['payload_hex']}。"
                "该指令【尚未发送】，需要你在上位机上人工确认后才会真正下发。"
            )
            confidence = "high"
        else:
            answer = (
                "（离线 mock 模式）已按流程调用工具取到摘要。"
                "最近一个采集时段内节点稳定处于通信态，功率均值与基线一致；"
                "仅在秒级出现数起短暂超限尖峰，未持续。"
            )
            confidence = "medium"

        payload = {
            "answer": answer,
            "evidence": evidence,
            "suggestions": [] if pending else [
                "确认超限尖峰是否为通信突发瞬时电流，而非真实过载。",
                "如需精确判定，应延长连续采集时段后再评估。",
            ],
            "confidence": confidence,
            "data_limitations": [
                "本结果为离线 mock 输出，仅用于验证链路，质量结论请以真实模型运行为准。",
                "数据在时间上不连续，存在小时级/天级断档。",
            ],
        }
        return {
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
            "tool_calls": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

    @staticmethod
    def _mock_pending(tool_msgs: list[dict]) -> dict | None:
        for msg in tool_msgs:
            try:
                data = json.loads(msg["content"])
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and data.get("status") == "待人工确认":
                return data
        return None


def _safe_json(value):
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {"_raw": value}
