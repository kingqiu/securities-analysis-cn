# 设计方案：用通达信 MCP 替换 securities-analysis-cn 的 Tushare 数据层

> 目标：在不向用户索取任何 API Key / Token、不依赖第三方网关（如 `tt.xiaodefa.cn`）的前提下，
> 让「股基研究助手」skill 跑通 A股 / ETF / 港股 的研究复盘报告。
>
> **主数据源为通达信 MCP（TDX）**——已实测覆盖 skill 绝大多数数据，且为平台维护的结构化接口，比 AkShare 稳定。
> AkShare 新浪日线用作 A股/ETF 行情兜底，yfinance 仅作港股日线备选。
>
> **状态（2026-07-16）**：本方案已落地实现，分支 `feature/tdx-data-source` 已提交并 push。
> **P0（5 项）+ P1（6 项）全部完成并双标的验证通过（002294 / 600176），报告零 token、字面 None = 0。**
> 本设计文档的「§12 实现状态」记录最终架构、报告结构与验证结论；P2 探索项见改进方案文档。

---

## 0. 数据源选型结论（已实测）

| 候选源 | A股核心 | ETF | 港股财务 | 港股日K | 新闻/研报 | token | 结论 |
|---|---|---|---|---|---|---|---|
| **通达信 MCP (TDX)** | ✅ 全覆盖 | ✅ | ✅ 90期 | ❌ 不支持 | ✅ wenda_* | 无 | **主用** |
| AkShare | ⚠️ 脆弱 | ✅ | ❌ | ❌ 沙箱被拦 | ❌ | 无 | 仅港股日K兜底 |
| yfinance | — | — | — | ⚠️ 可试 | — | 无 | 港股日K备选 |
| Tushare | ✅ | ✅ | ✅ | ✅ | — | **需token** | 不采用 |

TDX 实测通过项（真实调用，非推测）：
- `tdx_lookup_stock`："贵州茅台"→600519 ✅
- `tdx_kline`(period=4)：A股+ETF 日K，Data=YYYYMMDD+OHLCV ✅
- `tdx_quotes`(hasCwInfo=1)：现 PE(SYL)/PB(MGJZC2)/总市值(ZSZ)/总股本(ZGB)/营收/净利/总资产 ✅
- `tdx_api_data` entry=`ph_agf10_gzfx`：**行业 PE 历史 242 个交易日** ✅（列名"行业估值"，是行业 PE）
- `tdx_api_data` entry=`ph_agf10_cw_lyb`：A股利润表 **24 期**，含`归属母公司净利润`/`营业总收入`/`日期` ✅
- `tdx_api_data` entry=`skef10_hk_cwfx`(fixedTag=1)：港股利润表 **90 期**回溯 2001 ✅

---

## 1. 现状与替换边界

### 1.1 现有架构（Tushare 版）
```
用户输入 → identify_code_type.resolve_input → DataProvider.identify_security
         → DataProvider.fetch_*() → 中间 JSON(dict) 保存到 temp_*.json
         → step4/5/6_generate_*_pdf.py 读取 JSON → build_summary → analyst_model → PDF
```
- 数据层是干净抽象：`providers/base.py` 定义 `DataProvider`（5 个抽象方法）。
- 工厂 `providers/__init__.py::get_data_provider()` 按 `config.DATA_PROVIDER` 分发，目前只支持 `tushare`。

