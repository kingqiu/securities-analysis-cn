# securities-analysis-cn

中国证券（A股/港股/ETF）深度分析 PDF 报告自动生成器。

## 项目结构

```
├── run_analysis.py                 # 统一入口（解析→识别→获取→研究→生成）
├── config.py                       # 全局配置（Provider 选择 + API 密钥，从 .env 加载）
├── providers/                      # 插件化适配器（Provider Pattern）
│   ├── base.py                     # 三个抽象基类：DataProvider / LLMProvider / SearchProvider
│   ├── __init__.py                 # 工厂函数：get_data_provider / get_llm_provider / get_search_provider
│   ├── data_tushare.py             # 数据源：小德法 Tushare API（委托现有 fetch 模块）
│   ├── llm_minimax.py              # LLM：MiniMax-M2.7（Anthropic 兼容 x-api-key）
│   ├── llm_openai.py               # LLM：OpenAI 兼容（Bearer token，支持 GPT/DeepSeek/通义等）
│   ├── search_ai.py                # 搜索：AI 知识库总结（通过 LLMProvider 调用）
│   └── search_tavily.py            # 搜索：Tavily API + LLM 总结
├── identify_code_type.py           # 代码/名称解析：resolve_input / identify / search_by_name
├── ai_analysis.py                  # AI 投资建议：prompt 模板 + 规则化 fallback + _call_llm()
├── web_research.py                 # 互联网研究（薄代理层，委托 SearchProvider）
├── step1_fetch_real_data.py        # ETF 数据获取（Tushare API）
├── step1_fetch_stock_data.py       # A股 数据获取（21 项 API 调用）
├── step1_fetch_hk_stock_data.py    # 港股 数据获取（9 项 API 调用）
├── step3_generate_pdf_report.py    # ETF PDF 报告生成（reportlab + matplotlib）
├── step4_generate_stock_pdf.py     # A股 PDF 报告生成（16 章节）
├── step5_generate_hk_stock_pdf.py  # 港股 PDF 报告生成（10 章节）
├── .env                            # 敏感配置（gitignored）
├── .env.example                    # 环境变量模板
├── SKILL.md                        # Skill 定义（agent 系统入口）
└── README.md / README_EN.md        # 中英文项目说明
```

## 核心数据流

```
用户输入（名称/代码）
  → resolve_input()          # 名称搜索或代码标准化
  → DataProvider.identify()  # 判断 etf / stock / hk_stock
  → DataProvider.fetch_*()   # 拉取行情+财务+股东等多维数据
  → SearchProvider.search()  # AI 互联网研究（可选）
  → 数据写入 temp JSON
  → create_*_pdf()           # 读取 JSON → 计算指标 → 调用 LLMProvider → 生成 PDF
```

## 关键约定

- **所有 API 密钥** 仅通过 `.env` 加载，**绝不硬编码**
- **Provider 切换** 通过 `.env` 中的 `DATA_PROVIDER` / `LLM_PROVIDER` / `SEARCH_PROVIDER`
- **PDF 生成** 使用 reportlab + matplotlib，中文字体使用 STHeiti（macOS）或 SimHei
- **AI 调用失败** 时自动降级为规则化建议，不中断流程
- **互联网研究失败/超时** 时自动跳过，不中断流程
- `temp_*.json` 是中间产物，已在 `.gitignore` 中排除

## 开发须知

- 编辑 Provider：修改 `providers/` 下对应文件，实现基类接口
- 新增数据字段：在 `step1_fetch_*.py` 中添加 API 调用 → 在 `step*_generate_*_pdf.py` 的 `_load()` 中加载 → 在 `create_*_pdf()` 中添加展示逻辑
- 修改 AI Prompt：编辑 `ai_analysis.py` 中的 `_STOCK_PROMPT` / `_HK_STOCK_PROMPT` / `_ETF_PROMPT`
- 运行测试：`python3 run_analysis.py 泡泡玛特`（港股端到端验证）
