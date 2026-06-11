# securities-analysis-cn

中国证券（A股/港股/ETF）研究复盘 PDF 报告生成器。

## 项目结构

```text
├── run_analysis.py                  # 统一入口（解析→识别→获取→研究→生成）
├── config.py                        # Provider 选择 + API 密钥，从 .env 加载
├── providers/                       # 插件化适配器
│   ├── base.py                      # DataProvider / LLMProvider / SearchProvider
│   ├── __init__.py                  # provider 工厂函数
│   ├── data_tushare.py              # Tushare 兼容数据源
│   ├── llm_minimax.py               # MiniMax-M2.7
│   ├── llm_openai.py                # OpenAI 兼容服务
│   ├── search_ai.py                 # LLM 降级搜索整理
│   └── search_tavily.py             # Tavily 搜索 + 结构化摘要
├── identify_code_type.py            # 名称/代码解析
├── ai_analysis.py                   # LLM 研究解读 prompts + fallback
├── analyst_model.py                 # A股规则化研究模型
├── hk_analyst_model.py              # 港股规则化研究模型
├── etf_analyst_model.py             # ETF规则化研究模型
├── peer_model.py                    # 同行龙头、质量标杆、估值锚
├── pdf_design.py                    # PDF 视觉系统、封面、页脚、证据地图
├── web_research.py                  # 互联网研究薄代理层
├── step1_fetch_real_data.py         # ETF 数据获取
├── step1_fetch_stock_data.py        # A股 数据获取
├── step1_fetch_hk_stock_data.py     # 港股 数据获取
├── step3_generate_pdf_report.py     # ETF PDF
├── step4_generate_stock_pdf.py      # A股 PDF
├── step5_generate_hk_stock_pdf.py   # 港股 PDF
├── step6_generate_comparison_pdf.py # 多标的对比 PDF
├── .env                             # 敏感配置（gitignored）
├── .env.example                     # 环境变量模板
├── SKILL.md                         # Skill 指令入口
└── README.md / README_EN.md         # 中英文说明
```

## 核心数据流

```text
单只模式：
  用户输入（名称/代码）
    → resolve_input()
    → DataProvider.identify()
    → DataProvider.fetch_*()
    → SearchProvider.search()       # Tavily 优先
    → 数据写入 temp JSON
    → create_*_pdf()

对比模式：
  多只输入
    → 逐只 resolve + identify + fetch
    → get_comparison_advice()       # 模型对比研究解读
    → create_comparison_pdf()
```

## 关键产品约定

- 报告定位是 **研究复盘与方法启发**，不是买卖建议。
- 不在结论中使用 `买入`、`卖出`、`建仓`、`加仓`、`减仓`、`止盈`、`止损`、`仓位建议`、`最佳买点`、`推荐买入` 等措辞。
- 使用 `研究状态`、`情景区间`、`观察触发器`、`风险复核线`、`研究假设与证据地图`、`模型研究解读`。
- LLM 只解释规则化模型和已取得的数据，不直接生成交易动作。
- 缺失数据必须标注为 `N/A`、`数据不可用` 或 `数据缺口`，不得让 LLM 补造结构化事实。

## 安全约定

- 所有 API 密钥只通过 `.env` 加载，绝不硬编码。
- `.env`、`temp_*.json`、生成的 `*.pdf`、`preview_pages/`、缓存目录均不得提交。
- 提交前运行 `git status --short` 检查是否有敏感文件或生成物被加入版本库。

## Provider 约定

- `DATA_PROVIDER`：结构化行情、财务、股东、基金和指数数据。
- `LLM_PROVIDER`：研究解读文字生成，可失败降级。
- `SEARCH_PROVIDER`：最新公司新闻和行业动态，默认 Tavily 优先。

互联网研究规则：

- 首选 Tavily。
- Tavily 不可用时才允许 AI 降级。
- 搜索结果需要过滤低质量标题、免责声明页和机构评级动作词。

## PDF 生成约定

- 使用 reportlab + matplotlib。
- 图表脚本在无界面环境中必须使用 `matplotlib.use("Agg")`。
- 封面和页脚尽量复用 `pdf_design.py`。
- 单标的和对比报告都应使用统一的非建议化封面语言。

## 开发须知

- 新增数据字段：在 `step1_fetch_*.py` 添加获取逻辑 → 在对应 `_load()` 或 summary 提取函数中接入 → 在 PDF 章节展示。
- 修改 LLM prompt：编辑 `ai_analysis.py`。
- 修改规则化模型：编辑 `analyst_model.py`、`hk_analyst_model.py`、`etf_analyst_model.py`。
- 修改封面/证据地图样式：编辑 `pdf_design.py`。
- 修改对比报告：编辑 `step6_generate_comparison_pdf.py`。

## 验证建议

```bash
PYTHONPYCACHEPREFIX=/private/tmp/codex_pycache python3 -m py_compile \
  ai_analysis.py analyst_model.py hk_analyst_model.py etf_analyst_model.py \
  step3_generate_pdf_report.py step4_generate_stock_pdf.py \
  step5_generate_hk_stock_pdf.py step6_generate_comparison_pdf.py

python3 run_analysis.py 贵州茅台
python3 run_analysis.py 腾讯控股
python3 run_analysis.py 510300
python3 run_analysis.py 510300 510500
```

如果生成 PDF 后要检查敏感措辞，可用 `pdftotext` 抽取文本后搜索：`买入|卖出|建仓|加仓|减仓|止盈|止损|仓位|推荐|最佳买点`。