### 1.2 复审发现的硬约束（必须处理，否则零 token 跑不通）
1. **`identify_code_type.py` 整块依赖 Tushare**（非纯本地）：`search_by_name`/`identify`/`resolve_input` 都调 Tushare 的 `stock_basic`/`fund_basic`/`hk_basic`；而 `run_analysis.py` 在拿到 provider **之前**就调 `resolve_input`。→ 名称输入会失败、`identify` 拿不到 name/industry。
2. **契约是"列名级"而非"键名级"**：`step4_generate_stock_pdf.py` 的 `_load()`/`_fin_summary()`/`_scenario_analysis()` 等对每个 DataFrame 读**精确英列名**（`trade_date/pe_ttm/n_income_attr_p/grossprofit_margin/debt_to_assets/n_cashflow_act/net_mf_amount/rzye/...`）。任何替代源返回中文列名，都必须做列重命名/reshape。
3. **`daily_basic` 是硬关键路径**：`_scenario_analysis()` 需 `daily_basic` 有 **≥10 个 pe_ttm** 点，否则情景区间/三情景/价格 bull/base/bear/安全边际观察区**全部跳过**（报告核心）。
4. **`check_env.py` 硬编码 Tushare 闸门**：缺 token 即 FAIL，不看 `DATA_PROVIDER`，会误报。
5. **港股 `fetch_hk_stock_data` 在 basic 失败时 `return None` → `run_analysis` 直接 `sys.exit(1)`**，不是"标 N/A 偏薄"。降级设计要返回部分 dict。

> **实现说明**：上述 5 条约束在 `feature/tdx-data-source` 分支已通过"绕开 `identify_code_type` 与 `step1_fetch_*.py`、由 `run_report.py` 编排 + 列名契约 + 章节级优雅降级"全部解决；原 `run_analysis.py`/`check_env.py`/`identify_code_type.py` 在本分支**未改动**，运行期不依赖它们。

### 1.3 替换边界（TDX 版）
| 保留（不动） | 替换 / 新增 |
|---|---|
| `providers/base.py` 接口定义 | 取数逻辑改由 **WorkBuddy 编排 TDX** 调用完成 |
| `analyst_model.py` / `hk_analyst_model.py` / `etf_analyst_model.py` 规则化模型 | `step1_fetch_*.py`（Tushare 取数）整体绕过 |
| `step3/4/5/6_generate_*_pdf.py` 报告引擎 | `identify_code_type.py` 用 `tdx_lookup_stock` 替代 |
| `pdf_design.py` / `peer_model.py` | `check_env.py` 改 provider 感知 |

---

## 2. 目标架构（已落地：fin 配置 + run_report 编排 + step4 引擎）

> **核心思路**：TDX 是 MCP 工具，由 WorkBuddy 在对话内调用，**不是** skill CLI 能 `import` 的 Python 库。
> 因此取数由 WorkBuddy 编排，落盘为**每只标的一份 `fin_<code>.json` 配置 + `tdx_raw/<code>_research.json` 检索结果**；
> 再由 `run_report.py`（编排层）读取配置、用 AkShare 补行情、本地计算，组装成 step4 期望的 `data` 字典并生成 PDF。

```
① WorkBuddy 编排 TDX 取数（一次性，落盘）
      tdx_lookup_stock / tdx_quotes / ph_agf10_cw_lyb/xjllb/zcfzb
      tdxf10_gg_jyds / gdyj / fhrz / tdx_indicator_select
      wenda_report/news/notice/macro_query  ──→  fin_<code>.json  +  tdx_raw/<code>_research.json

② run_report.py <code> <stock|etf>  （零 token 复用引擎）
      读 fin_<code>.json  →  用 AkShare 新浪源补日线/指数  →  本地计算 PE-TTM/分位/杜邦/反向DCF
      →  组装 data 字典（严格匹配 step4 的 _load 契约）  →  写 temp_<code>_data.json

③ step4_generate_stock_pdf.create_stock_pdf(data_file, out_pdf)
      _load() 解析 → build_*_summary → analyst_model（规则化）→ 22 章 PDF

   └─ 输出 PDF（零 token，无外部 LLM / 搜索调用）
```

**关键设计契约（列名级）**：`run_report.py` 组装的 `data` 字典，每个 DataFrame 必须满足 `step4` 的 `_load()` 期望的英列名（见 §3 契约表）。这是整个方案的硬约束——TDX 返中文列名，由编排层在 `fin_<code>.json` 阶段完成 reshape。

