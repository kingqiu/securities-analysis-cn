# 安装与排障指南

本 Skill 的目标是：用户拿到项目后，能先通过环境检查，再生成一份最小报告。

## 推荐安装方式

```bash
git clone https://github.com/kingqiu/securities-analysis-cn.git
cd securities-analysis-cn
python3 scripts/setup.py
```

`scripts/setup.py` 会做三件事：

- 安装 `requirements.txt` 中的依赖。
- 如果本地没有 `.env`，自动从 `.env.example` 复制一份。
- 运行 `scripts/check_env.py` 检查依赖、配置、中文字体和输出目录。

如果你已经装过依赖，只想初始化和检查：

```bash
python3 scripts/setup.py --skip-install
```

## 手动安装方式

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 scripts/check_env.py
```

然后编辑 `.env`：

```text
TUSHARE_API_TOKEN=你的 token
TUSHARE_API_URL=你的 Tushare 兼容网关地址
```

可选配置：

```text
MINIMA_API_KEY=你的 MiniMax Key
TAVILY_API_KEY=你的 Tavily Key
```

## 最小验证命令

```bash
python3 run_analysis.py 600519
python3 run_analysis.py 00700.HK
python3 run_analysis.py 510300
```

多标的对比：

```bash
python3 run_analysis.py 贵州茅台 五粮液
python3 run_analysis.py 510300 510500
```

## 常见问题

### 1. `TUSHARE_API_TOKEN` 检查失败

说明 `.env` 还没有填真实 token，或者仍然是 `your_tushare_token_here` 这类占位符。

处理方式：

```bash
cp .env.example .env
```

然后编辑 `.env`，填入真实 token。

### 2. `TUSHARE_API_URL` 检查失败

URL 必须以 `http://` 或 `https://` 开头。示例：

```text
TUSHARE_API_URL=https://tt.xiaodefa.cn
```

如遇本地 SSL 问题，可按服务方说明切换备用域名或协议。

### 3. LLM Key 缺失

LLM Key 缺失不会阻止报告生成。报告会尽量使用规则化研究文本降级输出，只是“模型文字解读”部分会更简化。

### 4. Tavily Key 缺失

默认 `SEARCH_PROVIDER=auto` 时，Tavily 缺失不会阻止报告生成，但最新新闻和行业动态会降级或跳过。

如果设置了：

```text
SEARCH_PROVIDER=tavily
```

则必须提供 `TAVILY_API_KEY`。

### 5. PDF 中文字体检查失败

需要安装可用于 PDF 的中文字体，例如：

- macOS：系统通常自带 `STHeiti`
- Linux：可安装 WenQuanYi / Noto CJK

### 6. 安装依赖失败

建议先升级 pip：

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

如果 `akshare`、`efinance`、`yfinance` 的安装失败，核心结构化数据仍依赖 Tushare；免费行情兜底能力可能受影响。

## 提交安全

不要提交以下文件：

- `.env`
- `temp_*.json`
- `*.pdf`
- `preview_pages/`
- `.local_plans/`
- Python / Matplotlib 缓存

提交前运行：

```bash
git status --short
```
