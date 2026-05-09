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
pip install requests pandas matplotlib reportlab numpy python-dotenv --break-system-packages
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
# Edit .env, add your TUSHARE_API_TOKEN and MINIMA_API_KEY
```

> If no Minima API Key is provided, reports will still generate with rule-based quantitative advice instead of AI-powered analysis.

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

## Project Structure

```
securities-analysis-cn/
├── SKILL.md                        # Skill definition (agent entry)
├── run_analysis.py                 # Unified entry script
├── identify_code_type.py           # Code/name parsing & type identification
├── config.py                       # Configuration management
├── ai_analysis.py                  # AI investment advice (MiniMax-M2.7)
├── web_research.py                 # Internet research module (AI events/reports)
├── step1_fetch_real_data.py        # ETF data fetching
├── step1_fetch_stock_data.py       # A-share data fetching (21 APIs)
├── step1_fetch_hk_stock_data.py    # HK stock data fetching (9 APIs)
├── step3_generate_pdf_report.py    # ETF PDF report generation
├── step4_generate_stock_pdf.py     # A-share PDF report generation (16 sections)
├── step5_generate_hk_stock_pdf.py  # HK stock PDF report generation (10 sections)
├── .env.example                    # Environment variable template
└── .gitignore
```

## Data Sources

- **Financial Data**: Xiaodefa Tushare API (A-share 21 APIs / HK 9 APIs / ETF full coverage)
- **AI Advice**: MiniMax-M2.7 model (Anthropic-compatible API)
- **Internet Research**: AI-powered company event, industry dynamics, and analyst opinion collection
- **Macro News**: CCTV News API (央视新闻联播)

## Compatibility

This skill is compatible with:
- **Claude Code** (Anthropic)
- **OpenClaw**
- **Hermes Agent**

Skill entry: `SKILL.md` (YAML frontmatter + Markdown instructions)

## License

MIT License
