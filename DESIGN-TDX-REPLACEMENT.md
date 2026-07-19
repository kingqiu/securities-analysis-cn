# 设计方案：用通达信 MCP 替换 securities-analysis-cn 的 Tushare 数据层

> 目标：在不向用户索取任何 API Key / Token、不依赖第三方网关（如 `tt.xiaodefa.cn`）的前提下，
> 让「股基研究助手」skill 跑通 A股 / ETF / 港股 的研究复盘报告。
>
> **主数据源为通达信 MCP（TDX）**——已实测覆盖 skill 绝大多数数据，且为平台维护的结构化接口，比 AkShare 稳定。
> AkShare 新浪日线用作 A股/ETF 行情兜底，yfinance 仅作港股日线备选。
>
> **状态（2026-07-18）**：本方案已落地实现，分支 `feature/tdx-data-source` 已提交并 push。
> **P0（5 项）+ P1（6 项）全部完成并双标的验证通过（002294 / 600176），报告零 token、字面 None = 0。**
> **可读性层（5 项）已落地于工作区（`step4` 改造，待提交）**，详见「§13 可读性层设计」。
> 本设计文档记录最终架构、报告结构与全部改进（P0 / P1 / 可读性）的实现状态；P2 探索项六项（12-17）的正式设计见「§14 P2 探索项正式设计」。

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
6. **可读性层已提交**：§13 的五项可读性改造已合入分支（commit `6c79bf0`），双标的复验通过（None=0、信号灯 `●` 各 22 个）；「财务健康度」小结 `health_notes` 已统一为 `_signal_text` 彩色 `●` 风格，风格不一致已消除。

### 12.7 下一步（P2，逐项评估定位兼容性）

配套改进方案文档「P2 探索性」章节列出六项：私董会轻量版(12) / 用户画像(13) / 图像识别(14) / 质押减持时间表(15) / 扣非与周转率警报(16) / 分投资者类型框架(17)。

其中 **12 / 13 / 14 / 15 / 16 / 17 六项已全部在本文档 §14 展开为正式设计**（含数据契约、函数签名、渲染方案、定位边界与可行性；15/16 的可行性标注为"中"，待 TDX 重连后实测接口/明细字段再落地实现）。

---

## 13. 可读性层设计（面向非专业用户，已落地并提交 `6c79bf0`）

> **背景**：报告数值专业、术语密集，普通用户读不懂数值含义（ROE 7.3% 是好是坏？CFO/净利润比是什么？）。本层在**不引入 LLM、不改变数据层**的前提下，通过"信号灯 + 术语释义 + 一页纸摘要 + 章节导语 + 白话封面"把专业数据翻译成普通人能看懂的信号。全部为规则化（零 token），位于 `step4_generate_stock_pdf.py`。

### 13.1 五项改进与实现位置

| 项 | 名称 | 实现函数 / 机制 | 触发位置 |
|---|---|---|---|
| 1 | 一页纸摘要 TL;DR | `_tldr()` → 封面后新增「核心要点速览」页，5-6 条带信号灯的大白话结论 + 一句话总结 | `create_stock_pdf` 在 `add_report_reading_guide` 之后插入 |
| 2 | 信号灯式指标评分 | `SIGNAL_THRESHOLDS` + `_signal()` / `_signal_text()` → 数值旁加 ● 彩色信号灯（绿/黄/红）+ 参考区间 | metric_cards、业绩表、现金流表、杜邦说明 |
| 3 | 术语释义注释 | `GLOSSARY` + `_gloss(term)` → 关键术语首次出现自动展开括号解释 | 各章节标题 / 表格列名 |
| 4 | 章节白话导语 | `_chapter_intro(key)` → 每章标题后一行"这节回答什么问题" | 全部 22 章标题后 |
| 5 | 封面 notes 大白话 | `_plain_summary()` → 按各指标信号灯拼接一条综合大白话判断，替换原行话 notes | 封面 notes「核心结论」 |

