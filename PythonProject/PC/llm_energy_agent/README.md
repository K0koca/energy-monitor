# 能耗监控系统 · 大模型分析助手

给「基于 Python 的通信节点能耗监控系统」加的大模型分析层。**零第三方依赖**（只用 Python 标准库），
云端 API 与本地 Ollama 共用一份 OpenAI 兼容配置，改一行就能切换。

## 核心设计原则

> **算术归 Python，语义归大模型。**

均值、极差、标准差、能耗积分、超限事件统计全部由本地 Python 算好，
只把「摘要」交给模型。原始时序数据（本项目 240 条）**绝不直接进模型上下文**。
这既省钱、又快，更重要的是**不会出现模型编造数值**。

## 目录结构

```
llm_energy_agent/
├── config.json          配置：provider / base_url / api_key / model / db_path
├── config.py            配置加载（支持环境变量覆盖，key 不必写进文件）
├── data_layer.py        ★ 数据摘要层：只读读库 + 清洗 + 统计 + 摘要渲染
├── tools.py             ★ 工具层：只读 SQL、精确统计、读数自洽性检查、待确认指令生成（含 CRC16）
├── prompts.py           提示词：口径 / 基线 / 输出 JSON 约束
├── llm_client.py        LLM 客户端：OpenAI 兼容 + JSON 容错 + 网络重试 + 离线 mock
├── agent.py             Agent 编排：Function Calling 循环 + JSON 校验重试
├── cli.py               命令行入口
├── ai_panel.py          ★ Tkinter 图形面板（接进 swj.py 用，只加 2 行）
├── eval_set.json        27 条评估集
├── run_eval.py          评估跑分脚本
├── VSCode接入说明.md      VS Code 里的接入步骤 + 报错对照表
├── vscode模板/           可直接复制到工程根 .vscode/ 的 settings.json / launch.json
├── report_*.md          真实数据跑出的分析报告（简报 / 异常归因 / 自洽性 / 口径）
├── eval_report_*.md     评估成绩单
└── README.md
```

## 快速开始

无需安装任何依赖，Python 3.8+ 即可。

```bash
cd llm_energy_agent

# 1) 先离线验证链路（不需要 API Key、不需要联网）
python cli.py --provider mock ask "最近一次采集里，功率有没有超出正常范围？"
python cli.py periods                          # 只看有哪些采集时段，不调模型

# 2) 切到云端（推荐）
#    Windows:  set ENGY_LLM_API_KEY=sk-xxxx
#    Linux/mac: export ENGY_LLM_API_KEY=sk-xxxx
python cli.py ask "睡眠状态下功率正常吗？"
python cli.py daily                            # 生成简报
python cli.py anomaly                          # 异常归因

# 建议用 --out 让报告落盘（同时规避 Windows 终端编码问题）
python cli.py daily   --out report_daily.md
python cli.py anomaly --out report_anomaly.md

# 3) 切到本地 Ollama（离线 / 隐私场景）
ollama serve
ollama pull qwen3:8b
python cli.py --provider local ask "电压稳定吗？"
```

## 配置说明

`config.json` 里 `provider` 三选一：`cloud` / `local` / `mock`。

**建议 API Key 走环境变量**，不要写进文件：

| 环境变量 | 作用 |
|---|---|
| `ENGY_LLM_API_KEY` | 覆盖 api_key |
| `ENGY_LLM_PROVIDER` | 覆盖 provider（cloud/local/mock） |
| `ENGY_LLM_MODEL` | 覆盖模型名 |

## 用哪家的 API Key

先看有哪些预设：

```bash
python cli.py presets
```

用 `--preset` 一键切换服务商（自动改 base_url 和模型名）：

```bash
python cli.py --preset zhipu ask "功率有没有超限？"     # 推荐：永久免费
python cli.py --preset deepseek ask "功率有没有超限？"
```

| 预设 | 模型 | 费用 | 说明 |
|---|---|---|---|
| **zhipu**（默认） | `glm-4-flash` | **永久免费** | 智谱 GLM-4-Flash，**支持 Function Calling**、128K 上下文，国内直连最稳 |
| deepseek | `deepseek-flash` | 很便宜 | ⚠️ `deepseek-chat` **已于 2026-07-24 退役**，现在用 `deepseek-flash` |
| dashscope | `qwen-plus` | 有免费额度 | 阿里云百炼，免费额度仅新加坡地域且 90 天有效 |
| kimi | `moonshot-v1-8k` | 新用户赠少量 | 长文本见长 |
| siliconflow | `Qwen/Qwen3-8B` | 新用户送额度 | 聚合平台，一个 Key 调 50+ 模型 |
| openai | `gpt-4o-mini` | 按量计费 | 需要能访问外网 |

