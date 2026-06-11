# securities-analysis-cn

AI Agent Skill：中国证券（A股/港股/ETF）深度分析报告自动生成器。

## 概述

输入任意证券**名称或代码**，自动完成：数据获取 → AI分析 → PDF报告生成。支持多只对比（最多5只）。

支持三大市场：
- **A股**：上交所/深交所股票（如 贵州茅台、比亚迪）
- **港股**：香港联交所（如 腾讯控股、泡泡玛特）
- **ETF**：场内ETF基金（如 沪深300ETF、中证500ETF）

## 安装

```bash
git clone https://github.com/kingqiu/securities-analysis-cn.git
cd securities-analysis-cn
pip install -r requirements.txt
python3 scripts/check_env.py
```

## 配置

复制 `.env.example` 为 `.env`，填入 API Key：

```bash
cp .env.example .env
# 编辑 .env，填入 TUSHARE_API_TOKEN 和 MINIMA_API_KEY
```

> 若无 AI API Key，报告仍可生成，AI 建议会降级为规则化量化建议。

### 最小可运行 Demo

`.env` 配好后，建议先用三类资产各跑一遍：

```bash
python3 run_analysis.py 贵州茅台   # A股
python3 run_analysis.py 腾讯控股   # 港股
python3 run_analysis.py 510300     # ETF
```

如果某些接口权限不足，程序会尽量继续生成报告，并在对应字段显示 `N/A` 或“数据不可用”，不会用大模型补造结构化数据。

## 专业投研模型

A股报告的投资建议不再直接让大模型“拍脑袋”给买卖结论，而是先由 `analyst_model.py` 基于估值、盈利质量、成长性、资金技术面和风险项生成结构化结论：

- 评级与 6-12 个月周期
- 谨慎/中性/乐观价值区间
- 安全边际买入区、观察区、分批止盈区、复盘止损位
- 分批建仓/观察/止盈的仓位计划
- 风险收益比、核心正向证据、主要风险和反证条件

大模型只负责解释该模型结论和组织语言，不应擅自改评级、目标价或交易区间。

同行对比也会通过 `peer_model.py` 识别市值龙头、质量标杆和估值锚，用来判断目标公司相对行业龙头是低估机会，还是基本面折价。

港股报告使用 `hk_analyst_model.py`，额外纳入南向资金、港股流动性、股息率、汇率风险和港股通持仓变化。若数据源缺少港股日线价格，模型不会强行生成买卖价格区间，而会明确标注价格数据不足。

港股增强维度还包括：场内流动性折价、港元/人民币汇率影响、分红/回购线索、ADR/美股映射提示，以及腾讯/阿里/美团等互联网公司的业务分部与监管敏感度。未接入结构化数据的部分会作为“数据缺口”提示，不直接生成结论。

ETF 报告使用 `etf_analyst_model.py`，不套用股票买卖建议，而是输出配置评级、交易评级、定投计划、加仓条件和止盈/再平衡规则，重点关注指数估值分位、跟踪误差、规模流动性、费率和场内溢价折价。

ETF增强维度包括：跟踪误差和日均偏差、溢折率分位、份额申赎趋势、成分集中度、费率成本、是否适合定投/波段/资产配置。当前数据源缺少成分股行业映射，因此行业权重先以“数据缺口 + 成分集中度”呈现，避免硬猜行业暴露。

A股买卖点模型新增交易纪律：近20/60日支撑阻力、均线位置、60日波动率、成交量确认、止损复盘条件，以及稳健/平衡/进取三类风险偏好的仓位节奏。

### 免费行情兜底

主数据源仍是 `.env` 配置的 Tushare 兼容接口；免费源只用于补充交易相关字段：