> 数据流：`create_stock_pdf` 内已计算 `cf_quality`(`_cashflow_quality`)、`business_engine`(`_business_engine`)、`industry_cycle`(`_industry_cycle`)、`bear_case`(`_bear_case`)，并喂给 `_tldr(...)` 与 `_plain_summary(...)`，故 TL;DR 与白话封面直接复用既有指标，无额外取数。

### 13.2 信号灯阈值（SIGNAL_THRESHOLDS，节选）

每个指标定义 2-3 档阈值，返回 `(bulb, 颜色, 标签)` 三元组；ReportLab 用 `<font color="...">` 给 `●`（U+25CF 黑色圆点，CN 字体 STHeiti/Arial Unicode MS 均支持）着色，`None`/N/A 返回 `–`（数据缺失）。

> **字体注意（已修复）**：原设计用 ✅/⚠️/❌ emoji 作信号灯，但 CN 字体不含 emoji 字形、ReportLab 也无法渲染彩色 emoji，导致灯泡显示为空白。复验时改为带颜色的 `●` 圆点，效果等同红/黄/绿交通灯，且 PDF 文本可正常提取。

```python
SIGNAL_THRESHOLDS = {
  "roe":          [(15,"●","优秀(>15%)"), (8,"●","一般(8-15%)"), (0,"●","偏弱(<8%)")],
  "pe_pct":       [(30,"●","偏低(<30%)"), (70,"●","适中(30-70%)"), (100,"●","偏高(>70%)")],
  "debt":         [(40,"●","健康(<40%)"), (70,"●","一般(40-70%)"), (100,"●","偏高(>70%)")],
  "cfo_ratio":    [(1.0,"●","扎实(≥1.0)"), (0.5,"●","一般(0.5-1.0)"), (0,"●","偏弱(<0.5)")],
  "gross_margin": [(50,"●","高毛利(≥50%)"), (35,"●","中等(35-50%)"), (0,"●","低毛利(<35%)")],
  "net_margin":   [(15,"●","较高(≥15%)"), (8,"●","中等(8-15%)"), (0,"●","偏低(<8%)")],
  "rev_growth":   [(15,"●","强劲(>15%)"), (0,"●","微增/持平(0-15%)"), (-100,"●","负增长(<0%)")],
  "profit_growth":[(15,"●","强劲(>15%)"), (0,"●","微增/持平(0-15%)"), (-100,"●","负增长(<0%)")],
  "current_ratio":[(2.0,"●","健康(≥2)"), (1.0,"●","一般(1-2)"), (0,"●","偏低(<1)")],
  "pledge":       [(5,"●","低风险(<5%)"), (10,"●","关注(5-10%)"), (100,"●","偏高(>10%)")],
}
```

### 13.3 术语表样例（GLOSSARY，节选）

| 术语 | 释义 |
|---|---|
| PE(TTM) | 市盈率（股价÷最近12个月每股收益），衡量估值高低 |
| ROE | 净资产收益率（净利润÷净资产），每1元股东权益赚多少利润 |
| CFO/净利比 | 经营现金流÷净利润，>1 表示利润含金量高（赚到的钱真的到手了） |
| 权益乘数 | 总资产÷净资产，即杠杆倍数。2倍 = 1元自有资金撬动2元总资产 |
| 毛利率 | （营业收入-营业成本）÷营业收入，衡量产品赚钱能力 |
| PE分位 | 当前PE在历史数据中的相对位置，30%表示比70%的历史时间都便宜 |
| 黑天鹅 | 极低概率但冲击巨大的事件，如突发政策、行业崩塌 |

### 13.4 TL;DR 渲染示例（信立泰 002294）

```
核心要点速览
1. 估值：PE(TTM)市盈率(...) 当前 22.5，近3年分位 35% ● 偏低(<30%)
2. 盈利能力：ROE净资产收益率(...) 当前 7.3% ● 一般(8-15%)
3. 现金流：CFO/净利润(...) 当前 0.85 ● 一般(0.5-1.0)
4. 赚钱方式：毛利率(...) 74.8% ● 高毛利(≥50%) → 高毛利溢价型
5. 行业周期：成熟/分化期
6. 看空信号：检出 3条 量化看空理由，需重点关注。
一句话：信立泰当前估值不算贵、盈利偏弱、利润含金量一般，需跟踪业绩与行业变化。
```

