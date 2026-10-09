"""配置加载：云端 API 与本地 Ollama 共用同一份 OpenAI 兼容配置，切换只改 provider。

用法：
    cfg = load_config()                 # 读 config.json
    ep  = active_endpoint(cfg)          # 取当前 provider 的连接参数

API Key 建议用环境变量 ENGY_LLM_API_KEY 传入，避免写进文件。
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(HERE, "config.json")

VALID_PROVIDERS = ("cloud", "local", "mock")

# 云端预设：用 `--preset <名字>` 一键切换 base_url + model，不用手改 JSON。
# ⚠️ 各家的模型名会变，正式用之前请到对应控制台确认一次当前可用的模型 ID。
CLOUD_PRESETS = {
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "note": "智谱 GLM-4-Flash —— 永久免费、支持 Function Calling、128K 上下文，"
                "国内直连最稳，本模块默认推荐（新版可试 glm-4.7-flash）",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-flash",
        "note": "便宜且能力强。注意 deepseek-chat / deepseek-reasoner 已于 2026-07-24 退役，"
                "现在用 deepseek-flash（V4.1-Flash）或 deepseek-v4-pro",
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "note": "阿里云百炼（通义千问）。免费额度仅新加坡地域且有 90 天限制",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "note": "月之暗面 Kimi。新用户赠送少量额度，长文本见长",
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen3-8B",
        "note": "硅基流动：聚合平台，一个 Key 可调 50+ 模型，新用户送额度；模型 ID 以控制台为准",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "note": "需要能访问外网",
    },
}


def apply_preset(cfg: dict, name: str) -> dict:
    """把某个云端预设写进 cfg['cloud']，并切换到 cloud provider。"""
    if name not in CLOUD_PRESETS:
        raise ValueError(f"未知预设 {name!r}，可选：{', '.join(CLOUD_PRESETS)}")
    preset = CLOUD_PRESETS[name]
    cfg.setdefault("cloud", {})
    cfg["cloud"]["base_url"] = preset["base_url"]
    cfg["cloud"]["model"] = preset["model"]
    cfg["provider"] = "cloud"
    return cfg


def load_config(path: str | None = None) -> dict:
    """读取配置，并允许环境变量覆盖 provider / api_key。"""
    path = path or DEFAULT_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    env_provider = os.environ.get("ENGY_LLM_PROVIDER")
    if env_provider:
        cfg["provider"] = env_provider

    env_key = os.environ.get("ENGY_LLM_API_KEY")
    if env_key:
        for name in ("cloud", "local"):
            if name in cfg:
                cfg[name]["api_key"] = env_key

    env_model = os.environ.get("ENGY_LLM_MODEL")
    if env_model:
        provider = cfg.get("provider", "cloud")
        if provider in cfg:
            cfg[provider]["model"] = env_model

    provider = cfg.get("provider", "cloud")
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"provider 必须是 {VALID_PROVIDERS} 之一，当前是 {provider!r}")
    return cfg


def active_endpoint(cfg: dict) -> dict:
    """返回当前 provider 生效的连接参数。"""
    provider = cfg.get("provider", "cloud")
    if provider == "mock":
        return {
            "provider": "mock",
            "base_url": "mock://offline",
            "api_key": "",
            "model": "mock",
            "temperature": 0.0,
            "timeout": 10,
            "supports_tools": True,
        }

    ep = dict(cfg[provider])
    ep["provider"] = provider
    ep.setdefault("supports_tools", True)
    ep.setdefault("temperature", 0.2)
    ep.setdefault("timeout", 60)
    if not ep.get("base_url"):
        raise ValueError(f"{provider} 缺少 base_url")
    if provider == "cloud" and not ep.get("api_key"):
        raise ValueError(
            "云端模式缺少 api_key。请设置环境变量 ENGY_LLM_API_KEY，或填进 config.json 的 cloud.api_key。\n"
            "临时想离线试跑：把 config.json 的 provider 改成 \"mock\"。"
        )
    return ep


def db_path(cfg: dict) -> str:
    p = cfg.get("db_path", "")
    if not p:
        raise ValueError("config.json 缺少 db_path")
    return p
