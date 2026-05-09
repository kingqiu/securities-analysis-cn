# 证券分析 - 全局配置文件

import os as _os

# ============================================================
# 环境变量加载（优先从 .env 文件读取）
# ============================================================
try:
    from dotenv import load_dotenv as _load_dotenv
    _dotenv_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".env")
    _load_dotenv(dotenv_path=_dotenv_path)
except ImportError:
    pass  # dotenv 未安装时直接读系统环境变量

# ============================================================
# Provider 选择（用户在此切换，或通过 .env 设置）
# ============================================================

# 数据源：tushare（默认）
DATA_PROVIDER = _os.environ.get("DATA_PROVIDER", "tushare")

# AI大模型：minimax（默认）| openai
LLM_PROVIDER = _os.environ.get("LLM_PROVIDER", "minimax")

# 搜索/研究：ai_summary（默认）| tavily | none
SEARCH_PROVIDER = _os.environ.get("SEARCH_PROVIDER", "ai_summary")

# ============================================================
# 数据源配置：Tushare
# ============================================================
TUSHARE_API_URL = _os.environ.get("TUSHARE_API_URL", "http://tsy.xiaodefa.cn")
TUSHARE_API_TOKEN = _os.environ.get("TUSHARE_API_TOKEN", "")

# ============================================================
# AI 大模型配置
# ============================================================

# MiniMax（默认）
MINIMA_API_URL = _os.environ.get("MINIMA_API_URL", "https://api.minimaxi.com/anthropic")
MINIMA_MODEL = _os.environ.get("MINIMA_MODEL", "MiniMax-M2.7")
MINIMA_API_KEY = _os.environ.get("MINIMA_API_KEY", "")

# OpenAI 兼容（可选，也支持 DeepSeek / 通义千问 / 文心一言等）
OPENAI_API_URL = _os.environ.get("OPENAI_API_URL", "https://api.openai.com")
OPENAI_API_KEY = _os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = _os.environ.get("OPENAI_MODEL", "gpt-4o")

# ============================================================
# 搜索/研究配置
# ============================================================
TAVILY_API_KEY = _os.environ.get("TAVILY_API_KEY", "")

# ============================================================
# 数据模式
# ============================================================
USE_MOCK_DATA = False

# 报告配置
DEFAULT_OUTPUT_DIR = _os.path.dirname(_os.path.abspath(__file__))

# ETF 代码 → 跟踪指数映射
ETF_INDEX_MAP = {
    "510300": "000300.SH",  # 沪深300
    "510500": "000905.SH",  # 中证500
    "159915": "399006.SZ",  # 创业板
    "588000": "000688.SH",  # 科创50
    "588200": "000688.SH",  # 科创50ETF
    "512690": "931087.CSI", # 酒ETF
}

# 图表配置
CHART_DPI = 150
CHART_WIDTH = 10
CHART_HEIGHT = 5

# 数据获取配置
DEFAULT_NAV_DAYS = 250  # 默认获取最近250个交易日净值
DEFAULT_DAILY_DAYS = 250  # 默认获取最近250个交易日行情
TOP_HOLDINGS_COUNT = 10  # 前N大重仓股

# 费率评价标准
FEE_EXCELLENT = 0.6  # 总费率低于此值为优秀
FEE_GOOD = 1.0  # 总费率低于此值为良好

# 收益率评价标准
RETURN_1M_EXCELLENT = 5.0  # 1个月收益率
RETURN_3M_EXCELLENT = 10.0  # 3个月收益率
RETURN_1Y_EXCELLENT = 20.0  # 1年收益率

# 持仓集中度评价标准
CONCENTRATION_HIGH = 60.0  # 前十大占比超过此值为高集中度
CONCENTRATION_MEDIUM = 40.0  # 前十大占比超过此值为中等集中度

# 股票报告配置
STOCK_FINANCIAL_YEARS = 5   # 获取近5年财务数据
STOCK_DAILY_DAYS = 250      # 近250个交易日行情
TOP_HOLDERS_COUNT = 10      # 前十大股东
PE_HIGH = 50.0              # PE高于此值为高估
PE_LOW = 15.0               # PE低于此值为低估