### 13.5 章节导语示例

```
一、公司概况
这节回答：这家公司是做什么的？在行业里处于什么位置？
```

### 13.6 设计原则与边界

- **零 token 硬约束**：可读性层不调用任何 LLM / 搜索，全部为阈值规则与模板文本。
- **不改数据层**：仅新增渲染函数与字典，不修改 `fin_<code>.json` 契约或 step4 的 `_load()`。
- **优雅降级**：任一指标为 `None`/`N/A` 时，信号灯显示 `–`（数据缺失），TL;DR 跳过该条，不报错。
- **风格统一（已完成）**：第八章（财务健康度）小结 `health_notes` 已改用 `_signal_text('roe'/'debt', ...)`，与其他章节一致，全部套用彩色 `●` 信号灯。
- **复验结论（2026-07-19）**：在 `feature/tdx-data-source` 重跑 002294 + 600176 双标的，报告均 exit 0；两份 PDF 字面 `None = 0`、信号灯 `●` 正常渲染（每份 22 个）、TL;DR 页 / 17 处章节导语 / 术语释义 / 白话封面均生效，运行期零 token。可读性层已验证并提交（`6c79bf0`）。

---

## 14. P2 探索项正式设计（12 / 13 / 14 / 15 / 16 / 17）

> **状态**：本章为设计记录，**尚未实现**。六项均遵守 skill 的核心定位——「研究复盘，不输出买卖建议」。
> 设计中严格区分两类实现：
> - **A 类（CLI 内、零 token、纯规则化）**：可直接进 `step4` / `run_report`，与现有引擎同构。12（轻量版）、13、15、16、17 属此类。
> - **B 类（编排层、非零 token、可选）**：依赖 LLM / 多模态，只能由 WorkBuddy 对话编排层产出结构化结果后**以数据形式喂给 CLI**，不破坏 CLI 的确定性与零 token。14 属此类；12 的重量版亦属此类，本设计不纳入 PDF。
>
> **合规红线（六项共用）**：不得输出买入/卖出/持有评级、目标价、仓位、止损位、"推荐/回避"等买卖倾向措辞。所有主观推断句一律加 §P1-10 的【判断】/【情景】标签。

### 14.0 定位边界总则

| 维度 | 约束 |
|---|---|
| 输出边界 | 只描述"事实 + 分歧 + 关注点"，买卖由用户拍板 |
| Token | A 类必须零 token；B 类的非零 token 部分限定在编排层，CLI 侧仍零 token |
| 降级 | 缺数据时该章节/该条目跳过或标 N/A，绝不 crash |
| 可选性 | 13 / 14 默认关闭，不提供输入时报告与现状完全一致（向后兼容） |

---

### 14.1 P2-12 多视角速览（私董会轻量版，A 类 · 零 token）

**目标**：在报告中提供 4 个预设"投研视角"对同一标的的一句话观点，模拟私董会的多视角交叉，强制暴露分歧；**不做** LLM 辩论（重量版明确排除，见 §14.1 边界）。

**四视角与判断依据（全部复用已算指标，无额外取数）**：

| 视角 | 关注核心 | 规则化观点来源 |
|---|---|---|
| 价值派 | 估值分位 + 现金流质量 | `val.pe_pct_3y` + `cf_quality.ratio` + `fin.roe` |
| 成长派 | 营收/净利增速 + 行业周期 | `fin.rev_growth` / `fin.profit_growth` + `industry_cycle.stage` |
| 趋势派 | 技术位 + 资金面 | 20 日均线偏离 + `net_mf_20d`（资金流）|
| 风险派 | 空方信号 + 负债/质押 | `bear_case.signals` + `fin.debt_ratio` |