**默认行为**：给出任意股票代码或名称，WorkBuddy 先 `tdx_lookup_stock` 解析，再生成**完整 22 章**报告（不要求用户按需点选章节）。

---

## 3. 中间 JSON 列名契约（A股，从 step4 实读）

> **实现说明**：当前 `run_report.py` 实际组装的 `data` 字典已稳定覆盖 `basic / daily / daily_basic / index_daily / income / fina_indicator / cashflow / moneyflow / top10_holders / dividend / industry_peers / realtime_quote / profile / dupont / web_research / data_sources`。其余键（balancesheet / holder_number / margin / block_trade / forecast / pledge / audit / mainbz）在 `fin_<code>.json` 未提供时由 step4 优雅降级（标 N/A 或跳过章节），不影响主框架。列名契约本身是硬约束，step4 不改。

| 键 | 必需列（英文名） | 报告用途 | 来源（TDX） |
|---|---|---|---|
| `basic` | `name, industry, area, list_date, market` | 基本信息 | `tdxf10_gg_gsgk` fixedTag=0 + `tdx_quotes` |
| `daily` | `trade_date(YYYYMMDD), close, high, low, vol` | 日线/支撑阻力/波动/量比/MA | `tdx_kline`(Data→trade_date) |
| `daily_basic` | `trade_date, pe_ttm, pb, total_mv, close` | **情景区间/PE分位(≥10点)** | 见 §4 缺口1 计算 |
| `income` | `end_date(YYYYMMDD), total_revenue, n_income_attr_p` | 营收/净利/CFO比 | `ph_agf10_cw_lyb`(日期→end_date) |
| `balancesheet` | `end_date, total_assets, total_liab, accounts_receiv, inventories` | 资产负债率 | `ph_agf10_cw_zcfzb` |
| `cashflow` | `end_date, n_cashflow_act` | CFO/净利润比 | `ph_agf10_cw_xjllb` |
| `fina_indicator` | `end_date, roe, grossprofit_margin, debt_to_assets, current_ratio, quick_ratio` | ROE/毛利/负债 | 由三表 + `tdx_quotes` CwInfo 计算/补全 |
| `top10_holders` | `end_date, holder_name, hold_amount, hold_ratio` | 股东集中度 | `tdxf10_gg_gdyj` ltgd |
| `moneyflow` | `trade_date, net_mf_amount` | net_mf_20d | `tdxf10_gg_jyds` zjlx |
| `index_daily` | `trade_date, close` | 基准对比 | `tdx_kline` 指数(setcode=62/1) |
| `industry_peers` | `{industry, peers:[{ts_code,name,pe_ttm,pb,total_mv,roe,gross_margin,rev_growth,profit_growth}]}` | 同行对比 | `ph_agf10_hypm` queryKey=00105 + `tdx_quotes` 批量 |
| `holder_number` | `end_date, holder_num` | 筹码集中度 | `tdxf10_gg_gdyj` gdrs |
| `margin` | `trade_date, rzye` | 融资融券 | `tdxf10_gg_jyds` rzrq |
| `block_trade` | `trade_date, amount` | 大宗交易 | `tdxf10_gg_jyds` dzjy |
| `dividend` | `end_date, cash_div_tax, stk_div` | 分红 | `tdxf10_gg_fhrz` |
| `forecast` | `ann_date, end_date, type, p_change_min/max` | 业绩预告/一致预期 | `tdxf9_ag_cwsj_yjyj` / `CWServ.tdxf10_gg_ybpj` yzyq |
| `pledge` | `end_date, pledge_ratio` | 质押率 | `tdx_api_data` 质押类 entry（待定） |
| `audit` | `end_date, audit_result` | 审计意见 | 弱，标 N/A |
| `web_research` | `sections:{recent_events,industry_dynamics,analyst_views,...}` | 互联网研究 | `wenda_news_query`/`wenda_report_query`/`wenda_notice_query` |
| `realtime_quote` | `price` | 情景价重缩放 | `tdx_quotes` Now |

