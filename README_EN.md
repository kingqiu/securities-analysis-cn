# securities-analysis-cn

AI Agent Skill: Automated Deep Analysis Report Generator for Chinese Securities (A-shares, Hong Kong Stocks, ETFs).

## Overview

Input any security **name or code**, and the system automatically: fetches data → AI analysis → generates PDF report.

Supports three markets:
- **A-shares**: Shanghai/Shenzhen Stock Exchange (e.g., 贵州茅台, 比亚迪)
- **Hong Kong**: HKEX (e.g., 腾讯控股, 泡泡玛特)
- **ETF**: On-exchange ETF funds (e.g., 沪深300ETF, 中证500ETF)

## Installation

```bash
pip install -r requirements.txt
python3 scripts/check_env.py
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
# Edit .env, add your TUSHARE_API_TOKEN and MINIMA_API_KEY
```

> If no AI API Key is provided, reports will still generate with rule-based quantitative advice.

## Analyst Model

A-share recommendations are no longer delegated directly to the LLM. `analyst_model.py` first builds a structured research view from valuation, quality, growth, funds/technical, and risk signals:

- rating with a 6-12 month horizon
- bear/base/bull fair value range
- safety-margin buy zone, watch zone, take-profit zone, and review stop
- position plan for staged entry, observation, or staged exit
- risk/reward, positive evidence, major risks, and rebuttal conditions

The LLM should explain this model output, not override ratings, target prices, or trading zones.

Peer comparison is also handled by `peer_model.py`, which identifies market-cap leaders, quality benchmarks, and valuation anchors to judge whether the target's discount is an opportunity or a fundamental discount.

### Switch AI Model

Default: MiniMax. Switch to any OpenAI-compatible service (GPT, DeepSeek, Qwen, etc.):

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
OPENAI_API_URL=https://api.openai.com      # or https://api.deepseek.com
OPENAI_MODEL=gpt-4o                        # or deepseek-chat
```

### Switch Search Engine

Default: AI knowledge summary. Switch to Tavily search or disable:

```env
SEARCH_PROVIDER=auto       # Tavily first, AI fallback
TAVILY_API_KEY=your_key
# SEARCH_PROVIDER=none     # disable internet research
```

## Usage

```bash
python3 run_analysis.py <name_or_code>
```

Examples:
```bash
python3 run_analysis.py 贵州茅台       # A-share, by name
python3 run_analysis.py 600519         # A-share, by code
python3 run_analysis.py 腾讯控股       # HK stock, by name
python3 run_analysis.py 00700.HK       # HK stock, by code
python3 run_analysis.py 沪深300ETF     # ETF, by name
python3 run_analysis.py 510300         # ETF, by code
```

Output: PDF file in current directory, named `{name}_{type}_report_{date}.pdf`

## Report Contents (Enhanced)

### A-share Report (16 Sections)
1. Company Overview → 2. AI Investment Advice → 3. Price & Valuation → 4. Earnings Analysis → 5. Financial Health (Cash Flow, Balance Sheet) → 6. Industry Comparable Valuation → 7. Three-Scenario Analysis → 8. Revenue Breakdown (by Product/Region) → 9. Capital Flow Analysis (Institutional Flow/Margin Trading/Shareholder Count/Block Trades/Pledges) → 10. Dividend History → 11. Earnings Forecast → 12. Concept Themes → 13. Shareholder Structure → 14. Company Research & Industry Dynamics (AI Internet Research) → 15. Macro Environment → 16. Audit & Compliance

### HK Stock Report (10 Sections)
1. Company Overview → 2. AI Investment Advice → 3. Price Chart → 4. Earnings Analysis → 5. Financial Health → 6. Cash Flow Quality → 7. Southbound Capital Analysis → 8. Key Financial Indicator Trends & Dividends → 9. Company Research & Industry Dynamics → 10. Macro Environment

### Data Dimensions (A-share: 21 API Calls)
Basic info, daily quotes, valuation metrics, income statement, balance sheet, cash flow statement, financial indicators, top 10 shareholders, industry benchmark index, industry peer valuation, revenue composition, dividend history, earnings forecast, shareholder count, capital flow, margin trading, block trades, concept themes, share pledges, audit opinions, CCTV news

## Plugin Architecture (Provider Pattern)

Three core components are independently swappable via `.env` configuration:

| Component | Env Variable | Options | Purpose |
|-----------|-------------|---------|--------|
| Data Source | `DATA_PROVIDER` | `tushare` (default) | Market/financial/shareholder data |
| AI Model | `LLM_PROVIDER` | `minimax` (default), `openai` | Investment advice generation |
| Search | `SEARCH_PROVIDER` | `auto` (default), `tavily`, `ai_summary`, `none` | Company news and industry dynamics |

To add a new provider: inherit from base class in `providers/base.py` → implement interface → register in `providers/__init__.py`.

## Project Structure

```
securities-analysis-cn/
├── SKILL.md                        # Skill definition (agent entry)
├── run_analysis.py                 # Unified entry script
├── config.py                       # Configuration (Provider selection + API keys)
├── providers/                      # Plugin adapters
│   ├── base.py                     # Three abstract base classes
│   ├── __init__.py                 # Factory functions
│   ├── data_tushare.py             # Data: Tushare API
│   ├── llm_minimax.py              # LLM: MiniMax-M2.7
│   ├── llm_openai.py               # LLM: OpenAI compatible (GPT/DeepSeek/Qwen)
│   ├── search_ai.py                # Search: AI knowledge summary
│   └── search_tavily.py            # Search: Tavily API
├── identify_code_type.py           # Code/name parsing & type identification
├── ai_analysis.py                  # AI investment advice (via LLMProvider)
├── web_research.py                 # Internet research (via SearchProvider)
├── step1_fetch_real_data.py        # ETF data fetching
├── step1_fetch_stock_data.py       # A-share data fetching (21 APIs)
├── step1_fetch_hk_stock_data.py    # HK stock data fetching (9 APIs)
├── step3_generate_pdf_report.py    # ETF PDF report generation
├── step4_generate_stock_pdf.py     # A-share PDF report generation (16 sections)
├── step5_generate_hk_stock_pdf.py  # HK stock PDF report generation (10 sections)
├── .env.example                    # Environment variable template (all options documented)
└── .gitignore
```

## Data Sources

- **Financial Data**: Tushare API (A-share 21 APIs / HK 9 APIs / ETF), swappable
- **AI Advice**: MiniMax-M2.7 (default), switchable to OpenAI/DeepSeek/Qwen
- **Internet Research**: AI knowledge summary (default), switchable to Tavily
- **Macro News**: CCTV News API (央视新闻联播)

## Compatibility

This skill is compatible with:
- **Claude Code** (Anthropic)
- **OpenClaw**
- **Hermes Agent**

Skill entry: `SKILL.md` (YAML frontmatter + Markdown instructions)

## License

MIT License