**函数设计**：
```python
def _multi_perspective(fin, val, cf_quality, industry_cycle, bear_case, tech):
    """返回 [{'lens':..., 'view':..., 'signal': _signal(...)}]，纯规则模板。"""
    # 每个视角依阈值拼接一句【判断】，例如：
    # 价值派：PE 近3年分位 35% 偏低、CFO/净利 0.85 一般 → 「估值有安全边际，但需确认利润含金量」
```

**渲染**：新增章节「多视角速览」（建议置于 §二 情景区间之后），一张 4 行表：`视角 | 关注点 | 一句话观点(【判断】)`。章节导语走 `_chapter_intro`：*"这节回答：不同风格的投研视角，会怎么看这家公司？分歧在哪？"*

**边界**：
- 重量版（接 `six-advisors` / 真实 LLM 辩论）**不纳入 PDF**；若做，作为编排层独立可选产物单独呈现，避免报告含 LLM 主观观点。
- 四视角观点均为【判断】，且只描述"关注点与倾向性观察"，不给买卖结论。

**可行性**：高。零 token，复用现有指标，约 1 个函数 + 1 章渲染。

---

### 14.2 P2-13 用户画像 / 偏好建档（A 类 · 零 token · 可选）

**目标**：让报告按用户投资风格微调"监控清单排序""情景假设宽窄""TL;DR 侧重"，提升相关性；默认不建档时报告与现状完全一致。

**画像 schema（`user_profile.json`，存于 workspace，非 git）**：
```json
{
  "style": "价值|成长|趋势|均衡",
  "horizon": "短线|中线|长线",
  "focus_industries": ["医药", "新能源"],
  "risk_tolerance": "低|中|高"
}
```

**交互与持久化分层**：
- **建档交互在 WorkBuddy 对话层**完成（首次问 3-4 个问题），写入 `user_profile.json`；**CLI 不做交互**，只读取该文件。
- `run_report.py` 增加可选读取：存在 `user_profile.json` → 载入并塞进 `data["user_profile"]`；不存在 → 跳过，行为不变。

**画像对报告的作用（仅影响展示，不改数据）**：

| 画像维度 | 影响点 |
|---|---|
| style | 监控清单 / 多视角速览的**排序权重**（价值派优先看估值与现金流条目）|
| risk_tolerance | 三情景区间的**呈现侧重**（低风险者高亮 Bear 情景，高风险者高亮 Bull）——仅高亮，不改区间数值 |
| horizon | TL;DR 末句提示"你更关注短期/长期"对应的观察变量 |
| focus_industries | 若标的行业命中，行业周期章节加一句"属于你关注的行业" |

**函数设计**：`_apply_profile(story_blocks, user_profile)`——在渲染前对相关块重排序/加高亮，纯模板逻辑。

**边界**：
- 严格"可选建档"：无 profile = 通用报告，向后兼容。
- 不据画像给买卖/仓位建议，只调整"看哪些指标"的呈现优先级。

**可行性**：中。零 token，但需新增文件读取 + 排序逻辑；建档交互依赖编排层。

---

### 14.3 P2-14 图文双轨（K 线截图交叉验证，B 类 · 编排层非零 token · 可选）

**目标**：用户上传 K 线截图时，识别图上的形态/均线/MACD，与 TDX 数据交叉验证，冲突时**以数据为准并标注差异**。

**关键架构决策**：图像识别属**多模态能力，放在 WorkBuddy 编排层**（对话中原生识图），**不进 CLI**。编排层把识别结果整理成结构化 `image_findings`，以**数据形式**喂给 `run_report` → `step4` 渲染对照章节。CLI 侧仍是确定性、零 token。

**`image_findings` schema（编排层产出，可选传入）**：
```json
{
  "source": "用户上传K线截图识别",
  "pattern": "头肩顶|双底|突破|震荡|...",
  "ma_signal": "多头排列|空头排列|缠绕",
  "macd_signal": "金叉|死叉|背离|无",
  "captured_at": "2026-07-19"
}
```

