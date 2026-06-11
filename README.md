# 股基研究助手

帮普通用户看懂股票、港股和 ETF 的研究框架。

`securities-analysis-cn` 是一个 AI Agent Skill：中国证券（A股、港股、ETF）研究复盘报告生成器。

本项目输入证券名称或代码后，自动完成数据获取、规则化投研模型分析、互联网研究整理和 PDF 报告生成。报告定位是 **研究参考与方法启发**，帮助普通用户理解估值、基本面、资金面、流动性和风险变量；不输出直接买卖结论，不构成任何投资建议。

## 支持范围

- **A股**：上交所/深交所股票，例如 贵州茅台、比亚迪、600519。
- **港股**：香港联交所股票，例如 腾讯控股、00700.HK。
- **ETF/指数基金**：场内 ETF，例如 沪深300ETF、510300。
- **多标的对比**：支持最多 5 个标的横向比较。

## Agent 兼容性

本项目是一个 `SKILL.md + Python CLI` 形式的 Skill。当前最适合在 **OpenAI Codex / Codex Desktop / Codex CLI** 和 **Claude Code** 中使用，也可以被 Cursor、Cline、Roo Code、Continue 等本地 coding agent 作为普通 Python 项目调用。

OpenClaw、Hermes Agent、LangGraph、CrewAI、AutoGen 等环境通常需要轻量适配或把 `run_analysis.py` 封装为工具。详细说明见 [docs/AGENT_COMPATIBILITY.md](docs/AGENT_COMPATIBILITY.md)。

## 安装

推荐一键初始化：

```bash
git clone https://github.com/kingqiu/securities-analysis-cn.git
cd securities-analysis-cn
python3 scripts/setup.py
```

该脚本会安装依赖、创建本地 `.env` 模板并运行环境检查。已经安装过依赖时可运行：

```bash
python3 scripts/setup.py --skip-install
```

手动安装：

```bash
git clone https://github.com/kingqiu/securities-analysis-cn.git
cd securities-analysis-cn
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 scripts/check_env.py
```

更多安装排障见 [docs/INSTALL.md](docs/INSTALL.md)。

## 配置

如果尚未创建 `.env`，复制 `.env.example` 为 `.env`，填入真实 API Key：

```bash
cp .env.example .env
```

核心配置：

- `TUSHARE_API_TOKEN`：行情、财务、估值、基金和持仓等结构化数据。
- `TUSHARE_API_URL`：Tushare 兼容网关地址。
- `LLM_PROVIDER`：`minimax` 或 `openai`，用于研究解读文字生成。
- `SEARCH_PROVIDER`：默认 `auto`，优先 Tavily 获取最新公司新闻和行业动态；Tavily 不可用时才降级。
- `TAVILY_API_KEY`：用于 Tavily 搜索。

没有 LLM Key 时，报告仍会尽量生成，并降级为规则化研究解读。程序不会用大模型补造缺失的结构化财务或行情数据。

## 最小可运行 Demo

先确认环境检查通过：

```bash
python3 scripts/check_env.py
```

再运行：

```bash
python3 run_analysis.py 贵州茅台   # A股
python3 run_analysis.py 腾讯控股   # 港股
python3 run_analysis.py 510300     # ETF

python3 run_analysis.py 贵州茅台 五粮液       # A股对比
python3 run_analysis.py 510300 510500         # ETF对比
```

输出文件：

- 单标的：`{名称}_{类型}深度分析报告_{日期}.pdf`
- 多标的：`{名称1}_vs_{名称2}_对比分析报告_{日期}.pdf`

## 报告定位

本项目刻意避免把报告写成“买入/卖出建议”。核心输出改为：

- **研究假设与证据地图**：列出当前数据支持什么、不支持什么、还需要观察什么。
- **情景区间与观察触发器**：把估值区间、风险复核线、趋势和成交信号整理为复盘框架。
- **模型研究解读**：大模型只解释规则化模型和已取得的数据，不直接生成交易动作。
- **同行/同类比较**：展示可比样本的估值、盈利质量、成长性、现金流、流动性和风险暴露。

## A股报告

A股报告使用 `analyst_model.py` 先生成可复盘的研究视图，再由 LLM 做审慎解释。核心维度包括：

- 谨慎/中性/乐观价值情景。
- 估值安全边际观察区、中性观察区、高估值复核区、风险复核线。
- 估值、盈利质量、成长性、资金技术面和风险项评分。
- 支撑/压力、均线结构、波动率、成交量确认等观察触发器。
- 核心正向证据、主要风险和反证条件。

## 港股报告

港股报告使用 `hk_analyst_model.py`，在基本面和估值之外额外关注：