**建议直接用 zhipu（GLM-4-Flash）**：它永久免费，而且明确支持 Function Calling ——
本模块的 `get_summary` / `calc_stats` / `propose_*` 全都依赖工具调用，这一点比模型"智商"更重要。

### 拿 Key 的步骤（以智谱为例）

1. 打开 https://open.bigmodel.cn 注册并登录
2. 进「API Keys」页面，新建一个 Key，复制（形如 `xxxxxxxx.xxxxxxxx`）
3. 命令行里设好：

```bash
# Windows
set ENGY_LLM_API_KEY=你的Key
# Linux / macOS
export ENGY_LLM_API_KEY=你的Key
```

4. 先跑一条验证：`python cli.py --preset zhipu ask "有哪些采集时段？"`

### 三种给 Key 的方式

| 方式 | 做法 | 适用 |
|---|---|---|
| 环境变量（推荐） | `ENGY_LLM_API_KEY` | Key 不会进配置文件，不会被误提交 |
| 写进 `config.json` | 填 `cloud.api_key` | 图省事，但**别提交到 git** |
| 不用 Key | `--provider mock` 或 `--provider local`（Ollama） | 离线自测、隐私场景 |

三个环境变量都支持：`ENGY_LLM_API_KEY` / `ENGY_LLM_PROVIDER` / `ENGY_LLM_MODEL`。

### 成本大概多少

以本模块为例，一问一答约占几千 token（系统提示词几百 + 摘要几百 + 输出几百）。
用 DeepSeek V4.1-Flash，百万 token 输入约 1.5 元、输出约 4.5 元（空闲时段），
**单次问答成本约在 0.01 元以内**，跑 100 次评估集也不到 1 元。用 zhipu 免费额度则为 0。

### 安全提醒

- **不要把 Key 写进代码或提交到 git**，用环境变量。
- Key 泄露请立刻到控制台吊销重建。
- 不要在群里/截图里露出完整 Key。

本地 Ollama 固定为 `http://127.0.0.1:11434/v1`，api_key 随便填（Ollama 不校验）。

## 三条「用得有效」的实践落在哪

| 实践 | 代码位置 | 具体做法 |
|---|---|---|
| **数据摘要化，不喂原始数据** | `data_layer.py::format_summary` | 240 条原始记录聚合为约 15 行摘要（统计值 + 状态分布 + 超限事件 + 覆盖时长），控制在几百 token |
| **数值交给工具算** | `tools.py` + `prompts.py` 铁律 2 | 模型只能通过 `calc_stats` / `get_summary` 拿数字，system prompt 明确禁止自行换算 |
| **给基线，不让它凭空判断** | `prompts.py::build_system_prompt`（调 `data_layer.describe_baseline`） | 注入论文 5.4 节实测基线（通信态 68~73mA / 220~235mW，睡眠态 9.9mA / 32mW），让模型做**对比**而非**猜** |
| 输出结构化 + 校验重试 | `agent.py::_ensure_json` | 强制 JSON，解析失败自动重试 2 次（本地 8B 模型必备兜底） |
| 温度低 + 评估集回归 | `config.json` / `eval_set.json` | temperature=0.2；24 条用例覆盖断档陷阱、能力边界、控制指令等 |
| 前缀缓存降本 | `prompts.py` | system prompt 保持静态，便于服务商做前缀缓存 |

## 安全设计（重要）

1. **数据库只读**：`data_layer.py` 用 `file:<path>?mode=ro` 打开，物理上不可能修改你的数据文件。
2. **SQL 白名单**：只允许单条 `SELECT`，禁 `insert/update/delete/drop/attach/pragma/...`，
   禁止访问系统表，无 `LIMIT` 时自动补上。
3. **指令不自动下发**：改阈值 / 睡眠 / 唤醒 / 同步 RTC 只生成「待确认指令包」，
   在 CLI 里以警告框形式打印，提示必须人工确认。模型无法自行改变设备状态。
4. **协议不重写**：CRC16-MODBUS 与数据包格式完全复用你 `swj.py` 的实现
   （`52 54 43` + 功能码 + 载荷 + CRC 低字节在前），已逐字节比对一致。

## 评估集

```bash
python run_eval.py --provider mock          # 离线自检，应 24/24 通过
python run_eval.py                          # 用真实模型跑（会产生 API 费用）
python run_eval.py --only Q09,Q21           # 只跑指定用例
python run_eval.py --limit 5                # 只跑前 5 条
```

检查项：JSON 结构是否合法、是否调用了期望的工具、有没有出现越界表述
（如把 3 个采集时段说成「连续运行 16 天」）、该给证据时有没有给、控制指令有没有进待确认队列。