**交叉验证逻辑（CLI 内规则化）**：`_image_data_reconcile(image_findings, tech)`——把截图识别信号与 TDX 实算技术位逐项比对：
- 一致 → 标「图数一致」；
- 冲突 → 标「⚠ 图数冲突，以数据为准」并给出数据侧的实际值。

**渲染**：新增子章节「图文双轨对照」（置于 §三 股价与估值下），表格：`维度 | 截图识别 | TDX 数据 | 结论`。章节顶部固定声明：*"图像识别可能因截图清晰度/周期不同而失真；本报告一律以 TDX 结构化数据为准。"*

**边界**：
- ✅ 与定位兼容，但**优先级低**：我们的数据本就比截图全；主要价值是服务"看图派"用户的输入习惯。
- 非零 token 部分（识图）严格限定在编排层；不提供截图时该章节不出现。

**可行性**：低-中。识图依赖多模态（编排层已具备），CLI 侧对照逻辑简单；主要成本在编排层的截图→结构化流程标准化。

---

### 14.4 P2-17 分投资者类型结论框架（A 类 · 零 token）

**目标**：报告结尾按投资者类型给"**关注点差异**"——这类投资者该重点看哪个指标、该指标当前什么状态；**严禁**滑向买卖/仓位/止损建议。

**四类型与关注框架（复用已算指标 + 信号灯）**：

| 投资者类型 | 重点关注指标 | 当前状态来源 |
|---|---|---|
| 价值型 | 估值分位、股息率、现金流质量、ROE | `val.pe_pct_3y` / `dividend` / `cf_quality` / `fin.roe` |
| 成长型 | 营收/净利增速、行业周期、赚钱机制 | `fin.*_growth` / `industry_cycle` / `business_engine` |
| 趋势型 | 技术位、资金流、量能 | 均线偏离 / `net_mf_20d` |
| 稳健型 | 负债率、流动比率、质押、波动 | `fin.debt_ratio` / `current_ratio` / `pledge` |

**函数设计**：
```python
def _investor_framework(fin, val, cf_quality, industry_cycle, bear_case, tech):
    """每类型返回 {'type', 'focus':[指标+当前信号灯状态], 'watch': 一句话关注提示}。
    watch 仅描述"该盯什么变量"，不含买卖/仓位措辞。"""
```

**渲染**：报告结尾（免责声明前）新增章节「研究结论框架（按投资者类型）」，每类型一小节：关注指标（带 `●` 信号灯）+ 一句【判断】式关注提示。章节顶部固定声明：*"本框架只说明不同类型投资者应重点关注的指标差异，不构成任何买卖、仓位或止损建议。"*

**边界（本项最需谨慎）**：
- 只输出"关注点差异"，不给"该买/该卖/该加减仓"。
- 每条提示避免"建议/应买入/可介入"等措辞，改用"需重点观察/其决策取决于"等中性表达。

**可行性**：高。零 token，纯模板 + 已算指标。

---

### 14.5 P2-15 治理与筹码事件时间表（A 类 · 零 token · 数据依赖 TDX 接口 / 公告检索）

**目标**：新增「治理与筹码」章节，把未来 12 个月内的质押到期 / 限售解禁 / 减持 / 股权激励行权 / 回购 / 监管问询等筹码事件显式列成时间表，把"生意好 + 治理差 = 高波动风险资产"这一风险源落地到可读清单。

**数据来源分层（CLI 渲染仍为确定性、零 token）**：
- **质押率** `pledge_ratio`：`§3` 已预留 `pledge` 键，源自 TDX 质押类 entry；取数成功直接喂 `data["pledge"]`，信号灯已支持（`SIGNAL_THRESHOLDS["pledge"]`，<5% 低风险 / 5-10% 关注 / >10% 偏高）。
- **限售解禁 / 减持 / 激励 / 回购 / 监管问询**：来自 `wenda_notice_query` 公告检索，由编排层筛出"未来 12 个月 + 筹码相关"条目，结构化后喂给 CLI。