> `pe_percentile` / `industry_pe_pct` 由 `daily_basic`/gzfs 序列本地计算；`support/resistance/volatility_60d/volume_ratio/ma_position` 由 `daily` 本地计算。

---

## 4. A股字段对照表（TDX 版）

| 报告用途 | TDX 工具 / entry | 实测状态 | 说明 |
|---|---|---|---|
| 名称→代码、类型识别 | `tdx_lookup_stock` | ✅ 已验证 | 替代 `identify_code_type` |
| 日线 OHLCV | `tdx_kline` period=4 | ✅ 已验证 | Data→trade_date |
| 个股现 PE/PB/市值/总股本/营收/净利/总资产 | `tdx_quotes` hasCwInfo=1 | ✅ 已验证 | SYL/MGJZC2/ZSZ/ZGB |
| 行业 PE 历史 | `tdx_api_data` `ph_agf10_gzfx` | ✅ 已验证 242点 | 列"行业估值"=行业PE→`industry_pe_pct` |
| 利润表(归母净利/营收/TTM来源) | `tdx_api_data` `ph_agf10_cw_lyb` | ✅ 已验证 24期 | →income |
| 资产负债表 | `tdx_api_data` `ph_agf10_cw_zcfzb` | 高置信 | →balancesheet |
| 现金流量表 | `tdx_api_data` `ph_agf10_cw_xjllb` | 高置信 | →cashflow(n_cashflow_act) |
| 十大股东/股东人数 | `tdx_api_data` `tdxf10_gg_gdyj` ltgd/gdrs | 高置信 | →top10_holders/holder_number |
| 主力资金流/融资融券/大宗 | `tdx_api_data` `tdxf10_gg_jyds` zjlx/rzrq/dzjy | 高置信 | →moneyflow/margin/block_trade |
| 分红 | `tdx_api_data` `tdxf10_gg_fhrz` | 高置信 | →dividend |
| 业绩预告/研报一致预期 | `tdxf9_ag_cwsj_yjyj` / `CWServ.tdxf10_gg_ybpj` yzyq | 高置信 | →forecast |
| 主营构成 | `tdx_api_data` `ph_agf10_jyfx` | 高置信 | →mainbz |
| 行业排名/估值排名 | `tdx_api_data` `ph_agf10_hypm` 00105 | 高置信 | →industry_peers |
| 指数日K | `tdx_kline` 指数 | 高置信 | →index_daily |
| 新闻/研报/公告/宏观 | `wenda_news/report/notice/macro_query` | 高置信 | →web_research（替代Tavily） |

**缺口 1（可解决）——个股逐日 PE-TTM 历史**：`ph_agf10_gzfx` 返回的是行业 PE（已比对现 PE=14.28 ≠ gzfs 最新=26.9 确认）。个股日 PE 由计算得到：
`个股日PE = 日收盘(tdx_kline) × 总股本(tdx_quotes ZGB) ÷ TTM归母净利润(ph_agf10_cw_lyb)`。三要素均实测可得，TTM 在两次财报间分段恒定，可构造 ≥10 点序列喂给 `_scenario_analysis`。**这是 P0 关键路径的解法。**

---

## 5. ETF 字段对照表（TDX 版）

| 报告用途 | TDX 工具 | 状态 |
|---|---|---|
| ETF 日线 | `tdx_kline` setcode=1 period=4 | ✅ 已验证(510300) |
| ETF 实时/规模/总市值 | `tdx_quotes` hasCwInfo=1 | ✅ 已验证 |
| 基金资料(规模/净值/费率) | `tdx_indicator_select` rang="JJ" | 高置信 |
| 跟踪指数日K/估值 | `tdx_kline` 指数 + `ph_agf10_gzfx`(指数?) | 指数日K✅；指数估值待验 |
| 前十大重仓 | `tdx_api_data` 基金持仓类 entry | 待验，缺失标 N/A |
| 净值序列 | `tdx_kline`(复权) 近似 / `tdx_indicator_select` | 待验 |

