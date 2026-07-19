# 交接说明（Handoff）：securities-analysis-cn · TDX 零 token 数据层替换

> 本文档供**接手本项目继续开发的 AI Agent**阅读。
> 项目目标：用「通达信 MCP (TDX)」替换 `securities-analysis-cn` 原有的 Tushare 数据层，
> 在不向用户索取任何 API Key / Token、不调用外部 LLM / 搜索的前提下，零 token 生成 A股 / ETF / 港股研究复盘报告。
>
> 分支：`feature/tdx-data-source`（所有演进都在这里；`main` 是旧 Tushare 版本，勿动）。
> 权威设计文档：仓库根目录 `DESIGN-TDX-REPLACEMENT.md`；背景：`IMPROVEMENT-PLAN.md`。

---

## Step 0 — 配置通达信 MCP（TDX）【必须，否则无法运行】

本项目数据层**完全依赖**「通达信 MCP (TDX)」——一个零 token 的 A股 / ETF / 港股财务与行情数据源。
**没有它，你无法运行或验证任何报告。** 你（新 Agent）当前很可能没有这个 MCP，请先配置。

### 路径 A：你的环境有 connector / MCP 市场（最常见）

1. 打开你的 connector / MCP 管理面板（与 Feishu / Lark 等连接器同处）。
2. 找到并启用「通达信 / TDX」MCP 连接器（也可能叫 "TDX 行情" / "通达信数据"）。
3. 信任 / 激活它。启用后，以下工具必须可用：
   - `tdx_lookup_stock`、`tdx_kline`、`tdx_quotes`、`tdx_api_data`、`tdx_indicator_select`
   - `wenda_news_query`、`wenda_report_query`、`wenda_notice_query`、`wenda_macro_query`
   - `tdxf10_*` 系列（`tdxf10_gg_gdyj` / `tdxf10_gg_jyds` / `tdxf10_gg_fhrz` 等）
4. 若市场里**没有**该连接器，走路径 B。

### 路径 B：手动加入 MCP 配置（自托管 server 时）

把下面这个 server 条目加进你的 MCP 配置文件（如 `~/.workbuddy/mcp.json` 的 `mcpServers` 下）：

```json
"<TDX_SERVER_NAME>": {
  "command": "<由项目方提供的 TDX command>",
  "args": ["<args>"],
  "env": { "<KEY>": "<VALUE>" }
}
```

> ⚠️ 上述 `command` / `args` / `env` / `url` / `headers` 的**真实取值必须向项目方索取**——
> 不要猜测，也**不要**把任何密钥硬编码进仓库。填好后**重启会话**让 MCP 工具加载。

> 环境备注：在参考环境（本仓库作者的工作站）中，`~/.workbuddy/mcp.json` 仅含 `obsidian-mcp-server`，
> **无 TDX 条目**，说明 TDX 在该环境是**平台级 connector**而非自托管 server。因此对新 Agent 而言
> 「路径 A」通常是正解；只有确认为自托管 server 时才需走路径 B。

---

## Step 1 — 获取代码

```bash
git clone https://github.com/kingqiu/securities-analysis-cn.git
cd securities-analysis-cn
git checkout feature/tdx-data-source
```

> ⚠️ 只在 `feature/tdx-data-source` 分支上工作。`main` 是旧的 Tushare 版本，**不要修改它**。

---

## Step 2 — 读取设计文档

- **`DESIGN-TDX-REPLACEMENT.md`**（仓库根目录）——架构与实现状态的**唯一权威文档**。
  - 报告最终结构、列名契约、降级策略见 §1–§11。
  - P0 / P1 实现状态见 §12；可读性层见 §13。
  - **P2 探索项（12–17）的正式设计在 §14**，分 A 类（CLI 内、零 token、纯规则化）与 B 类（编排层、非零 token、可选）。
- **`IMPROVEMENT-PLAN.md`**——改进方案与 P0/P1 完成记录、P2 探索笔记。

