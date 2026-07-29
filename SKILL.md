---
name: 股基研究助手
version: 1.1.0
description: 帮普通用户看懂股票、港股和 ETF 的研究框架，生成非荐股导向的中文研究复盘 PDF 报告。默认走通达信 MCP 零 token 路径（run_report.py，无需 API token），旧 Tushare 路径（run_analysis.py）保留作全类型兜底。
---

# 股基研究助手

帮普通用户看懂股票、港股和 ETF 的研究框架。

Generate PDF research reports for A-shares, Hong Kong stocks, listed ETFs, and multi-security comparisons.

The report is a research-review artifact. It should help the user understand evidence, scenarios, risks, and follow-up observations. It must not be framed as direct investment advice, a buy/sell call, or a best entry/exit point.

## Agent Compatibility

This skill is optimized for Codex-style and Claude Code-style local agents that can read files, run shell commands, install Python dependencies, load `.env`, and write PDF files. For Cursor, Cline, Roo Code, Continue, OpenClaw, Hermes Agent, LangGraph, CrewAI, AutoGen, and similar tools, see `docs/AGENT_COMPATIBILITY.md` before installing or wrapping the CLI.

## Quick Start

> 运行命令前请先 `cd` 到本 SKILL.md 所在目录（即技能仓库根目录），下方命令均相对该目录执行。

项目有两条数据路径，**默认走 A · TDX 零 token（推荐，无需任何 API token）**：

### 路径 A · TDX 零 token（推荐，当前主线）

数据来自通达信 MCP 落盘文件（`tdx_raw/*.json`、`fin_<code>.json`），价格/指数行情用 AkShare 兜底，**全程零 LLM token、零伪造**。

```bash
# ETF 报告（已生产可用：588000 已验证 T1+T2 数据增强）
python3 run_report.py 588000 etf

# A 股报告（实验/PoC：需先落盘 fin_<code>.json，详见「数据架构」）
python3 run_report.py 600519 stock
```

- **ETF**：生产可用。T1（5 个零 token 章节：监控/商业模式/熊市情景/数据源/情景图）+ T2（宽基估值锚 2.7 + 同类 ETF 费率 7.1）已落地（分支 `feature/tdx-data-source`，commit `0953d69`）。
- **A 股**：需预先用 TDX 采集并落盘 `fin_<code>.json`（参考 `tdx_build_report.py` PoC），否则回退到路径 B。
- **港股 / 对比报告**：暂未接入 TDX，仍走路径 B（Tushare）。

### 路径 B · Tushare（legacy，全类型覆盖）

需 `TUSHARE_API_TOKEN`，覆盖 股 / 港 / ETF / 对比 四类（step3~6）：

```bash
python3 run_analysis.py 贵州茅台
python3 run_analysis.py 600519
python3 run_analysis.py 腾讯控股
python3 run_analysis.py 00700.HK
python3 run_analysis.py 510300
python3 run_analysis.py 贵州茅台 五粮液 泸州老窖
```

Outputs are PDF files in the skill directory:

- Single security: `{名称}_{类型}深度分析报告_{日期}.pdf`
- Comparison: `{名称1}_vs_{名称2}_对比分析报告_{日期}.pdf`

## Setup

### 路径 A（TDX 零 token）
无需任何 `.env` / API token。前提：通达信 MCP 连接器已连接（本环境 `tdx-connector` 已 connected）。报告生成依赖见 `requirements.txt`：

```bash
python3 -m pip install -r requirements.txt
```

### 路径 B（Tushare）
```bash
python3 scripts/setup.py          # 或 python3 -m pip install -r requirements.txt
cp .env.example .env
python3 scripts/check_env.py
```

`.env` 需配置 `TUSHARE_API_TOKEN`（市场与财务数据 truth source）。`LLM_PROVIDER` / `SEARCH_PROVIDER` 可选——报告优先走确定性研究文本，缺 LLM key 也能出 PDF。Run `python3 scripts/check_env.py` before the first report or when debugging setup. For installation troubleshooting, see `docs/INSTALL.md`.

If a provider permission is missing, keep the report running when possible and mark the affected fields as `N/A`. Do not invent unavailable data.

## Workflow

