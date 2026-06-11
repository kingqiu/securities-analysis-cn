---
name: securities-analysis-cn
description: >
  Generate professional Chinese securities analysis reports for A-shares, Hong Kong stocks, and listed ETFs.
  Use when the user asks to analyze a Chinese stock/ETF, compare multiple securities, assess buy/sell zones,
  review valuation and fundamentals, or generate a PDF investment research report from a ticker or Chinese name
  such as 600519, 贵州茅台, 00700.HK, 腾讯控股, 510300, or 沪深300ETF.
---

# securities-analysis-cn

Generate PDF research reports for A-shares, Hong Kong stocks, and listed ETFs.

## Quick Start

Run from the skill directory:

```bash
python3 scripts/check_env.py
python3 run_analysis.py <name-or-code>
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

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure:

- `TUSHARE_API_TOKEN`: required for market and financial data.
- `LLM_PROVIDER`: `minimax` or `openai`; optional because advice falls back to rule-based analysis.
- `SEARCH_PROVIDER`: `auto`, `tavily`, `ai_summary`, or `none`. Use `auto` by default; it searches Tavily first for latest company news and industry dynamics, then falls back to AI only when Tavily is missing or unavailable.

Run `python3 scripts/check_env.py` before the first report or when debugging setup.

## Workflow

1. Resolve input name/code with `identify_code_type.resolve_input()`.
2. Identify security type with `DataProvider.identify_security()`.
3. Fetch market, financial, shareholder, fund-flow, and peer data.
4. Supplement realtime market quotes with free AkShare/efinance fallbacks when enabled.
5. For A-shares, build a deterministic analyst model before calling the LLM.
6. Build peer-leader context for A-shares when industry peer data is available.
7. Use Tavily first for latest news and industry dynamics; use the LLM only to summarize search results or explain the deterministic model and peer context.
8. Generate the PDF with the matching report generator.

## Recommendation Rules

For A-share reports, do not ask the LLM to invent a buy/sell call directly. Use `analyst_model.py` first. It produces:

- rating and 6-12 month horizon
- bear/base/bull fair value
- safety-margin buy zone, watch zone, take-profit zone, and review stop
- position plan for staged entry, observation, or profit-taking
- score breakdown across valuation, quality, growth, funds/technical, and risk
- positive evidence, major risks, and review triggers

Use “trading plan” language. Avoid deterministic wording such as “best buy point”, “best sell point”, “guaranteed”, or “must buy”.

For Hong Kong stock reports, use `hk_analyst_model.py` before LLM wording. Include southbound holdings, dividend yield, liquidity, FX risk, and HK price-data availability. If HK daily prices are unavailable, do not create buy/sell price zones.

For ETF reports, use `etf_analyst_model.py`. Treat ETFs as allocation tools, not single-stock trades. Produce allocation rating, trading rating, DCA plan, add conditions, and rebalance/take-profit rules from index valuation, tracking quality, fund size, fees, premium/discount, and realtime liquidity fields when available.

## Free Market Data Fallbacks

`ENABLE_FREE_MARKET_DATA=1` is enabled by default. Keep Tushare-compatible data as the source of truth for fundamentals, financials, holdings, and index valuation. Use AkShare/efinance only to supplement realtime quote fields; use AkShare/yfinance only when Tushare HK/ETF daily bars are unavailable. If these free sources fail, continue the report and mark unavailable fields as `N/A`.

For deeper prompt/report changes, read `references/analyst-framework.md`.

## Failure Handling

- Missing `TUSHARE_API_TOKEN`: stop and ask the user to configure `.env`.
- Missing LLM key: continue with deterministic rule-based advice.
- Search provider unavailable: skip internet research and continue.
- Partial data: generate the report, but clearly mark missing fields as `N/A`.
- Multiple inputs: compare up to `MAX_COMPARE_COUNT` securities.

## Key Files

- `run_analysis.py`: unified CLI entry.
- `analyst_model.py`: professional stock rating and trading-plan model.
- `hk_analyst_model.py`: Hong Kong stock rating and trading-plan model.
- `etf_analyst_model.py`: ETF allocation, DCA, and rebalance model.
- `peer_model.py`: peer leader, valuation anchor, and quality benchmark model.
- `ai_analysis.py`: LLM prompts and fallback advice.
- `providers/`: data, LLM, and search adapters.
- `providers/free_market_data.py`: optional AkShare/efinance realtime and daily fallback helpers.
- `step4_generate_stock_pdf.py`: A-share report generator.
- `step5_generate_hk_stock_pdf.py`: Hong Kong stock report generator.
- `step6_generate_comparison_pdf.py`: multi-security comparison report.