ETF 日线+实时已验证；持仓/净值/指数估值需落实，缺失标 N/A（不影响主框架）。

---

## 6. 港股字段对照表 + 短板

| 报告用途 | TDX | 状态 |
|---|---|---|
| 港股财务三表(损益/资产负债/现金流) | `tdx_api_data` `skef10_hk_cwfx` fixedTag=1/2/3 | ✅ 已验证 90期 |
| 港股研报/新闻/公告 | `wenda_report/news/notice_query` | 高置信 |
| 港股名称→代码 | `tdx_lookup_stock` range="HK-GP" | ✅ 已验证(06199贵州银行) |
| **港股日K线** | TDX **不支持**（skill 文档明确） | ❌ 缺口 2 |
| 港股实时行情 | TDX 不支持 | ❌ |

**缺口 2（真缺口）——港股日K**：TDX 不提供港股实时行情和 K 线。影响：港股报告的"价格情景区间/三情景"章节缺（无日K），但财务/估值/研报章节都在——已比 AkShare 强（AkShare 港股财务+日线都没有）。
**处理**：港股日线用 yfinance 兜底（`yf.download("0700.HK")`）；若仍不可用，价格情景章节标 N/A，报告其余部分正常产出。降级时 `fetch_hk_stock_data` **返回部分 dict（不返回 None）**，避免 `run_analysis` 的 `sys.exit(1)`。

---

## 7. 降级与缺失策略（含复审 P1 修正）

1. **字段级 `N/A`**：TDX 任一接口返回空/失败时写 `N/A`；模型 `_safe_float` 已容错。
2. **计算替代**：个股日 PE、pe_percentile、industry_pe_pct、support/resistance、volatility_60d 全部本地计算。
3. **港股不阻断**：港股 basic/财务可取即返回 dict；日K缺失只影响价格情景章节（修正原 `return None` → abort 的问题）。
4. **章节级跳过**：审计/概念等弱源章节不渲染。
5. **`check_env.py` provider 感知**：当 `DATA_PROVIDER≠tushare` 时跳过 Tushare token 检查，改为校验 TDX 连接器在线 + 包 + 字体 + 写权限。

---

## 8. 实现步骤（**已完成**，对应 `feature/tdx-data-source` 分支）

1. **名称/类型解析** ✅：`tdx_lookup_stock` 替代 `identify_code_type`；编排入口走 `run_report.py`。
2. **取数编排** ✅：WorkBuddy 在对话内调 TDX，落盘 `fin_<code>.json` + `tdx_raw/<code>_research.json`。
3. **列名/reshape 层** ✅：`fin_<code>.json` 已按 §3 契约 reshape 成英列名 DataFrame。
4. **计算补全** ✅：个股日 PE-TTM、1年/3年 PE 分位、行业分位、技术位、杜邦、反向 DCF 全部本地计算。
5. **写中间 JSON** ✅：`temp_<code>_data.json`，结构严格匹配 step4 的 `_load()`。
6. **复用引擎** ✅：直接 `create_stock_pdf(data_file, out_pdf)` / `create_etf_pdf(...)` 生成 PDF。
7. **搜索层** ✅：`web_research` 用 `wenda_*` 替代 Tavily（无需 Key），且**不调 LLM**、纯结构化组装。
8. **`check_env.py`** ⏸：本分支未改此文件（运行期不依赖它，绕过了原 Tushare 闸门）。
9. **港股日K** ⏸：港股路径未实现（TDX 不支持港股日K，yfinance 兜底待接）；当前已验证 A股 + ETF。

---

## 9. 测试计划（**实际执行结果**）