**`chip_events` schema（编排层产出，可选传入）**：
```json
[
  {"date": "2026-11-30", "type": "限售解禁|减持|质押到期|股权激励行权|回购|监管问询",
   "detail": "解禁 1.2 亿股，占流通股本 8%", "source": "TDX 公告检索"}
]
```

**函数设计**：
```python
def _chip_event_timeline(events, pledge_ratio, top10_holders):
    """返回 12 个月事件表 + 质押信号灯 + 股东集中度观察。
    无 events 且无 pledge → 该子章标 N/A（优雅降级）。"""
```

**渲染**：新增「治理与筹码」章节（建议置于 §十三 股东结构之后），含两子块：
1. **质押与集中度**：质押率信号灯（已有 `●`）+ 十大股东集中度观察。
2. **未来 12 个月筹码事件时间表**：表格 `日期 | 类型 | 明细 | 来源`，按日期升序；仅当取数成功且检索结果为空时才可标“检索范围内未发现重大筹码事件”。若取数失败、覆盖范围不明或事件日期无法确认，一律标 `N/A（待用户本地验证）`，不得把“未取到”写成“没有”。

**边界**：
- ✅ 与定位兼容——只列客观事件 + 质押信号灯，不给"利空/利好"定性或买卖建议。
- 可行性中：质押接口已在契约预留；解禁/减持/激励的事件提取依赖公告检索召回质量，需 TDX 重连后实测字段与条目覆盖，缺失则降级标 N/A。

---

### 14.6 P2-16 扣非净利润 / 周转率 / 存货应收警报（A 类 · 零 token）

**目标**：把"财务扫雷"从单一归母净利 / CFO 扩展为更全面的质量体检——区分归母净利与**扣非净利**（识别非经常性损益注水）、引入**存货周转率**与**应收账款周转天数**（识别滞销与回款风险）、强化已有的 CFO/净利比。

**指标与计算（全部本地，零 token）**：

| 指标 | 公式 | 数据来源 |
|---|---|---|
| 扣非净利润 | 归母净利 − 非经常性损益 | `ph_agf10_cw_lyb` 利润表明细（需实测"非经常性损益"行键是否存在）|
| 扣非占比 | 扣非净利 ÷ 归母净利 | 上两项派生 |
| 存货周转率 | 营业成本 ÷ 平均存货 | `ph_agf10_cw_zcfzb` 存货 + `lyb` 营业成本 |
| 应收账款周转天数 | 平均应收账款 × 365 ÷ 营业收入 | `zcfzb` 应收账款 + `lyb` 营业收入 |
| CFO/净利比 | 经营现金流 ÷ 净利润（已有，强化） | `ph_agf10_cw_xjllb` |

**信号灯阈值（新增 `SIGNAL_THRESHOLDS`，仅作首版展示规则）**：
```python
"kfj_ratio":   [(0.85,"●","利润扎实(≥85%)"), (0.6,"●","留意(60-85%)"), (0,"●","注水嫌疑(<60%)")],
"inv_turnover":[(6,"●","健康(≥6次)"), (2,"●","一般(2-6次)"), (0,"●","滞销(<2次)")],
"ar_days":     [(60,"●","回款快(≤60天)"), (120,"●","一般(60-120天)"), (1000,"●","偏慢(>120天)")],
```

> **阈值边界**：存货周转率和应收账款周转天数强烈受行业商业模式影响，不能把上表作为跨行业的风险结论。首版必须同时展示原始值、计算期与可比期；无行业分组基线时，状态只可写“相对本公司历史偏高/偏低”或“待结合行业确认”，不得使用“健康/滞销/回款快”等跨行业定性。扣非字段、存货和应收字段的实际 TDX 行键未经烟测前均视为 `N/A`。

**函数设计**：
```python
def _financial_quality_alerts(income, balancesheet, cashflow):
    """返回扣非占比/存货周转率/应收天数信号灯 + 一句【判断】式扫雷提示。
    任一明细缺失 → 该指标 N/A，其余照常，绝不 crash。"""
```