**改完提示词或换模型后请务必跑一遍**，这是发现退化的唯一手段。

## 接进现有上位机（不改你的文件）

成品面板已经写好，就是 `ai_panel.py`。**你只需在 `swj.py` 里加 2 行**：

```python
# 文件顶部
from ai_panel import open_ai_panel

# create_gui() 的 control_frame 里（放在"清空历史数据"按钮之后）
ttk.Button(control_frame, text="AI 分析",
           command=lambda: open_ai_panel(root)).pack(side="left", padx=5, pady=10)
```

面板会自动从 `swj.py` 里找到 `client_conn` / `connected`，点「发送到节点」时复用你原有的 socket，
**不重写你的通信代码**。也支持显式传入：`open_ai_panel(root, send_bytes=..., is_connected=...)`。

**详细步骤、`.vscode` 配置模板、常见报错对照表 → 见 [VSCode接入说明.md](VSCode接入说明.md)**
（配置模板在 `vscode模板/` 目录，可直接复制到工程根的 `.vscode/`）

> **关键提醒：AI 调用必须放独立线程**，否则会阻塞 Tkinter 主循环导致界面卡死。
> `ai_panel.py` 已用「后台线程 + queue + `after()` 轮询」实现；
> 若你自己改代码，务必不要在子线程里直接操作 Tk 控件 —— Tkinter 不是线程安全的。
>
> 另外注意 VS Code 的一个坑：`python.analysis.extraPaths` 只影响 Pylance 静态提示，
> **不影响运行时导入**。运行时找不到模块要配 `PYTHONPATH`，或把模块放到脚本同目录。

## 实测发现（用真实数据跑出来的，值得你看一眼）

接入真实模型后，工具链发现了一件**你的测量数据本身的问题**，建议写论文时留意：

INA219 应满足 `功率 = 电压 × 电流`。实测本库 **231 行有效数据里有 75 行（32.5%）不满足**，
容差 5 mW 以上，且两种失效模式同时存在：

| 时段 | 有效行 | 不自洽 | 功率虚高 | 电流虚高 |
|---|---|---|---|---|
| 全库 | 231 | 75（32.5%） | 32 | 43 |
| 2026-06-08 | 169 | 59（34.9%） | 26 | 33 |
| 2026-05-22 | 47 | 14（29.8%） | 6 | 8 |
| 2026-06-02 | 15 | 2（13.3%） | 0 | 2 |

最极端的一行：`2026-06-08 08:51:25`，电压 3.272 V × 电流 72.493 mA = **237.197 mW**，
但功率寄存器记的是 **404.783 mW**（偏差 +167.6 mW）。反向的例子也存在：`08:49:23`
电流 111.443 mA（对应 361.967 mW），功率却只记 229.086 mW。

**两种模式同时存在**，说明不是量程或校准错误，更像**固件依次读取电压/分流电压/电流/功率寄存器时，
负载在快速跳变（ESP8266 射频突发），导致电流与功率落在不同的转换窗口**。
这不是真实功耗突变。

影响：论文 5.4 节报的「通信态 68~73 mA / 220~235 mW」对应的是**自洽的多数行**，
口径站得住（我复算：通信态 |I| 均值 72.854 mA、功率均值 234.031 mW）——
但若答辩时被追问极值，`111.443 mA` 和 `404.783 mW` 会暴露这个问题。

建议：① 固件里改为同一转换窗口读取、或对功率做 3~5 点滑动平均；
② 判超限时用 `V×|I|` 复核，避免单点毛刺触发报警；
③ 报告里标注自洽性标记。

本模块已把这个检查产品化：`check_reading_consistency` 工具 + 提示词铁律第 7 条 +
摘要里的 ⚠ 自动提示，模型在给功率峰值结论前会先做这个校验。

## 已知局限

- **数据不连续**：本项目数据只集中在 3 天（05-22 / 06-02 / 06-08），累计有效覆盖仅约 4.7 分钟。
  因此任何「日均」「连续运行时长」类结论都不成立，摘要里已显式标注，提示词里也列为铁律 3。
- **温湿度不入库**：表中没有温湿度列，模型无法分析温湿度，`describe_schema()` 已明确声明。
- **电流原始值为负**：INA219 分流方向导致，本模块统一取绝对值对外呈现。
- **无效行**：9 条 `voltage≈0.4V` 的掉线/上电采样已被过滤，摘要里会报告剔除条数。
- **8B 本地模型**：JSON 与工具调用可靠性低于云端旗舰，`json_retry` 兜底必不可少；
  若本地模型频繁调错工具，把 `supports_tools` 设为 `false` 并改用纯提示词协议。