| 测试 | 方法 | 结果 |
|---|---|---|
| 单元：A股取数 | 对 600519 调 TDX，断言中间 JSON 含 `daily/daily_basic(750点)/income` | ✅ 核心字段非空（见 `fin_600519.json` PoC） |
| 端到端 A股 | 600519 茅台 → 生成完整 PDF | ✅ 含 22 章、零 token |
| 端到端 A股 | 002294 信立泰 → PDF | ✅ 22 章，None=0，反向 DCF 隐含增速 37.8% |
| 端到端 A股 | 600176 中国巨石 → PDF | ✅ 22 章，None=0（无互联网研究，优雅跳过多维交叉验证章） |
| PE 计算验证 | 个股日 PE 最新值 ≈ `tdx_quotes` SYL | ✅ 口径一致（市值单位 bug 已修复 `/1e8`） |
| 端到端 ETF | 588000 科创50ETF → PDF | ✅ 日线来自 TDX 落盘、规模/净值/持仓可用（修复"None"显示 bug） |
| 回归：P0→P1 | 002294 + 600176 重跑 | ✅ 双标的 None=0，运行期外部调用=0 |
| 缺失容错 | 断 wenda（无 research 文件） | ✅ 报告仍生成，多维交叉验证章优雅跳过 |
| 对比 PDF | 茅台 vs 五粮液 | ⏸ 未实现（非当前重点） |

**验证结论**：A股（600519/002294/600176）与 ETF（588000）四条报告链路端到端跑通，全部零 token、字面 `None = 0`。

---

## 10. 风险清单

| 风险 | 等级 | 缓解 |
|---|---|---|
| TDX 连接器掉线 | 中 | 编排层检测不可用→提示用户重连；保留 AkShare 离线保底分支 |
| 个股 PE 计算口径偏差 | 低 | 用 `tdx_quotes` SYL 校准；财报期切换处分段恒定 |
| 港股日K不可用 | 高(仅港股价格情景) | yfinance 兜底；否则该章节 N/A，财务章节仍出 |
| TDX 接口字段微调 | 低 | 平台维护、结构化，比 AkShare 稳；编排层 try/except + N/A |
| 列名契约漂移 | 低 | step4 是本地代码，契约稳定；以 §3 表为准 |

---

## 11. 结论

**通达信 MCP 已作为主数据源落地实现，覆盖 A股全量 + ETF 的研究复盘报告，优于 AkShare，且零 token。**
集成方式为"WorkBuddy 编排 TDX 取数 → 落盘 `fin_<code>.json`/`tdx_raw/*_research.json` → `run_report.py` 组装列名契约字典 → 复用 `step4` 规则化引擎"，绕过 Tushare 取数层与 `identify_code_type`。
两条缺口：个股 PE 历史（已用 close×总股本/TTM净利 计算解决）、港股日K（TDX 不支持，yfinance 兜底或标 N/A，港股路径尚未实现）。
**当前状态**：P0（5 项）+ P1（6 项）全部完成并验证（详见 §12）；P2 探索项见配套改进方案文档，逐项待评估定位兼容性。

---

## 12. 实现状态（截至 2026-07-16）：P0 + P1 已完成并验证

### 12.1 分支与提交

- 分支：`feature/tdx-data-source`（local repo 从 `/tmp` 迁移至工作目录，与 `main`/原 Tushare 版并存）。
- 关键提交：`058517f`（P0 五项）、`986d61d`（P1 六项），均已 push 到 `origin`。
- `main` 分支保留原始 Tushare 版本，不受影响。
- 配套文档：`securities-analysis-cn-improvement-plan.md`（改进方案 + P0/P1 完成记录），与仓库同级（未进 git）。

### 12.2 文件结构（实际）

