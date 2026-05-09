---
name: securities-analysis-cn
description: >
  自动分析A股、港股、ETF基金，生成专业PDF深度分析报告（含AI买卖建议）。
  支持输入证券代码（510300、600519、00700.HK）或名称（贵州茅台、腾讯控股、沪深300ETF），
  自动识别类型并生成对应报告。使用场景：当用户要求"分析某只股票/基金"、"生成财报分析"、
  "帮我看看XX的投资价值"、"分析A股/港股"、"ETF报告"时触发。
  数据源：小德法Tushare API。AI建议：MiniMax-M2.7模型。
---

# 中国证券深度分析报告生成器

## 执行方式

**一条命令完成全部流程**，在 skill 根目录下运行：

```bash
python3 run_analysis.py <用户输入>
```

`<用户输入>` 可以是：
- 证券代码：`600519`、`00700.HK`、`510300`
- 证券名称：`贵州茅台`、`腾讯控股`、`沪深300ETF`

输出：当前目录下的 PDF 文件，命名格式 `{名称}_{类型}深度分析报告_{日期}.pdf`

## 前置条件

首次使用时安装依赖：

```bash
pip install requests pandas matplotlib reportlab numpy python-dotenv --break-system-packages
```

确认 `.env` 文件存在于 skill 根目录，包含：
```
MINIMA_API_KEY=<key>
```

若 `.env` 不存在或 key 为空，AI 建议会降级为基于规则的量化建议（不影响报告生成）。

## 工作流程

`run_analysis.py` 内部执行四步：

1. **解析输入** → `identify_code_type.resolve_input()` 将名称/代码转为标准 ts_code
2. **识别类型** → `identify_code_type.identify()` 判断 etf / stock / hk_stock
3. **获取数据** → 调用对应 fetcher（Tushare API，约60-120秒）
4. **生成PDF** → 调用对应 generator（reportlab + matplotlib，约20秒）

类型路由：

| 类型 | 数据获取 | PDF生成 |
|------|----------|---------|
| ETF | `step1_fetch_real_data.fetch_all_data()` | `step3_generate_pdf_report.create_etf_pdf()` |
| A股 | `step1_fetch_stock_data.fetch_stock_data()` | `step4_generate_stock_pdf.create_stock_pdf()` |
| 港股 | `step1_fetch_hk_stock_data.fetch_hk_stock_data()` | `step5_generate_hk_stock_pdf.create_hk_stock_pdf()` |

## 报告内容

### ETF报告（9章）
封面 → 投资摘要 → AI买卖建议 → 业绩分析（净值走势图+收益率+跟踪误差） → 持仓分析 → 同类对比 → 规模与流动性 → 费率分析 → 风险提示

### A股报告（9章）
封面 → 公司概况 → AI买卖建议 → 股价走势（vs上证综指） → 业绩分析（营收/利润图） → 财务健康度 → 现金流质量 → 行业可比估值+三情景分析 → 股东结构 → 风险提示

### 港股报告（8章）
封面 → 公司概况 → AI买卖建议 → 股价走势（含MA20/MA60） → 业绩分析 → 财务健康度 → 现金流质量 → 南向资金持仓分析 → 风险提示

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

- API连接失败 → 脚本报错退出，提示检查网络
- 代码无法识别 → 提示用户检查代码或名称
- AI建议调用失败 → 自动降级为规则化建议（不影响报告）

## 配置文件

`config.py` 管理所有配置项，一般无需修改：
- `TUSHARE_API_URL` / `TUSHARE_API_TOKEN`：数据源
- `MINIMA_API_URL` / `MINIMA_MODEL`：AI模型
- `ETF_INDEX_MAP`：ETF→跟踪指数映射
- 评估阈值：`PE_HIGH`、`FEE_EXCELLENT` 等