- A股：补充实时价、涨跌幅、成交额、换手率等；东财全量接口不可用时，自动降级到腾讯单股行情。
- 港股：优先用 AkShare 港股实时行情补充当前价；当 `hk_daily` 权限或频率不足导致日线缺失时，依次用 AkShare、yfinance 港股日线兜底。
- ETF：优先用 efinance/AkShare 补充场内实时价格、涨跌幅、成交额、换手率；当基金日线缺失时，用 AkShare ETF 日线兜底。

可通过 `.env` 设置 `ENABLE_FREE_MARKET_DATA=0` 关闭。免费接口失败不会中断报告，只会在数据包中记录为跳过或失败。

### 切换 AI 大模型

默认使用 MiniMax，可在 `.env` 中切换为 OpenAI 兼容服务（支持 GPT、DeepSeek、通义千问等）：

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
OPENAI_API_URL=https://api.openai.com      # 或 https://api.deepseek.com
OPENAI_MODEL=gpt-4o                        # 或 deepseek-chat
```

### 切换搜索引擎

默认使用 `auto`：优先 Tavily 获取最新公司新闻和行业动态，Tavily 未配置或服务不可用时才降级为 AI 整理；也可以强制禁用：

```env
SEARCH_PROVIDER=auto       # Tavily 优先，AI 降级
TAVILY_API_KEY=your_key
# SEARCH_PROVIDER=none     # 禁用互联网研究
```

## 使用

```bash
python3 run_analysis.py <名称或代码>
```

示例：
```bash
python3 run_analysis.py 贵州茅台       # A股，按名称
python3 run_analysis.py 600519         # A股，按代码
python3 run_analysis.py 腾讯控股       # 港股，按名称
python3 run_analysis.py 00700.HK       # 港股，按代码
python3 run_analysis.py 沪深300ETF     # ETF，按名称
python3 run_analysis.py 510300         # ETF，按代码

