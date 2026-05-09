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
pip install requests pandas matplotlib reportlab numpy python-dotenv --break-system-packages
```

## 配置

复制 `.env.example` 为 `.env`，填入 API Key：

```bash
cp .env.example .env
# 编辑 .env，填入 TUSHARE_API_TOKEN 和 MINIMA_API_KEY
```

> 若无 AI API Key，报告仍可生成，AI 建议会降级为规则化量化建议。

### 切换 AI 大模型

默认使用 MiniMax，可在 `.env` 中切换为 OpenAI 兼容服务（支持 GPT、DeepSeek、通义千问等）：

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
OPENAI_API_URL=https://api.openai.com      # 或 https://api.deepseek.com
OPENAI_MODEL=gpt-4o                        # 或 deepseek-chat
```

### 切换搜索引擎

默认使用 AI 知识库总结，可切换为 Tavily 搜索或禁用：

```env
SEARCH_PROVIDER=tavily     # 或 none 禁用
TAVILY_API_KEY=your_key
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

## 插件化架构（Provider Pattern）

三大核心组件均可独立替换，通过 `.env` 配置切换，无需修改代码：

| 组件 | 环境变量 | 可选值 | 说明 |
|------|---------|--------|------|
| 数据源 | `DATA_PROVIDER` | `tushare`（默认） | 行情/财务/股东数据 |
| AI模型 | `LLM_PROVIDER` | `minimax`（默认）、`openai` | 投资建议生成 |
| 搜索引擎 | `SEARCH_PROVIDER` | `ai_summary`（默认）、`tavily`、`none` | 公司研究信息 |

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