- 南向资金持仓及趋势。
- 港股流动性折价和成交活跃度。
- 港元/人民币汇率影响。
- 分红、回购、股东回报线索。
- ADR/美股映射提示。
- 互联网平台公司的监管敏感度和业务分部拆解。

缺少结构化数据的项目会以“数据缺口”提示，不硬生成结论。

## ETF/指数基金报告

ETF 报告使用 `etf_analyst_model.py`，把 ETF 当作指数暴露和资产配置工具观察，而不是套用股票交易逻辑。核心维度包括：

- 指数估值分位和指数暴露。
- 跟踪误差、日均偏差和跟踪质量。
- 综合费率、基金规模、成交额、换手率。
- 折溢价及历史分位。
- 份额变化、规模变化、成分集中度。
- 核心配置、卫星配置、定期观察、波段观察等研究框架。

## 多标的对比报告

对比报告使用统一的新封面和非建议化措辞。输出重点是：

- 为什么这些标的可比，哪些指标不可简单横比。
- 估值、成长性、盈利质量、财务健康、分红/股东回报、流动性和跟踪质量。
- 综合评分只是相对证据排序，不代表买卖结论。

## 互联网研究

默认 `SEARCH_PROVIDER=auto`：

1. 优先使用 Tavily 搜索最新公司新闻、行业动态、机构观点和风险事件。
2. Tavily 未配置或不可用时，才允许 LLM 降级整理。
3. 搜索结果会过滤低质量标题、免责声明页和评级动作词，避免把网页噪音当作结论。

## 数据权限说明

- **A股**：核心依赖日线、估值、利润表、资产负债表、现金流、财务指标、资金流、股东、行业同行等接口。
- **港股**：核心依赖港股基本信息、财务指标、日线、南向持仓；ADR价差和回购明细目前仅作为线索或缺口提示。
- **ETF**：核心依赖基金净值、基金日线、指数日线、指数估值、份额、费率、指数权重；行业权重需要额外接入成分股行业映射。
- **免费行情兜底**：AkShare、efinance、yfinance 仅用于补充实时行情或日线缺口，不作为财务和估值主数据源。

## Provider 架构

| 组件 | 环境变量 | 可选值 | 说明 |
|------|---------|--------|------|
| 数据源 | `DATA_PROVIDER` | `tushare` | 行情、财务、股东、基金数据 |
| LLM | `LLM_PROVIDER` | `minimax`、`openai` | 研究解读文字 |
| 搜索 | `SEARCH_PROVIDER` | `auto`、`tavily`、`ai_summary`、`none` | 公司新闻和行业动态 |

扩展新 provider：继承 `providers/base.py` 中的基类，实现接口，并在 `providers/__init__.py` 注册。

## 文件结构

```text
securities-analysis-cn/
├── SKILL.md                         # Skill 指令入口
├── run_analysis.py                  # 统一入口脚本
├── scripts/setup.py                  # 一键安装与初始化检查
├── scripts/check_env.py              # 环境与配置预检
├── docs/INSTALL.md                   # 安装与排障指南
├── docs/AGENT_COMPATIBILITY.md       # 主流 Agent 兼容性说明
├── config.py                        # 配置和 Provider 选择
├── ai_analysis.py                   # LLM 研究解读 prompts 和 fallback
├── analyst_model.py                 # A股规则化研究模型
├── hk_analyst_model.py              # 港股规则化研究模型
├── etf_analyst_model.py             # ETF规则化研究模型
├── peer_model.py                    # 同行/龙头/估值锚比较
├── pdf_design.py                    # PDF 视觉系统和封面组件
├── providers/                       # 数据、LLM、搜索适配器
├── step3_generate_pdf_report.py      # ETF PDF
├── step4_generate_stock_pdf.py       # A股 PDF
├── step5_generate_hk_stock_pdf.py    # 港股 PDF
├── step6_generate_comparison_pdf.py  # 多标的对比 PDF
├── .env.example                     # 环境变量模板
└── .gitignore
```

## 敏感文件与提交安全

`.gitignore` 已排除：

- `.env`
- `temp_*.json`
- 生成的 `*.pdf`
- `preview_pages/`
- Python 和 Matplotlib 缓存
- macOS `.DS_Store`

提交前建议运行：

```bash
git status --short
```

确认没有 API Key、token、临时数据或报告 PDF 被加入版本库。

## 免责声明

本项目仅用于公开数据整理、研究复盘和学习讨论。所有模型输出都可能受数据缺口、接口权限、延迟行情、搜索质量和模型解释偏差影响。报告不构成任何投资建议、收益承诺或交易依据，请以公司公告、交易所披露和专业持牌机构意见为准。

## 许可证

MIT License
