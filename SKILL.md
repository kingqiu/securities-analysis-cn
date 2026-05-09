---
name: securities-analysis-cn
description: >
  自动分析A股、港股、ETF基金，生成专业PDF深度分析报告（含AI买卖建议和互联网研究）。
  支持单只分析和多只对比：输入证券代码（510300、600519、00700.HK）或名称（贵州茅台、腾讯控股），
  自动识别类型。多只输入时自动生成对比分析报告（含综合评分+说人话解读）。
  使用场景：当用户要求"分析某只股票/基金"、"对比XX和YY"、"帮我看看XX的投资价值"时触发。
  插件化架构：数据源、AI模型、搜索引擎均可通过 .env 配置切换。
---

# 中国证券深度分析报告生成器

## 执行方式

**一条命令完成全部流程**，在 skill 根目录下运行：

```bash
python3 run_analysis.py <用户输入>
```

`<用户输入>` 可以是：
- **单只分析**：`600519`、`00700.HK`、`510300`、`贵州茅台`
- **多只对比**：`贵州茅台 五粮液`、`510300 510500`（空格分隔，最多5只）

输出：
- 单只模式 → `{名称}_{类型}深度分析报告_{日期}.pdf`
- 对比模式 → `{名称1}_vs_{名称2}_对比分析报告_{日期}.pdf`

## 前置条件

首次使用时安装依赖：

```bash
pip install requests pandas matplotlib reportlab numpy python-dotenv --break-system-packages
```

确认 `.env` 文件存在于 skill 根目录，至少包含：
```
TUSHARE_API_TOKEN=<token>
MINIMA_API_KEY=<key>
```

- `TUSHARE_API_TOKEN` 必填，否则无法获取数据
- `MINIMA_API_KEY` 可选，为空时 AI 建议降级为规则化量化建议

## 工作流程

`run_analysis.py` 通过 Provider 适配器执行五步：

1. **初始化 Provider** → 根据 `.env` 配置创建 DataProvider / LLMProvider / SearchProvider
2. **解析输入** → `resolve_input()` 将名称/代码转为标准 ts_code
3. **识别类型** → `DataProvider.identify_security()` 判断 etf / stock / hk_stock
4. **获取数据** → `DataProvider.fetch_*()` 调用对应 API（约60-120秒）
5. **互联网研究** → `SearchProvider.search_company()` 获取近期事件/研报（A股/港股）
6. **生成PDF** → 调用对应 generator（reportlab + matplotlib，约20秒）

类型路由：

| 类型 | 数据获取 | 数据维度 | PDF生成 |
|------|----------|----------|---------|
| ETF | `DataProvider.fetch_etf_data()` | 基本+净值+持仓+规模 | `create_etf_pdf()` |
| A股 | `DataProvider.fetch_stock_data()` | 21项API | `create_stock_pdf()` |
| 港股 | `DataProvider.fetch_hk_stock_data()` | 9项API | `create_hk_stock_pdf()` |

## 报告内容

### ETF报告（9章）
封面 → 投资摘要 → AI买卖建议 → 业绩分析（净值走势图+收益率+跟踪误差） → 持仓分析 → 同类对比 → 规模与流动性 → 费率分析 → 风险提示

### A股报告（16章）
1. 公司概况 → 2. AI投资建议（5档评级+操作策略） → 3. 股价与估值（vs上证综指） → 4. 业绩分析（营收/利润图） → 5. 财务健康度（现金流+资产负债） → 6. 行业可比估值 → 7. 三情景分析 → 8. 主营业务构成（按产品/地区） → 9. 资金面综合分析（主力资金流向/融资融券/股东人数/大宗交易/股权质押） → 10. 分红送股历史 → 11. 业绩预告 → 12. 概念板块与投资题材 → 13. 股东结构 → 14. 公司研究与行业动态（AI互联网研究） → 15. 宏观环境参考 → 16. 审计与合规

