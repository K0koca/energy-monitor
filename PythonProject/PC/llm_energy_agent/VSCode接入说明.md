# 在 VS Code 里接入 AI 分析面板

> 前提：你的工作区文件夹是 `E:\1DKN\big4\PythonProject`（和原来的 PyCharm 工程根一致）。
> 如果你打开的是 `上位机` 子文件夹，把下文路径里的 `\上位机` 去掉即可。

## 一、VS Code 最容易踩的坑（先看这条）

VS Code 里有两个"看起来一样、作用完全不同"的配置：

| 配置 | 作用 | 影响运行吗 |
|---|---|---|
| `python.analysis.extraPaths` | 让 **Pylance 静态分析**找到模块，消除红色波浪线 | **不影响** |
| `PYTHONPATH` 环境变量 | 让 **Python 解释器运行时**找到模块 | **影响** |

所以典型症状是：**编辑器里不报红，一运行就 `ModuleNotFoundError: No module named 'ai_panel'`**。
解决办法见第二、三节。

## 二、放哪里（二选一）

### 方案 A：复制到工程里（推荐，最省事，不需要 PYTHONPATH）

把整个 `llm_energy_agent` 文件夹放到 `swj.py` 旁边：

```
E:\1DKN\big4\PythonProject\
├── .venv\
└── 上位机\
    ├── swj.py
    ├── db_module.py
    ├── energy_monitor.db
    └── llm_energy_agent\      ← 整个文件夹放这里
        ├── ai_panel.py
        └── ...
```

因为 Python 运行脚本时会把**脚本所在目录**加进 `sys.path`，
`swj.py` 和 `ai_panel.py` 同目录，`import ai_panel` 天然可用。

### 方案 B：不动工程，用 PYTHONPATH 指过去

模块留在 `D:\code\workbuddy\2026-10-08-21-49-07\llm_energy_agent`，
在工程根建一个 `.env` 文件（内容见 `vscode模板\.env.example`）：

```
PYTHONPATH=E:\1DKN\big4\PythonProject\上位机;D:\code\workbuddy\2026-10-08-21-49-07\llm_energy_agent
```

并在 `.vscode/settings.json` 里加：

```json
"python.envFile": "${workspaceFolder}\\.env"
```

这样调试和集成终端都能生效。**注意 Windows 下多个路径用 `;` 分隔，不是 `:`。**

## 三、配置 `.vscode`（模板已给好）

把 `vscode模板` 里的文件复制到工程根的 `.vscode\` 目录：

```
E:\1DKN\big4\PythonProject\.vscode\
├── settings.json
├── launch.json
└── .env            ← 从 .env.example 改名，填上你的 Key（可选）
```

`launch.json` 里已经准备了 4 个可直接按 F5 运行的配置：

| 配置名 | 作用 |
|---|---|
| ① 运行 swj.py（能耗监控主界面） | 正常启动你的上位机 |
| ② 独立预览 AI 面板 | 不接 swj.py，单独看面板长什么样 |
| ③ 命令行：生成简报 | 等价于 `python cli.py daily --out report_daily.md` |
| ④ 命令行：离线自测提问 | 不需要 Key，验证链路 |

> 若你的 Python 扩展较旧，`"type": "debugpy"` 需改成 `"type": "python"`。
> `"console": "integratedTerminal"` **不要改成 internalConsole** —— GUI 程序和中文输出在集成终端里才正常。

## 四、选解释器（一定要做）

`Ctrl + Shift + P` → 输入 `Python: Select Interpreter` → 选：

```
E:\1DKN\big4\PythonProject\.venv\Scripts\python.exe
```

确认方法（VS Code 集成终端里执行）：

```
python -c "import sys,tkinter,matplotlib;print(sys.version);print(tkinter.TkVersion)"
```

应输出 `3.14.2` 与 `8.6`。**本模块零 pip 依赖**（纯标准库 + tkinter），不用装任何包。

> 顺带一提：你工程里 `.idea/misc.xml` 记的是 "Python 3.11"，而 `.venv` 实际是 3.14.2。
> 如果用 VS Code 就无所谓了，但如果你哪天回 PyCharm，记得核对一下。

## 五、改 swj.py：只加两行

文件顶部加一行 import：

```python
from ai_panel import open_ai_panel
```

在 `create_gui()` 里 `control_frame` 那段（"清空历史数据"按钮之后）加一个按钮：

```python
    btn_ai = ttk.Button(control_frame, text="AI 分析",
                        command=lambda: open_ai_panel(root))
    btn_ai.pack(side="left", padx=5, pady=10)
```

**其余一行都不用改。** 面板会自动从 `swj.py` 里找到 `client_conn` / `connected`，
点「发送到节点」时复用你原来的 socket 发送。

> 提示：VS Code 里如果 `from ai_panel import ...` 有红色波浪线但能跑，说明只是
> `python.analysis.extraPaths` 没配（第一节的表）。不影响运行。

## 六、验证顺序

1. **先不改 swj.py**，直接跑配置①，确认原有功能（启动透传、曲线、数据库）全部正常 —— 证明没破坏你的东西
2. 加上按钮和 import，再跑一次
3. 点「AI 分析」→ 面板弹出
4. 服务商选「离线自测（不用 Key）」→ 点「本地快检」→ **应秒出 32.5% 不自洽的结论**（零费用）
5. 仍是离线模式，输入「把报警阈值改成 200。」→ 应出现待确认指令卡片，
   数据包 `52 54 43 01 C8 00 2F E1`。**先别点发送**，只验证界面
6. 切到云端，填 Key，跑一次「生成简报」

## 七、常见报错对照

| 现象 | 真正原因 | 解决 |
|---|---|---|
| 编辑器不报红，运行却 `ModuleNotFoundError: No module named 'ai_panel'` | 只配了 extraPaths，没配运行时路径 | 方案 A 或方案 B（第一节） |
| 编辑器报红但能正常运行 | extraPaths 没配 | settings.json 里加 `python.analysis.extraPaths` |
| `No module named 'tkinter'` | 选错解释器 | 第四节 |
| 点按钮后界面卡死 | AI 调用阻塞主线程 | 本模块已用后台线程；若你改过代码请确认没在主线程调 `agent.ask()` |
| `缺少 api_key` | 选了云端却没填 Key | 面板里填，或 `.env` 里设 `ENGY_LLM_API_KEY` |
| `上位机未连接到节点` | 点「发送到节点」时透传没启动 | 先点主界面「启动透传」，等 ESP8266 连上 |
| 终端里中文乱码 | 终端编码 | 面板里用「保存报告」写成 UTF-8 文件；cli.py 也自带 UTF-8 输出 |
| 启动报 `Could not find platform independent libraries <prefix>` | venv 的 base Python 路径在别的用户下（`C:\Users\DKN\...`） | 一般可忽略；若真出错就在本机重建 venv：`python -m venv .venv` |

## 八、答辩演示建议

现场网络不可靠：提前把服务商切成「离线自测」演示界面与工具链路，
再用「保存报告」展示之前跑好的真实报告（`report_anomaly.md`、`report_consistency.md` 等）。
本地 Ollama 是另一条完全离线的路线（需提前 `ollama pull qwen3:8b`）。