**路径 A（TDX 零 token）**：
1. 用 TDX MCP 采集标的财务/行情，落盘为 `tdx_raw/<code>_*.json` 与 `fin_<code>.json`（PoC 见 `tdx_build_report.py`；ETF 已有现成落盘）。
2. `python3 run_report.py <code> <stock|etf>`：读落盘数据 + AkShare 行情兜底，跑确定性研究模型，**不调用 LLM**。
3. 生成 PDF（`step3`=ETF，`step4`=A股）。

**路径 B（Tushare）**：
1. `identify_code_type.resolve_input()` 解析名称/代码。
2. `DataProvider.identify_security()` 识别证券类型。
3. 拉取行情、财务、股东、资金流、同业数据（Tushare）。
4. 用 AkShare/efinance/yfinance 补充实时行情（可关）。
5. 先建确定性研究模型，再用 LLM 润色（缺 key 则确定性文本兜底）。
6. Tavily 取最新资讯；搜索不可用则用 LLM 兜底摘要。
7. 生成对应类型 PDF。

## 数据架构（双路径并存）

| 路径 | 入口 | 数据源 | token | 实际覆盖 |
|---|---|---|---|---|
| A · TDX 零 token | `run_report.py` | 通达信 MCP 落盘 + AkShare 兜底 | 零 LLM token | ETF（生产）/ A股（PoC）/ 港股·对比（未接） |
| B · Tushare | `run_analysis.py` | Tushare API | 需 `TUSHARE_API_TOKEN` | 股 / 港 / ETF / 对比 全类型 |

- TDX 落盘契约：`tdx_raw/<code>_daily.json`（ETF 日线）、`<code>_quote.json`（实时快照）、`index_pe*.json`（指数 PE 历史）、`peer_etf_fees.json`（同业费率）、`<code>_research.json`（互联网检索）；`fin_<code>.json`（TDX 采集的财务中间结构，喂给 step4/step3 的 `_load` 契约）。
- 零 token 红线：TDX 无源的数据项诚实标「未获取 / 数据不足 / N/A」，绝不编造。

## 与 etf-buy-timing-analysis 的分工

本 skill 与已安装的 `etf-buy-timing-analysis` 在 ETF 上互补、不重叠：

- **股基研究助手（本 skill）**＝**综合研究复盘 PDF 生成器**。覆盖股/港/ETF/对比，强调"理解证据、情景、风险全貌"，**非荐股导向**（用语：研究状态 / 情景区间 / 观察触发器 / 风险复核线，禁用 买入/卖出/仓位建议 等）。核心交付物是结构化深度 PDF。
- **etf-buy-timing-analysis**＝**ETF 买入时机决策层**。直接用 TDX MCP 取数，生成 HTML 报告，给**买入 / 观望 / 回避**评级 + 具体交易计划（入场/止损/目标/仓位）。

推荐组合用法：先用本 skill 出 ETF 研究复盘 PDF（看全貌、定观察框架），再用 `etf-buy-timing-analysis` 出买入时机决策（看当下该不该动手）。前者零 token 结构化、覆盖全类型；后者聚焦 ETF 时机、可含网络检索估值分位。

## Wording And Compliance Rules

Do not ask the LLM to produce a direct buy/sell call.

Use these terms:

- `研究状态`
- `情景区间`
- `观察触发器`
- `风险复核线`
- `研究假设与证据地图`
- `模型研究解读`
- `相对证据排序`

Avoid these terms in report conclusions:

- `买入`
- `卖出`
- `建仓`
- `加仓`
- `减仓`
- `止盈`
- `止损`
- `仓位建议`
- `最佳买点`
- `最佳卖点`
- `必须买入`
- `推荐买入`

Disclaimers may say the report does not constitute investment advice.

## Report Model Rules

For A-share reports, use `analyst_model.py` first. It produces:

- bear/base/bull value scenarios
- valuation safety-margin observation zone, neutral observation zone, high-valuation review zone, and risk review line
- score breakdown across valuation, quality, growth, funds/technical, and risk
- positive evidence, major risks, rebuttal conditions, and observation triggers

For Hong Kong stock reports, use `hk_analyst_model.py` before LLM wording. Include southbound holdings, dividend yield, liquidity, FX risk, HK price-data availability, ADR mapping notes, buyback/dividend clues, and regulatory sensitivity. If HK daily prices are unavailable, do not create price scenario bands.