### 港股报告（10章）
1. 公司概况 → 2. AI投资建议 → 3. 股价走势（含MA20/MA60） → 4. 业绩分析 → 5. 财务健康度 → 6. 现金流质量 → 7. 南向资金持仓分析 → 8. 核心财务指标趋势与分红 → 9. 公司研究与行业动态 → 10. 宏观环境参考

### 股票对比报告（10章）
1. 对比概览（基本面快照表） → 2. AI对比分析建议（通俗语言） → 3. 股价走势叠加（归一化） → 4. 估值对比（PE/PB柱状图） → 5. 成长性对比（营收/净利增速） → 6. 盈利质量对比（DuPont视角） → 7. 财务健康度对比 → 8. 分红与股东回报 → 9. 资金面信号（仅A股） → 10. 综合评分表（★星级+加权得分）

### ETF对比报告（10章）
1. 基金概览 → 2. AI对比分析建议 → 3. 净值走势叠加 → 4. 收益率对比（1月/3月/1年） → 5. 风险指标对比 → 6. 跟踪效率对比 → 7. 成本对比（费率） → 8. 流动性对比 → 9. 持仓分析对比 → 10. 综合评分表

> **「说人话」特色**：对比报告每个章节都配有通俗易懂的解读（用生活化比喻），让金融小白也能看懂。

## 插件化架构（Provider Pattern）

三大核心组件均可通过 `.env` 独立替换，无需修改代码：

| 组件 | 环境变量 | 默认值 | 可选值 |
|------|---------|--------|--------|
| 数据源 | `DATA_PROVIDER` | `tushare` | 可扩展 |
| AI模型 | `LLM_PROVIDER` | `minimax` | `openai`（兼容 GPT/DeepSeek/通义千问） |
| 搜索引擎 | `SEARCH_PROVIDER` | `ai_summary` | `tavily`、`none` |

切换示例（使用 DeepSeek 替代 MiniMax）：
```
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
OPENAI_API_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

扩展新 provider：继承 `providers/base.py` 中的基类 → 实现接口 → 在 `providers/__init__.py` 注册。

## 代码输入规则

| 输入 | 解析结果 |
|------|----------|
| `600519` | → `600519.SH`（6位数字，6/9开头=SH） |
| `300750` | → `300750.SZ`（6位数字，其他=SZ） |
| `510300` | → `510300.SH`（6位数字，5开头=SH） |
| `00700` | → `00700.HK`（≤5位数字=港股） |
| `00700.HK` | → `00700.HK`（已带后缀，直接用） |
| `贵州茅台` | → 搜索 A股→基金→港股，返回匹配代码 |
| `腾讯控股` | → 搜索 A股→基金→港股，返回 `00700.HK` |

## 错误处理

- `TUSHARE_API_TOKEN` 为空 → 数据获取失败，脚本报错退出
- API 连接失败 → 脚本报错退出，提示检查网络
- 代码无法识别 → 提示用户检查代码或名称
- AI 建议调用失败 → 自动降级为规则化建议（不影响报告生成）
- 互联网研究失败/超时 → 自动跳过（不影响报告生成）

## 配置文件

`config.py` 统一管理所有配置，优先从 `.env` 环境变量读取：

**Provider 选择**：`DATA_PROVIDER` / `LLM_PROVIDER` / `SEARCH_PROVIDER`

**数据源**：`TUSHARE_API_URL` / `TUSHARE_API_TOKEN`

**AI模型**：
- MiniMax：`MINIMA_API_URL` / `MINIMA_MODEL` / `MINIMA_API_KEY`
- OpenAI兼容：`OPENAI_API_URL` / `OPENAI_MODEL` / `OPENAI_API_KEY`

**搜索**：`TAVILY_API_KEY`（Tavily 模式时需要）

**业务参数**：`ETF_INDEX_MAP`、`PE_HIGH`、`FEE_EXCELLENT` 等评估阈值
