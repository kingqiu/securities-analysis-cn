# securities-analysis-cn

AI Agent Skill：中国证券（A股/港股/ETF）深度分析报告自动生成器。

## 概述

输入任意证券**名称或代码**，自动完成：数据获取 → AI分析 → PDF报告生成。

支持三大市场：
- **A股**：上交所/深交所股票（如 贵州茅台、比亚迪）
- **港股**：香港联交所（如 腾讯控股、泡泡玛特）
- **ETF**：场内ETF基金（如 沪深300ETF、中证500ETF）

## 安装

```bash
pip install requests pandas matplotlib reportlab numpy python-dotenv --break-system-packages
```

## 配置

复制 `.env.example` 为 `.env`，填入 Minima API Key：

```bash
cp .env.example .env
# 编辑 .env，填入 MINIMA_API_KEY
```

> 若无 API Key，报告仍可生成，AI 建议会降级为规则化量化建议。

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
```

输出 PDF 文件在当前目录，命名格式：`{名称}_{类型}深度分析报告_{日期}.pdf`

## 报告内容（增强版）

### A股报告（16个章节）
1. 公司概况 → 2. AI投资建议 → 3. 股价与估值 → 4. 业绩分析 → 5. 财务健康度（含现金流、资产负债） → 6. 行业可比估值 → 7. 三情景分析 → 8. 主营业务构成（按产品/地区） → 9. 资金面综合分析（主力资金流向/融资融券/股东人数/大宗交易/股权质押） → 10. 分红送股历史 → 11. 业绩预告 → 12. 概念板块与投资题材 → 13. 股东结构 → 14. 公司研究与行业动态（AI互联网研究） → 15. 宏观环境参考 → 16. 审计与合规

### 港股报告（10个章节）
1. 公司概况 → 2. AI投资建议 → 3. 股价走势 → 4. 业绩分析 → 5. 财务健康度 → 6. 现金流质量 → 7. 南向资金持仓分析 → 8. 核心财务指标趋势与分红 → 9. 公司研究与行业动态 → 10. 宏观环境参考

### 数据维度（A股21项API调用）
基本信息、日线行情、估值指标、利润表、资产负债表、现金流量表、财务指标、前十大股东、行业基准指数、行业可比估值、主营业务构成、分红历史、业绩预告、股东人数、资金流向、融资融券、大宗交易、概念板块、股权质押、审计意见、央视新闻

## 文件结构

```
securities-analysis-cn/
├── SKILL.md                        # Skill 定义（agent 入口）
├── run_analysis.py                 # 统一入口脚本
├── identify_code_type.py           # 代码/名称解析与类型识别
├── config.py                       # 配置管理
├── ai_analysis.py                  # AI买卖建议（MiniMax-M2.7）
├── web_research.py                 # 互联网研究模块（AI近期事件/研报）
├── step1_fetch_real_data.py        # ETF 数据获取
├── step1_fetch_stock_data.py       # A股 数据获取（21项API）
├── step1_fetch_hk_stock_data.py    # 港股 数据获取（9项API）
├── step3_generate_pdf_report.py    # ETF PDF报告生成
├── step4_generate_stock_pdf.py     # A股 PDF报告生成（16章节）
├── step5_generate_hk_stock_pdf.py  # 港股 PDF报告生成（10章节）
├── .env.example                    # 环境变量模板
├── .env                            # 实际密钥（不上传）
└── .gitignore
```

## 数据源

- **财务数据**：小德法 Tushare API（A股21项/港股9项/ETF全覆盖）
- **AI建议**：MiniMax-M2.7 模型（Anthropic 兼容 API）
- **互联网研究**：通过 AI 模型获取公司近期事件、行业动态、机构观点
- **宏观新闻**：央视新闻联播 API

## 兼容性

本 skill 兼容以下 agent 体系：
- **Claude Code** (Anthropic)
- **OpenClaw**
- **Hermes Agent**

Skill 入口：`SKILL.md`（YAML frontmatter + Markdown 指令）

## 许可证

MIT License