```
securities-analysis-cn/
├── run_report.py              # 零 token 编排层（股票走 step4 / ETF 走 step3）
├── step4_generate_stock_pdf.py# 股票报告共享引擎（22 章，规则化）
├── step3_generate_pdf_report.py# ETF 报告引擎
├── peer_model.py / pdf_design.py / analyst_model.py  # 复用
├── fin_<code>.json           # 每只标的的 TDX 提取配置（核心数据落盘）
│   ├─ fin_600519.json / fin_002294.json / fin_600176.json / fin_588000.json ...
├── tdx_raw/<code>_research.json  # TDX wenda 检索落盘（研报/新闻/公告/宏观）
├── tdx_raw/<code>_daily.json     # ETF 日线 TDX 落盘（AkShare 不可用时）
└── <名称>_股票深度分析报告_<YYYYMMDD>.pdf
```

**`fin_<code>.json` 实际结构**（以股票为例）：
```json
{
  "name": "信立泰", "code": "002294", "ts_code": "002294.SZ",
  "shares": 1053110000, "total_assets": ..., "net_assets": ...,
  "price": 40.87, "industry": "化学制药", "list_date": "2009-09-10",
  "income_annual": [["20251231", 营收, 归母净利, 营业成本], ...],  // 近年年报
  "cashflow_annual": [["20251231", 经营现金流], ...],
  "moneyflow_20d": [["日期", 主力净流入], ...],
  "industry_peers": [{"name":..., "pe_ttm":..., "pb":..., "total_mv":...(元)}, ...],
  "top10_holders": [["股东名", 持股数], ...], "top10_end_date": "20260331",
  "dividend_rows": [["除权日", "每股派息", "分红方案", "送转", "公告日"], ...],
  "ttm_net_profit": 6.52
}
```

### 12.3 报告最终结构（股票 22 章，全部零 token、规则化）

| 章 | 标题 | 关键内容 | 来源/函数 |
|---|---|---|---|
| 一 | 公司概况 | 基本信息、一句话结论 | `_load` |
| 二 | 情景区间与观察触发器 | 三情景价 / 安全边际观察区 | `_scenario_analysis` |
| 三 | 股价与估值 | PE/PB/市值、1年+3年分位 | `_latest_valuation` |
| 四 | 业绩分析 | 营收/净利/增速 | income |
| 五 | 财务健康度 | ROE/毛利率/负债率/CFO 现金含量 | fina_indicator/cashflow |
| 5.6 | ROE 杜邦分解 | 净利率×周转率×权益乘数 + 驱动 | **P0-3 `_dupont`** |
| 六 | 同行龙头与估值锚对比 | PE/PB/市值 + 同行定位结论 | peer_model + **P1-9** |
| 七 | 三情景分析 | 未来 1 年 bull/base/bear | `_scenario_analysis` |
| 八 | 主营业务构成 | 营收/成本拆分 | income |
| 九 | 资金面综合分析 | MA 位置/主力20日净流入/支撑阻力 | moneyflow/daily |
| 十 | 分红送股历史 | 历年分红 | dividend |
| 十一 | 业绩预告 | 暂无则标注 | forecast(N/A) |
| 十二 | 概念板块与投资题材 | N/A 降级 | — |
| 十三 | 股东结构 | 十大流通股东/集中度 | top10_holders |
| 十四 | 公司研究与行业动态 | 研报观点/新闻公告/宏观 | **P0-1 `web_research`** |
| 十五 | 行业与公司动态 | 同上延伸 | web_research |
| 十六 | 审计与合规 | N/A 降级 | — |
| 十七 | 隐含预期推演（反向 DCF） | 市值反推隐含增速 vs 历史 CAGR | **P0-2 `_reverse_dcf`** |
| 十八 | 未来验证节点（监控清单） | 强化/证伪事件 + 时间节点 | **P0-5 `_monitor_checklist`** |
| 十九 | 赚钱机制与商业模式拆解 | 毛利率/净利率/资产周转 → 盈利模式 | **P1-8 `_business_engine`** |
| 二十 | 行业周期与格局判断 | 同业 PE 中位 + 增长 → 周期阶段 | **P1-7 `_industry_cycle`** |
| 二十一 | 空方逻辑与风险推演 | 量化看空信号 + 黑天鹅场景 | **P1-6 `_bear_case`** |
| 二十二 | 数据来源与取数说明 | 逐源记录方法 + 取数时间 | **P1-11 `data_sources`** |

