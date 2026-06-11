# securities-analysis-cn

AI Agent Skill for Chinese securities research-review PDF reports covering A-shares, Hong Kong stocks, ETFs, and multi-security comparisons.

The project fetches data, builds deterministic research models, summarizes source-backed context, and generates PDF reports. Reports are for research review and learning. They do not provide direct buy/sell advice, return promises, or trading instructions.

## Supported Assets

- **A-shares**: Shanghai/Shenzhen stocks, e.g. 贵州茅台, 比亚迪, 600519.
- **Hong Kong stocks**: HKEX stocks, e.g. 腾讯控股, 00700.HK.
- **ETFs / index funds**: exchange-listed ETFs, e.g. 沪深300ETF, 510300.
- **Comparison reports**: compare up to `MAX_COMPARE_COUNT` securities.

## Agent Compatibility

This project is distributed as a `SKILL.md + Python CLI` skill. It is best suited for **OpenAI Codex / Codex Desktop / Codex CLI** and **Claude Code**. Cursor, Cline, Roo Code, Continue, and similar local coding agents can use it as a normal Python CLI project.

OpenClaw, Hermes Agent, LangGraph, CrewAI, and AutoGen usually need light adaptation or a wrapper around `run_analysis.py`. See [docs/AGENT_COMPATIBILITY.md](docs/AGENT_COMPATIBILITY.md).

## Installation

Recommended:

```bash
git clone https://github.com/kingqiu/securities-analysis-cn.git
cd securities-analysis-cn
python3 scripts/setup.py
```

If dependencies are already installed:

```bash
python3 scripts/setup.py --skip-install
```

Manual setup:

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 scripts/check_env.py
```

For troubleshooting, see [docs/INSTALL.md](docs/INSTALL.md).

## Configuration

If `.env` does not exist yet, copy `.env.example` to `.env` and fill in real keys:

```bash
cp .env.example .env
```

Core variables:

- `TUSHARE_API_TOKEN`: structured market, financial, valuation, fund, and holding data.
- `TUSHARE_API_URL`: Tushare-compatible gateway URL.
- `LLM_PROVIDER`: `minimax` or `openai`, used for research commentary.
- `SEARCH_PROVIDER`: default `auto`; Tavily first for latest company news and industry dynamics.
- `TAVILY_API_KEY`: recommended for source-backed web research.

If no LLM key is configured, reports still generate where possible and fall back to deterministic research text. The system does not invent missing structured market or financial data.

## Quick Demo

```bash
python3 run_analysis.py 贵州茅台
python3 run_analysis.py 腾讯控股
python3 run_analysis.py 510300

python3 run_analysis.py 贵州茅台 五粮液
python3 run_analysis.py 510300 510500
```

Output files:

- Single security: `{name}_{type}_report_{date}.pdf`
- Comparison: `{name1}_vs_{name2}_comparison_report_{date}.pdf`

## Report Philosophy

The reports avoid direct trading language. They use:

- **Research hypothesis and evidence map**
- **Scenario bands and observation triggers**
- **Risk review lines**
- **Model research commentary**
- **Relative evidence ranking for comparisons**

The LLM explains deterministic model outputs and retrieved sources. It should not create a buy/sell call or override structured model values.

## A-share Reports

`analyst_model.py` builds a deterministic research view before LLM wording:

- bear/base/bull value scenarios
- valuation safety-margin observation zone, neutral observation zone, high-valuation review zone, and risk review line
- score breakdown across valuation, quality, growth, funds/technical, and risk
- support/resistance, moving-average state, volatility, volume confirmation, and rebuttal conditions
- positive evidence, major risks, and follow-up observation triggers

## Hong Kong Stock Reports

`hk_analyst_model.py` adds Hong Kong-specific dimensions:

- southbound capital holdings and trend
- HK liquidity discount and turnover activity
- HKD/CNY FX impact
- dividend and buyback clues
- ADR / US listing mapping notes
- regulatory sensitivity and business segment breakdown for internet platforms

Missing structured data is shown as a data gap rather than converted into a conclusion.

## ETF Reports

`etf_analyst_model.py` treats ETFs as index exposure and allocation research tools:

- index valuation percentile and exposure
- tracking error and daily tracking bias
- total fee, fund size, amount, turnover
- premium/discount and historical percentile
- share changes, scale trend, and concentration
- core allocation, satellite allocation, periodic observation, and tactical observation frameworks

## Comparison Reports

Comparison reports use the same visual system as single-security reports. They focus on:

- whether the compared securities are truly comparable
- valuation, growth, profitability, financial health, shareholder return, liquidity, and tracking quality
- relative evidence ranking, not trading conclusions

## Search And News

Default `SEARCH_PROVIDER=auto`:

1. Use Tavily first for latest company news, industry dynamics, analyst views, and risk events.
2. Fall back to LLM summarization only when Tavily is unavailable.
3. Filter low-quality titles, disclaimer pages, and broker rating-action words.

## Data Permission Notes

- **A-shares**: daily bars, valuation, income statement, balance sheet, cash flow, financial indicators, fund flow, shareholder, and peer data.
- **HK stocks**: basic info, financial indicators, daily bars, southbound holdings; ADR spread and buyback details are notes or data gaps unless a structured source is added.
- **ETFs**: NAV, fund daily bars, index daily bars, index valuation, fund share, fees, and index weights; industry weights require future constituent-industry mapping.
- **Free fallbacks**: AkShare, efinance, and yfinance supplement realtime quotes or daily gaps only; fundamentals and valuation remain tied to the configured Tushare-compatible source.

## Provider Architecture

| Component | Env Variable | Options | Purpose |
|-----------|--------------|---------|---------|
| Data | `DATA_PROVIDER` | `tushare` | market, financial, shareholder, fund data |
| LLM | `LLM_PROVIDER` | `minimax`, `openai` | research commentary |
| Search | `SEARCH_PROVIDER` | `auto`, `tavily`, `ai_summary`, `none` | company news and industry dynamics |

To add a provider, inherit from `providers/base.py`, implement the interface, and register it in `providers/__init__.py`.

## Project Structure

```text
securities-analysis-cn/
├── SKILL.md                         # Skill entry instructions
├── run_analysis.py                  # Unified CLI
├── config.py                        # Provider and environment config
├── ai_analysis.py                   # LLM prompts and fallback research text
├── analyst_model.py                 # A-share deterministic research model
├── hk_analyst_model.py              # HK deterministic research model
├── etf_analyst_model.py             # ETF deterministic research model
├── peer_model.py                    # Peer leader and valuation-anchor model
├── pdf_design.py                    # Shared PDF visual system
├── providers/                       # Data, LLM, and search adapters
├── step3_generate_pdf_report.py      # ETF PDF
├── step4_generate_stock_pdf.py       # A-share PDF
├── step5_generate_hk_stock_pdf.py    # HK PDF
├── step6_generate_comparison_pdf.py  # Comparison PDF
├── .env.example                     # Environment template
└── .gitignore
```

## Repository Hygiene

Never commit `.env`, API keys, tokens, temp JSON files, generated PDFs, preview images, or local caches. `.gitignore` excludes them by default.

## Disclaimer

This project is for public-data organization, research review, and learning. Outputs may be affected by data gaps, API permissions, delayed quotes, search quality, and model interpretation. Reports do not constitute investment advice, return promises, or trading basis.

## License

MIT License
