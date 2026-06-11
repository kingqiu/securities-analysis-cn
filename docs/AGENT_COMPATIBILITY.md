# Agent 兼容性说明

本项目是一个 **Skill + Python CLI 工具**：核心入口是 `SKILL.md` 和 `run_analysis.py`。  
只要 Agent 能读取项目文件、运行本地命令、安装 Python 依赖、访问 `.env` 配置，就可以使用本项目生成报告。

## 兼容性总览

| Agent / 平台 | 当前适配度 | 使用方式 | 说明 |
|---|---:|---|---|
| OpenAI Codex / Codex Desktop / Codex CLI | 高 | 原生 Skill / 本地项目 | 已提供 `SKILL.md` 和 `agents/openai.yaml`，推荐直接使用。 |
| Claude Code | 高 | 本地项目 / `CLAUDE.md` | 已提供 `CLAUDE.md`，可按项目说明运行安装和分析命令。 |
| Cursor Agent | 中高 | 本地项目 | Cursor 可读取 README/SKILL 并运行 CLI，但不是原生 Skill 分发格式。 |
| Cline / Roo Code / Continue | 中高 | 本地项目 | 适合通过命令行调用 `run_analysis.py`，需要本地 `.env` 和 Python 环境。 |
| OpenClaw | 中 | 轻量适配 | 如果环境支持 `SKILL.md`、shell、Python 和本地文件，即可使用；否则需写 OpenClaw 专用 wrapper。 |
| Hermes Agent | 不确定 / 需适配 | 工具封装 | 需要确认具体 Hermes 实现是否支持本地命令、文件和环境变量。 |
| Gemini CLI / Gemini Code Assist | 中 | 普通 Python 项目 | 可按 CLI 项目使用，但不是原生 Skill 格式。 |
| GitHub Copilot Coding Agent | 中 | 仓库任务 / CI-like 环境 | 可运行代码，但 API Key、`.env`、PDF 输出和联网权限需要额外配置。 |
| LangGraph / CrewAI / AutoGen | 中 | Tool wrapper | 不直接读取 `SKILL.md`，建议把 `run_analysis.py` 封装成工具函数。 |
| Aider | 中 | 维护和运行项目 | 更适合改代码；可运行脚本，但不属于原生 Skill 使用场景。 |
| 纯网页版 ChatGPT / Claude / Gemini | 低 | 仅能阅读说明 | 如果没有本地文件、shell 和 `.env` 权限，不能真正获取数据和生成 PDF。 |

## 推荐使用方式

### Codex

Codex 是当前最贴合的目标环境。

```bash
python3 scripts/setup.py
python3 run_analysis.py 贵州茅台
python3 run_analysis.py 510300 510500
```

Codex 可直接读取：

- `SKILL.md`
- `agents/openai.yaml`
- `README.md`
- `docs/INSTALL.md`

### Claude Code

Claude Code 可作为本地项目使用：

```bash
python3 scripts/setup.py
python3 run_analysis.py 腾讯控股
```

建议 Claude Code 先阅读：

- `CLAUDE.md`
- `SKILL.md`
- `docs/INSTALL.md`

### Cursor / Cline / Roo Code / Continue

这些工具通常不把项目识别为“原生 Skill”，但可以作为普通本地 CLI 项目使用：

```bash
python3 scripts/setup.py --skip-install
python3 scripts/check_env.py
python3 run_analysis.py 600519
```

使用前需要确认：

- 可以访问项目目录。
- 可以运行 Python。
- `.env` 已配置真实数据源 token。
- 允许生成 PDF 文件。

### OpenClaw

当前项目没有 OpenClaw 专用 manifest。  
如果 OpenClaw 支持读取 `SKILL.md` 并执行本地命令，可以直接按本项目说明使用。

如果 OpenClaw 需要专用工具描述，建议封装命令：

```bash
python3 run_analysis.py <name-or-code>
```

并把 `.env`、依赖安装和输出 PDF 路径写入 OpenClaw 的工具配置。

### Hermes Agent

Hermes Agent 名称对应的实现较多，兼容性取决于它是否支持：

- 本地 shell 命令
- Python 依赖安装
- `.env` 环境变量
- 文件读写
- PDF 输出

如果支持这些能力，可把 `run_analysis.py` 封装为一个工具；如果只支持 prompt 模板，则无法完整运行本项目。

### LangGraph / CrewAI / AutoGen

这些框架更适合通过工具函数调用，而不是直接读取 Skill 文档。

最小 wrapper 思路：

```python
import subprocess
from pathlib import Path

PROJECT_DIR = Path("/path/to/securities-analysis-cn")

def generate_security_report(query: str) -> str:
    result = subprocess.run(
        ["python3", "run_analysis.py", query],
        cwd=PROJECT_DIR,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout
```

多标的对比可把多个参数传给 `run_analysis.py`：

```python
subprocess.run(
    ["python3", "run_analysis.py", "贵州茅台", "五粮液"],
    cwd=PROJECT_DIR,
    check=True,
)
```

## 能力要求

无论使用哪一种 Agent，都需要具备以下能力：

- Python 3.9+
- 可安装 `requirements.txt`
- 可读取和写入项目目录
- 可读取本地 `.env`
- 可访问配置的数据源和搜索服务
- 可生成 PDF 文件

如果 Agent 运行在云端或沙箱环境，需要额外配置：

- `TUSHARE_API_TOKEN`
- `TUSHARE_API_URL`
- 可选：`MINIMA_API_KEY` / `OPENAI_API_KEY`
- 可选：`TAVILY_API_KEY`

## 不适合的使用场景

以下环境不适合直接运行本 Skill：

- 只能聊天、不能执行命令的网页版 Agent。
- 不能安装 Python 依赖的环境。
- 不能读取 `.env` 或 secrets 的云端环境。
- 不能写入 PDF 文件的只读环境。
- 禁止联网且没有本地数据缓存的环境。

## 分发建议

对外分发时建议保留：

- `SKILL.md`
- `CLAUDE.md`
- `agents/openai.yaml`
- `README.md`
- `README_EN.md`
- `docs/INSTALL.md`
- `docs/AGENT_COMPATIBILITY.md`
- `scripts/setup.py`
- `scripts/check_env.py`

不要分发：

- `.env`
- `temp_*.json`
- 生成的 `*.pdf`
- `preview_pages/`
- `.local_plans/`
- 本地缓存目录
