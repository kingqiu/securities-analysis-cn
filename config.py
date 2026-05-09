# 证券分析 - 全局配置文件

import os as _os
import re as _re
import time as _time
import threading as _threading

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

# 对比分析配置
MAX_COMPARE_COUNT = 5       # 最多同时对比5只标的

# ============================================================
# API 限流器（Tushare 接口限制 120次/分钟）
# ============================================================
API_RATE_LIMIT = int(_os.environ.get("API_RATE_LIMIT", "110"))  # 安全余量，默认110次/分钟
_API_WINDOW = 60  # 时间窗口（秒）


class _RateLimiter:
    """
    滑动窗口限流器。
    记录最近 _API_WINDOW 秒内的调用时间戳，
    如果已达上限则自动 sleep 等待，直到窗口滑过。
    线程安全。
    """

    def __init__(self, max_calls: int, window: int):
        self._max_calls = max_calls
        self._window = window
        self._timestamps: list[float] = []
        self._lock = _threading.Lock()

    def acquire(self):
        """在发起 API 调用前调用此方法，必要时会自动等待"""
        with self._lock:
            now = _time.time()
            cutoff = now - self._window
            # 清除过期时间戳
            self._timestamps = [t for t in self._timestamps if t > cutoff]

            if len(self._timestamps) >= self._max_calls:
                # 需要等待：算出最早那条记录何时过期
                wait_time = self._timestamps[0] - cutoff
                if wait_time > 0:
                    print(f"  ⏳ API限流：已达{self._max_calls}次/分钟上限，等待 {wait_time:.1f}s ...")
                    _time.sleep(wait_time + 0.1)  # 额外0.1s安全余量
                    # 清理过期时间戳
                    now = _time.time()
                    cutoff = now - self._window
                    self._timestamps = [t for t in self._timestamps if t > cutoff]

            self._timestamps.append(_time.time())


# 全局单例限流器，所有 call_api 共享
api_rate_limiter = _RateLimiter(API_RATE_LIMIT, _API_WINDOW)


# ============================================================
# Markdown → ReportLab 转换工具
# ============================================================

def md_to_rl(text: str) -> str:
    """
    将 AI 返回的 Markdown 文本转换为 ReportLab Paragraph 支持的 HTML 标签。
    处理：**粗体** → <b>粗体</b>，*斜体* → <i>斜体</i>，
         Markdown 列表标记 → 去掉或保留缩进，### 标题 → <b>标题</b>
    """
    if not text:
        return text

    # 处理标题：### 标题 → <b>标题</b>
    text = _re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=_re.MULTILINE)

    # 处理粗体：**text** 或 __text__
    text = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = _re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # 处理斜体：*text* 或 _text_（注意不要误伤已处理的粗体）
    text = _re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)

    # 处理行内代码：`code` → code
    text = _re.sub(r'`(.+?)`', r'\1', text)

    # 处理无序列表标记：- item 或 * item → • item
    text = _re.sub(r'^[\s]*[-*+]\s+', '• ', text, flags=_re.MULTILINE)

    # 处理有序列表标记：1. item → 保留数字但去掉多余空格
    text = _re.sub(r'^(\d+)\.\s+', r'\1. ', text, flags=_re.MULTILINE)

    return text


def md_to_story(text: str, body_style, table_builder=None):
    """
    将 AI 返回的 Markdown 文本（可能包含表格）转换为 ReportLab story 元素列表。
    - 普通文本 → Paragraph（使用 md_to_rl 转换标记）
    - Markdown 表格（| col1 | col2 | 格式） → ReportLab Table
    - 分隔线 --- → 跳过

    参数:
        text: AI 返回的原始文本
        body_style: ReportLab ParagraphStyle，用于普通段落
        table_builder: 可选，接收 data 二维列表和 col_widths 返回 Table 对象的函数
    返回:
        list: ReportLab story 元素列表
    """
    if not text:
        return []

    from reportlab.platypus import Paragraph as _Para, Spacer as _Spacer, Table as _Table, TableStyle as _TS
    from reportlab.lib import colors as _colors
    from reportlab.lib.units import cm as _cm

    elements = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # 跳过空行
        if not line:
            i += 1
            continue

        # 跳过纯分隔线（--- 或 ===）
        if _re.match(r'^[-=]{3,}$', line):
            i += 1
            continue

        # 检测 Markdown 表格：| xxx | yyy | 格式
        if line.startswith("|") and line.endswith("|") and "|" in line[1:-1]:
            table_lines = []
            while i < len(lines):
                ln = lines[i].strip()
                if ln.startswith("|") and ln.endswith("|"):
                    table_lines.append(ln)
                    i += 1
                elif not ln:
                    i += 1
                    break
                else:
                    break

            # 解析表格行
            rows = []
            for tl in table_lines:
                stripped = tl.strip("|")
                cells = [c.strip() for c in stripped.split("|")]
                # 跳过分隔行 |---|---|
                if all(_re.match(r'^[-:\s]+$', c) for c in cells if c):
                    continue
                rows.append(cells)

            if rows:
                if table_builder:
                    n_cols = len(rows[0])
                    col_w = [18 * _cm / n_cols] * n_cols
                    elements.append(table_builder(rows, col_widths=col_w))
                else:
                    n_cols = max(len(r) for r in rows)
                    for r in rows:
                        while len(r) < n_cols:
                            r.append("")
                    col_w = [18 * _cm / n_cols] * n_cols
                    style = _TS("md_tbl", [
                        ("BACKGROUND",    (0, 0), (-1, 0), _colors.HexColor("#c0392b")),
                        ("TEXTCOLOR",     (0, 0), (-1, 0), _colors.white),
                        ("FONTSIZE",      (0, 0), (-1, -1), 8),
                        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_colors.white, _colors.HexColor("#fff5f5")]),
                        ("GRID",          (0, 0), (-1, -1), 0.4, _colors.HexColor("#cccccc")),
                        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING",    (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ])
                    t = _Table(rows, colWidths=col_w, repeatRows=1)
                    t.setStyle(style)
                    elements.append(t)
                elements.append(_Spacer(1, 0.2 * _cm))
        else:
            # 普通文本行
            elements.append(_Para(md_to_rl(line), body_style))
            i += 1

    return elements