For ETF reports, use `etf_analyst_model.py`. Treat ETFs as index exposure and allocation research tools, not single-stock trades. Emphasize index valuation, tracking quality, fund size, fees, premium/discount, share changes, liquidity, concentration, and suitable observation framework.

For peer comparison, explain the selection logic. Use industry peers to identify market-cap leaders, quality leaders, valuation anchors, and risk-exposure peers when data exists.

For comparison reports, present relative evidence rankings and metric differences. Do not say one security should be bought or sold.

## Data Permission Notes

- ETF/A股 走 TDX 零 token 路径时，以下所需数据由 TDX 落盘文件（`tdx_raw/`、`fin_<code>.json`）提供，无需 Tushare；TDX 无源项标「未获取」。
- A-share reports need daily bars, daily valuation, income/balance/cash-flow/fina indicators, shareholder, fund-flow, and peer data.
- HK reports deepen when `hk_hold`/southbound, HK financial indicators, and HK daily bars are available. ADR spread and buyback details are currently surfaced as notes or data gaps unless a structured source is added.
- ETF reports need NAV, fund daily bars, index daily bars, fund share, index valuation, and index weights. Industry weights require a future constituent-industry mapping source; until then, use top holding/concentration analysis.

## Free Market Data Fallbacks

**路径 A（TDX 零 token）**：行情用 AkShare 新浪/东财兜底，财务与估值来自 TDX 落盘文件，不依赖 Tushare。

**路径 B（Tushare）**：`ENABLE_FREE_MARKET_DATA=1` 默认开，Tushare 为 truth source（基本面/财务/持仓/指数估值），AkShare/efinance 仅补实时行情字段；Tushare HK/ETF 日线不可用时用 AkShare/yfinance。

If free sources fail, continue the report and mark unavailable fields as `N/A`.

## Failure Handling

- 路径 A 缺 TDX 落盘数据：回退路径 B（若已配 Tushare），否则标「未获取」继续出 PDF；缺 TDX-connector 连接：提示用户连接通达信 MCP。
- Missing `TUSHARE_API_TOKEN`（路径 B）：stop and ask the user to configure `.env`.
- Missing LLM key: continue with deterministic research text.
- Tavily unavailable: either skip internet research or clearly mark LLM fallback.
- Partial data: generate the report, but clearly mark missing fields as `N/A`.
- Multiple inputs: compare up to `MAX_COMPARE_COUNT` securities.

## Key Files

- `run_report.py`: TDX 零 token 报告入口（推荐）。
- `tdx_build_report.py`: TDX 财务采集编排 PoC（落盘 `fin_<code>.json`）。
- `tdx_raw/`: TDX 落盘数据目录（ETF 日线/实时快照/指数 PE/同业费率/研究检索）。
- `fin_<code>.json`: TDX 采集的财务中间结构，喂给 step3/step4 的 `_load` 契约。
- `run_analysis.py`: Tushare 路径统一 CLI 入口（legacy，全类型）。
- `scripts/setup.py`: one-command local setup helper.
- `scripts/check_env.py`: preflight dependency/config checker.
- `docs/INSTALL.md`: installation and troubleshooting guide.
- `docs/AGENT_COMPATIBILITY.md`: compatibility notes for mainstream coding agents and wrappers.
- `analyst_model.py`: A-share deterministic research model.
- `hk_analyst_model.py`: Hong Kong stock deterministic research model.
- `etf_analyst_model.py`: ETF deterministic research model.
- `peer_model.py`: peer leader, valuation anchor, and quality benchmark model.
- `ai_analysis.py`: LLM prompts and fallback research text.
- `pdf_design.py`: shared PDF visual system and cover components.
- `providers/`: data, LLM, and search adapters.
- `providers/free_market_data.py`: optional AkShare/efinance/yfinance fallback helpers.
- `step3_generate_pdf_report.py`: ETF report generator.
- `step4_generate_stock_pdf.py`: A-share report generator.
- `step5_generate_hk_stock_pdf.py`: Hong Kong stock report generator.
- `step6_generate_comparison_pdf.py`: multi-security comparison report generator.

## Repository Hygiene

Never commit `.env`, API keys, tokens, temp JSON files, generated PDFs, preview images, or local caches. `.gitignore` excludes them by default.