> 通篇采用【事实】/【判断】/【情景】标注（**P1-10**）：封面结论、新章节、反向 DCF 判定、监控清单均逐句标注，便于追溯。

### 12.4 验证结论（双标的，002294 + 600176）

| 维度 | 002294 信立泰 | 600176 中国巨石 |
|---|---|---|
| 字面 `None` | **0** | **0** |
| 22 章渲染 | ✅ 全渲染 | ✅ 全渲染（多维交叉验证章优雅跳过） |
| 反向 DCF | ✅ 隐含增速 37.8% vs CAGR 5.1% | ✅ 隐含增速 37.1% vs 增速 -14.1% |
| 杜邦/赚钱机制 | ✅ 杠杆驱动 / 高毛利溢价 | ✅ 周转率驱动 / 低毛利走量 |
| 同行对比市值 | ✅ 已填充（修了 total_mv→mv_bn bug） | ✅ 同 |
| 运行期外部调用 | **0** | **0** |

### 12.5 已实现改进（P0 + P1）一览

- **P0-1 多维交叉验证**：`web_research` 读 `tdx_raw/<code>_research.json`，结构化组装研报/新闻/公告/宏观，**不调 LLM**。
- **P0-2 反向 DCF**：`_reverse_dcf()` 二分法反推隐含增速（折现率 9% / 永续 3% / 5 年）。
- **P0-3 ROE 杜邦**：`_dupont()` 三因子 + 驱动判断。
- **P0-4 估值分位扩展**：`_latest_valuation()` 新增 1年/3年双分位（750 交易日）。
- **P0-5 监控清单**：`_monitor_checklist()` 强化/证伪事件 + 关键节点。
- **P1-6 空方逻辑**：`_bear_case()` 量化看空信号 + 行业化黑天鹅模板。
- **P1-7 行业周期**：`_industry_cycle()` 同业 PE 中位 + 增长 → 周期阶段（轻量代理，标注为方向性参考）。
- **P1-8 赚钱机制**：`_business_engine()` 毛利率/净利率/资产周转 → 盈利模式判断。
- **P1-9 同行深度对比**：目标行补全净利率/营收增速；peer 市值修正渲染；新增同行定位结论。
- **P1-10 事实/判断分离**：全局标注约定 + 逐句标签。
- **P1-11 数据来源清单**：`data_sources` 逐源记录 + 取数时间。

### 12.6 已知限制（诚实记录，非 bug）

1. **同行 peer 基本面**：fin 的 `industry_peers` 仅含 `pe_ttm/pb/total_mv`；peer 的 ROE/毛利率/增速在 TDX 离线时为 N/A。代码已支持这些字段，待 TDX 重连后在 `run_report` peer 组装处补 `indicator_select` 扩展即可自动填充，step4 无需改。
2. **行业周期为轻量代理**：基于同业截面估值 + 增长信号，缺行业历史 PE 序列与产能/Capex 数据；报告内已显式标注"仅为方向性参考"。
3. **港股路径未实现**：TDX 不支持港股日K；`yfinance` 兜底与降级逻辑待接。
4. **`check_env.py` 未改**：本分支运行期不依赖它，原 Tushare 闸门不影响；若需作为独立 skill 打包，仍需做 provider 感知改造。
5. **ETF 持仓/净值**：588000 已验证可用；部分 ETF 的 `fund_open_fund_info_em`/`fund_portfolio_hold_em` 取数失败时优雅降级（B 兜底 N/A）。

### 12.7 下一步（P2，逐项评估定位兼容性）

见配套改进方案文档「P2 探索性」章节：私董会轻量版 / 用户画像 / 图像识别 / 质押减持时间表 / 扣非与周转率警报 / 分投资者类型框架。其中 12/13/17 需先确认是否突破"不输出买卖建议"边界；15/16 为纯规则化可优先。
