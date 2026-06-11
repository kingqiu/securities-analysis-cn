---
name: 股基研究助手
version: 1.0.0
description: 帮普通用户看懂股票、港股和 ETF 的研究框架，生成非荐股导向的中文研究复盘 PDF 报告。
---

# 股基研究助手

帮普通用户看懂股票、港股和 ETF 的研究框架。

Generate PDF research reports for A-shares, Hong Kong stocks, listed ETFs, and multi-security comparisons.

The report is a research-review artifact. It should help the user understand evidence, scenarios, risks, and follow-up observations. It must not be framed as direct investment advice, a buy/sell call, or a best entry/exit point.

## Agent Compatibility

This skill is optimized for Codex-style and Claude Code-style local agents that can read files, run shell commands, install Python dependencies, load `.env`, and write PDF files. For Cursor, Cline, Roo Code, Continue, OpenClaw, Hermes Agent, LangGraph, CrewAI, AutoGen, and similar tools, see `docs/AGENT_COMPATIBILITY.md` before installing or wrapping the CLI.

## Quick Start

Run from the skill directory:

```bash
python3 scripts/setup.py
python3 run_analysis.py <name-or-code>
```

If dependencies are already installed, run:

```bash
python3 scripts/setup.py --skip-install
```

Examples:

```bash
python3 run_analysis.py 贵州茅台
python3 run_analysis.py 600519
python3 run_analysis.py 腾讯控股
python3 run_analysis.py 00700.HK
python3 run_analysis.py 510300
python3 run_analysis.py 贵州茅台 五粮液 泸州老窖
python3 run_analysis.py 510300 510500
```

Outputs are PDF files in the skill directory:

- Single security: `{名称}_{类型}深度分析报告_{日期}.pdf`
- Comparison: `{名称1}_vs_{名称2}_对比分析报告_{日期}.pdf`

## Setup

Recommended setup:

```bash
python3 scripts/setup.py
```

Manual setup:

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 scripts/check_env.py
```

Copy `.env.example` to `.env` and configure:

- `TUSHARE_API_TOKEN`: required for market and financial data.
- `TUSHARE_API_URL`: Tushare-compatible gateway URL.
- `LLM_PROVIDER`: `minimax` or `openai`; optional because reports fall back to deterministic research text.
- `SEARCH_PROVIDER`: `auto`, `tavily`, `ai_summary`, or `none`.
- `TAVILY_API_KEY`: recommended for latest company news and industry dynamics.

Run `python3 scripts/check_env.py` before the first report or when debugging setup.
For installation troubleshooting, see `docs/INSTALL.md`.

## Minimum Demo

After `.env` is configured:

```bash
python3 run_analysis.py 贵州茅台
python3 run_analysis.py 腾讯控股
python3 run_analysis.py 510300
```

If a provider permission is missing, keep the report running when possible and mark the affected fields as `N/A`. Do not invent unavailable data.

## Workflow

1. Resolve input name/code with `identify_code_type.resolve_input()`.
2. Identify security type with `DataProvider.identify_security()`.
3. Fetch market, financial, shareholder, fund-flow, and peer data.
4. Supplement realtime market quotes with free AkShare/efinance/yfinance fallbacks when enabled.
5. Build deterministic research models before LLM wording.
6. Use Tavily first for latest news and industry dynamics; use LLM fallback only when search is unavailable or for summarizing retrieved sources.
7. Generate a PDF with the matching report generator.

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

- A-share reports need daily bars, daily valuation, income/balance/cash-flow/fina indicators, shareholder, fund-flow, and peer data.
- HK reports deepen when `hk_hold`/southbound, HK financial indicators, and HK daily bars are available. ADR spread and buyback details are currently surfaced as notes or data gaps unless a structured source is added.
- ETF reports need NAV, fund daily bars, index daily bars, fund share, index valuation, and index weights. Industry weights require a future constituent-industry mapping source; until then, use top holding/concentration analysis.

## Free Market Data Fallbacks

`ENABLE_FREE_MARKET_DATA=1` is enabled by default. Keep Tushare-compatible data as the source of truth for fundamentals, financials, holdings, and index valuation. Use AkShare/efinance only to supplement realtime quote fields; use AkShare/yfinance only when Tushare HK/ETF daily bars are unavailable.

If free sources fail, continue the report and mark unavailable fields as `N/A`.

## Failure Handling

- Missing `TUSHARE_API_TOKEN`: stop and ask the user to configure `.env`.
- Missing LLM key: continue with deterministic research text.
- Tavily unavailable: either skip internet research or clearly mark LLM fallback.
- Partial data: generate the report, but clearly mark missing fields as `N/A`.
- Multiple inputs: compare up to `MAX_COMPARE_COUNT` securities.

## Key Files

- `run_analysis.py`: unified CLI entry.
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