# 对比模式（空格分隔多只标的）
python3 run_analysis.py 贵州茅台 五粮液       # A股对比
python3 run_analysis.py 510300 510500         # ETF对比
python3 run_analysis.py 600519 000858 000596  # 多只对比
```

输出 PDF 文件在当前目录：
- 单只：`{名称}_{类型}深度分析报告_{日期}.pdf`
- 对比：`{名称1}_vs_{名称2}_对比分析报告_{日期}.pdf`

## 报告内容（增强版）

### A股报告（16个章节）
1. 公司概况 → 2. AI投资建议 → 3. 股价与估值 → 4. 业绩分析 → 5. 财务健康度（含现金流、资产负债） → 6. 行业可比估值 → 7. 三情景分析 → 8. 主营业务构成（按产品/地区） → 9. 资金面综合分析（主力资金流向/融资融券/股东人数/大宗交易/股权质押） → 10. 分红送股历史 → 11. 业绩预告 → 12. 概念板块与投资题材 → 13. 股东结构 → 14. 公司研究与行业动态（AI互联网研究） → 15. 宏观环境参考 → 16. 审计与合规

### 港股报告（10个章节）
1. 公司概况 → 2. AI投资建议 → 3. 股价走势 → 4. 业绩分析 → 5. 财务健康度 → 6. 现金流质量 → 7. 南向资金持仓分析 → 8. 核心财务指标趋势与分红 → 9. 公司研究与行业动态 → 10. 宏观环境参考

### 股票对比报告（10个章节）
对比概览 → AI对比建议 → 股价走势叠加 → 估值对比 → 成长性对比 → 盈利质量（DuPont） → 财务健康度 → 分红回报 → 资金面 → 综合评分表

### ETF对比报告（10个章节）
基金概览 → AI对比建议 → 净值走势叠加 → 收益率对比 → 风险指标 → 跟踪效率 → 成本对比 → 流动性 → 持仓分析 → 综合评分表

> 💡 对比报告每个章节都配有「说人话」解读，用生活化比喻解释专业指标，金融小白也能看懂。

### 数据维度（A股21项API调用）
基本信息、日线行情、估值指标、利润表、资产负债表、现金流量表、财务指标、前十大股东、行业基准指数、行业可比估值、主营业务构成、分红历史、业绩预告、股东人数、资金流向、融资融券、大宗交易、概念板块、股权质押、审计意见、央视新闻

## 数据权限说明

- **A股**：核心分析依赖日线、估值、三张表、财务指标、资金流、股东、行业同行等接口；概念和宏观新闻默认关闭。
- **港股**：基础报告依赖港股基本信息、财务指标、日线和南向持仓；ADR价差、回购明细目前没有结构化接口，只做映射或线索提示。
- **ETF**：核心分析依赖基金净值、基金日线、指数日线、指数估值、份额、费率、指数权重；行业权重需要额外接入成分股行业映射。
- **Tavily**：用于最新公司新闻和行业动态；Tavily不可用时才允许 AI 降级总结，并会明确标注。

## 插件化架构（Provider Pattern）

三大核心组件均可独立替换，通过 `.env` 配置切换，无需修改代码：

| 组件 | 环境变量 | 可选值 | 说明 |
|------|---------|--------|------|
| 数据源 | `DATA_PROVIDER` | `tushare`（默认） | 行情/财务/股东数据 |
| AI模型 | `LLM_PROVIDER` | `minimax`（默认）、`openai` | 投资建议生成 |
| 搜索引擎 | `SEARCH_PROVIDER` | `auto`（默认）、`tavily`、`ai_summary`、`none` | 公司新闻和行业动态 |

扩展新 provider 只需：继承 `providers/base.py` 中的基类 → 实现接口 → 在 `providers/__init__.py` 注册。

## 文件结构

```
securities-analysis-cn/
├── SKILL.md                        # Skill 定义（agent 入口）
├── run_analysis.py                 # 统一入口脚本
├── config.py                       # 配置管理（Provider 选择 + API 密钥）
├── providers/                      # 插件化适配器
│   ├── base.py                     # 三个抽象基类
│   ├── __init__.py                 # 工厂函数
│   ├── data_tushare.py             # 数据源：小德法 Tushare
│   ├── llm_minimax.py              # LLM：MiniMax-M2.7
│   ├── llm_openai.py               # LLM：OpenAI 兼容（GPT/DeepSeek/通义等）
│   ├── search_ai.py                # 搜索：AI 知识库总结
│   └── search_tavily.py            # 搜索：Tavily API
├── identify_code_type.py           # 代码/名称解析与类型识别
├── ai_analysis.py                  # AI投资建议（通过 LLMProvider）
├── web_research.py                 # 互联网研究（通过 SearchProvider）
├── step1_fetch_real_data.py        # ETF 数据获取
├── step1_fetch_stock_data.py       # A股 数据获取（21项API）
├── step1_fetch_hk_stock_data.py    # 港股 数据获取（9项API）
├── step3_generate_pdf_report.py    # ETF PDF报告生成
├── step4_generate_stock_pdf.py     # A股 PDF报告生成（16章节）
├── step5_generate_hk_stock_pdf.py  # 港股 PDF报告生成（10章节）
├── step6_generate_comparison_pdf.py # 对比分析 PDF（股票10章/ETF10章 + 说人话解读）
├── .env.example                    # 环境变量模板（含所有配置说明）
└── .gitignore
```

## 数据源

- **财务数据**：小德法 Tushare API（A股21项/港股9项/ETF全覆盖），可替换
- **免费行情兜底**：AkShare / efinance / yfinance，用于补充实时行情和港股/ETF日线缺口
- **AI建议**：MiniMax-M2.7（默认），可切换为 OpenAI/DeepSeek/通义千问
- **互联网研究**：AI 知识库总结（默认），可切换为 Tavily 搜索引擎
- **宏观新闻**：央视新闻联播 API

## 兼容性

本 skill 兼容以下 agent 体系：
- **Claude Code** (Anthropic)
- **OpenClaw**
- **Hermes Agent**

Skill 入口：`SKILL.md`（YAML frontmatter + Markdown 指令）

## 许可证

MIT License