**渲染**：扩展 §五 财务健康度（在 ROE / 负债 / CFO 之后新增"财务质量扫雷"子块），用信号灯表呈现；章节导语补一句"这节回答：利润有没有水分？货好不好卖？钱好不好收？"。

**边界**：
- 扣非 / 明细行依赖 TDX 利润表与资产负债表明细字段，需实测字段名（`lyb`/`zcfzb` 行键），缺失则对应指标标 N/A。
- ✅ 纯规则化、零 token，与定位完全兼容（只做质量体检，不下买卖结论）。

**可行性**：中。计算本身简单；主要成本在 TDX 明细字段的 reshape 实测与降级处理。

---

### 14.7 P2 实施优先级、数据闸门与验收标准

P2 应区分“研究增量价值”和“当前可安全实现性”。只按实现容易程度排，会把展示层功能排在财务质量、治理事实之前；只按研究价值排，又会忽略接口字段尚未验证的现实约束。

| 研究价值排序 | 项 | 当前状态 / 数据闸门 | 建议动作 |
|---:|---|---|---|
| 1 | 16 扣非/周转率警报 | 必须先用已授权 TDX 对 `lyb`/`zcfzb` 明细行做字段烟测，并核对单位、报告期和行业基线 | **优先验证后落地**；未通过前只保留设计与 `N/A` |
| 2 | 15 治理与筹码时间表 | 必须验证质押接口、公告日期语义、未来事件召回范围；“无结果”与“未取到”必须可区分 | **优先验证后落地** |
| 3 | 12 多视角速览 | 仅复用既有 `step4` 派生指标，无新增取数 | **首个可直接编码项**；应合并相近信号，避免重复复述 TL;DR |
| 4 | 17 分投资者类型框架 | 仅复用既有指标，但与 12 的“视角”存在展示重叠，且措辞最易越过适当性边界 | 放在 12 后；先做“关注指标卡”，不输出行动导向结论 |
| 5 | 13 用户画像 | 本地画像涉及隐私、持久化和跨设备语义；需明确存储位置、删除方式与默认关闭 | 等核心事实层稳定后再做 |
| 6 | 14 图文双轨 | 编排层多模态非零 token，且结构化行情已是更可靠事实源 | 保持可选探索，不进入当前 CLI 范围 |

**推荐实施顺序**：先实现 **12**，以最小改动验证 P2 的章节装配与事实/判断标注；待 TDX 连通后，按 **16 → 15** 的顺序做字段和日期语义烟测，测试通过才实现；随后根据 12 的实际阅读反馈决定是否需要 17，避免两个“视角类”章节重复。13、14 不建议进入本轮代码范围。

**统一输入契约（设计占位，字段未经 TDX 验证前不得写死解析）**：`run_report.py` 仅接受编排层已归一化的数据，P2 字段放在可选块中，缺块不改变既有 22 章输出：

```json
{
  "p2": {
    "enabled_modules": ["multi_perspective"],
    "as_of": "2026-07-19",
    "chip_events": [],
    "financial_quality_inputs": null,
    "user_profile": null,
    "image_findings": null
  }
}
```

- `enabled_modules` 是显式开关；未声明或字段不合法时跳过对应 P2 章节，不改变默认报告。
- `as_of` 必填于启用的 P2 块，用于显示数据截至时间；超过编排层约定的时效窗口时标 `N/A（数据时点待确认）`。
- `chip_events=[]` 仅表示“成功检索但无归一化事件”；`null` 表示未取数或无法验证，渲染不得得出“无事件”。
- `financial_quality_inputs` 只承载已归一化的数值、单位、报告期与来源，不直接透传 TDX 原始中文行名；这使 CLI 保持字段契约稳定。

**章节级验收**：每个 P2 模块至少覆盖“完整输入、字段缺失、空结果、非法日期/单位”四类夹具；其中“字段缺失”和“空结果”必须输出不同文字；报告中不得出现 `None`、不得新增买卖倾向措辞。只有在已授权环境完成上述夹具与一个真实标的的人工复核后，才能把状态从“设计”更新为“已实现”。