---

## Step 3 — 验证 TDX MCP 已连通（动手前必做）

冒烟测试：调用 `tdx_lookup_stock("贵州茅台")` → 期望返回 `600519`。

```text
示例：tdx_lookup_stock("贵州茅台")  →  600519
```

若失败，**立即停止**并告知用户「TDX MCP 未连通」，不要继续写代码或跑报告。

---

## Step 4 — 做你的改动

- 保持**中文撰写风格**；新增 / 扩展 P2 设计请沿用 `§14.x` 小节格式（数据契约 + 函数签名 + 渲染方案 + 定位边界 + 可行性）。
- **严守零 token 定位**：不调用任何外部 LLM / 搜索；报告只跑 TDX 数据 + 本地计算。
- 新增 P2 设计需明确**类别**：
  - **A 类**：CLI（`step4` / `run_report`）内、零 token、纯规则化——可直接实现。
  - **B 类**：编排层、非零 token、可选——只能由对话编排层产出结构化结果后**以数据形式喂给 CLI**，不破坏 CLI 的确定性与零 token。
- 合规红线（全项目共用）：**不输出**买入 / 卖出 / 持有评级、目标价、仓位、止损位、「推荐 / 回避」等买卖倾向措辞。所有主观推断句加【判断】/【情景】标签。

---

## Step 5 — 提交并推回同一分支

```bash
git add -A
git commit -m "docs(tdx): <你的改动摘要>"
git push origin feature/tdx-data-source
```

> 提交信息沿用 `docs(tdx):` / `feat(tdx):` 前缀，便于归类。

---

## 硬性约束（务必遵守）

1. **零 token**：绝不调用外部 LLM / 搜索。所有报告生成必须仅依赖 TDX 数据 + 本地计算。
2. **绝不提交** API Key / Token / 密钥到仓库。
3. **不碰 `main` 分支**——所有改动在 `feature/tdx-data-source`。
4. **优雅降级**：任一数据缺失时标 `N/A` 或跳过章节，绝不 `crash`。
5. **定位不越界**：只做研究复盘，不下买卖建议。

---

## 速查：TDX 工具 → 报告用途对照（已实测可用）

| 用途 | 工具 / entry |
|---|---|
| 名称→代码、类型识别 | `tdx_lookup_stock` |
| 日线 OHLCV | `tdx_kline` (period=4) |
| 个股现 PE/PB/市值/总股本/营收/净利/总资产 | `tdx_quotes` (hasCwInfo=1) |
| 行业 PE 历史 | `tdx_api_data` `ph_agf10_gzfx` |
| 利润表（归母净利/营收/TTM 来源） | `tdx_api_data` `ph_agf10_cw_lyb` |
| 资产负债表 | `tdx_api_data` `ph_agf10_cw_zcfzb` |
| 现金流量表 | `tdx_api_data` `ph_agf10_cw_xjllb` |
| 十大股东 / 股东人数 | `tdx_api_data` `tdxf10_gg_gdyj` (ltgd/gdrs) |
| 主力资金流 / 融资融券 / 大宗 | `tdx_api_data` `tdxf10_gg_jyds` (zjlx/rzrq/dzjy) |
| 分红 | `tdx_api_data` `tdxf10_gg_fhrz` |
| 行业排名 / 估值排名 | `tdx_api_data` `ph_agf10_hypm` (queryKey=00105) |
| 指数日 K | `tdx_kline` (指数 setcode=62/1) |
| 新闻 / 研报 / 公告 / 宏观 | `wenda_news/report/notice/macro_query` |
| ETF 日线 / 实时 / 规模 | `tdx_kline` / `tdx_quotes` / `tdx_indicator_select` |

> 港股日 K 线 TDX **不支持**（真缺口），需 `yfinance` 兜底或标 N/A；其余港股财务 / 研报均可用。
