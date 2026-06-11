#!/usr/bin/env python3
"""
步骤6：多标的对比分析 PDF 报告生成器
支持：股票对比（A股/港股）、ETF对比、混合对比
每个章节遵循"专业数据 + 说人话解读"原则
"""

import json
import os
import tempfile
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.rcParams["font.sans-serif"] = ["Arial Unicode MS", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ai_analysis import get_comparison_advice
from config import md_to_rl, md_to_story
from pdf_design import add_cover, add_report_reading_guide, draw_report_footer

# ── 字体注册 ──────────────────────────────────────────────────────────────────

def _register_fonts():
    candidates = [
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
        "/Library/Fonts/Arial Unicode MS.ttf",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("CN", path))
                return "CN"
            except Exception:
                continue
    return "Helvetica"

CN_FONT = _register_fonts()

# ── 配色方案（最多5只标的的颜色）────────────────────────────────────────────

COLORS_HEX = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6"]
COLORS_RGB = [
    (0.91, 0.30, 0.24),  # 红
    (0.20, 0.60, 0.86),  # 蓝
    (0.18, 0.80, 0.44),  # 绿
    (0.95, 0.61, 0.07),  # 橙
    (0.61, 0.35, 0.71),  # 紫
]

# ── 样式 ──────────────────────────────────────────────────────────────────────

def _styles():
    def s(name, **kw):
        return ParagraphStyle(name, fontName=CN_FONT, **kw)
    return {
        "title":    s("T",   fontSize=22, leading=28, alignment=TA_CENTER, spaceAfter=6),
        "subtitle": s("ST",  fontSize=13, leading=18, alignment=TA_CENTER, spaceAfter=4,
                       textColor=colors.HexColor("#555555")),
        "h1":       s("H1",  fontSize=14, leading=20, spaceBefore=14, spaceAfter=6,
                       textColor=colors.HexColor("#1a5276")),
        "h2":       s("H2",  fontSize=12, leading=16, spaceBefore=8, spaceAfter=4,
                       textColor=colors.HexColor("#2980b9")),
        "body":     s("B",   fontSize=10, leading=15, spaceAfter=4, alignment=TA_JUSTIFY),
        "explain":  s("EXP", fontSize=10, leading=15, spaceAfter=6, alignment=TA_LEFT,
                       textColor=colors.HexColor("#2c3e50"),
                       backColor=colors.HexColor("#eaf2f8"),
                       borderPadding=6),
        "caption":  s("C",   fontSize=8, leading=12, textColor=colors.grey,
                       alignment=TA_CENTER),
    }

# ── 表格工具 ─────────────────────────────────────────────────────────────────

def _tbl(data, col_widths=None, header_bg="#1a5276"):
    """生成统一风格的表格"""
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor(header_bg)),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, -1), CN_FONT),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#eaf2f8")]),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle(style_cmds))
    return t


def _safe(val, fmt=".2f", suffix="", default="N/A"):
    """安全格式化数值"""
    if val is None or val == "N/A" or val == "":
        return default
    try:
        v = float(val)
        return f"{v:{fmt}}{suffix}"
    except (TypeError, ValueError):
        return str(val)


def _safe_float(val, default=None):
    """安全转换浮点数"""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _cover_kind(compare_type):
    if compare_type == "etf":
        return "etf"
    if compare_type == "hk_stock":
        return "hk"
    return "stock"


def _sanitize_guidance_text(text):
    value = str(text or "")
    replacements = {
        "AI 对比建议": "模型对比解读",
        "AI对比建议": "模型对比解读",
        "AI分析建议": "模型研究解读",
        "投资建议": "研究参考",
        "买卖建议": "研究解读",
        "交易建议": "研究观察",
        "如果只能买一只": "若只看当前可见证据",
        "我推荐": "证据更支持关注",
        "推荐": "证据较强",
        "不推荐": "证据偏弱",
        "买入": "纳入观察",
        "卖出": "风险复核",
        "建仓": "建立观察",
        "加仓": "提高关注度",
        "减仓": "降低关注度",
        "止盈": "高估值复核",
        "止损": "风险复核",
        "仓位": "关注比例",
        "最佳选择": "证据相对更充分的样本",
        "更适合从": "可优先从",
        "适合长期放着当": "可作为长期核心暴露观察",
        "适合从": "可从",
        "想稳一点、流动性好，选": "若关注稳健与流动性，可观察",
        "能承受波动、追求弹性，选": "若关注弹性和波动承受，可观察",
        "选“大企业俱乐部”": "观察“大企业俱乐部”暴露",
        "选“中型企业拼盘”": "观察“中型企业拼盘”暴露",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    return value


def _comparison_cover_notes(compare_type, summaries, names):
    if compare_type == "etf":
        fees = [s.get("total_fee") for s in summaries if s.get("total_fee") not in (None, "N/A", "")]
        fee_text = f"费率样本 {min(fees)}%-{max(fees)}%/年" if fees else "费率数据需结合正文核验"
        return [
            ["核心结论", f"本报告比较 {len(names)} 只ETF的收益、跟踪质量、费率、规模和流动性，重点看产品差异而非给出配置结论。"],
            ["关注变量", f"指数估值、跟踪误差、折溢价、成交额、规模变化和{fee_text}。"],
            ["主要风险", "历史收益不代表未来，指数系统性波动、跟踪偏差和流动性变化都可能改变比较结果。"],
        ]
    industries = sorted(set(str(s.get("industry", "未知")) for s in summaries))
    return [
        ["核心结论", f"本报告比较 {len(names)} 个标的的估值、成长、盈利质量、财务健康和资金/流动性特征。"],
        ["关注变量", f"行业口径：{'、'.join(industries[:4])}；需区分同业可比和跨行业不可比。"],
        ["主要风险", "评分只反映当前可见数据的相对位置，不能替代公告核验、行业研究和个人风险承受能力判断。"],
    ]


def _comparison_cover_questions(compare_type):
    if compare_type == "etf":
        return ["指数暴露是否可比", "产品成本与跟踪质量", "流动性和折溢价风险"]
    if compare_type == "hk_stock":
        return ["估值与流动性折价", "南向资金和股东回报", "汇率与监管敏感度"]
    if compare_type == "mixed":
        return ["哪些指标可以横向比较", "哪些指标需要分市场理解", "风险暴露是否一致"]
    return ["估值是否可比", "成长和盈利质量", "风险暴露与反证条件"]


# ── 图表生成 ─────────────────────────────────────────────────────────────────

def _save_chart(fig, prefix="cmp"):
    """保存 matplotlib 图表到临时文件"""
    path = os.path.join(tempfile.gettempdir(), f"{prefix}_{id(fig)}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _extract_daily_series(data, code_type):
    """从原始数据中提取日期+收盘价序列，兼容 fields+items 格式和 dict-list 格式"""
    dates, closes = [], []

    # 确定使用哪个数据源
    if code_type == "etf":
        candidates = ["nav_data", "daily_data", "daily"]
    elif code_type == "hk_stock":
        candidates = ["hk_daily", "daily"]
    else:
        candidates = ["daily", "daily_basic", "daily_data"]

    for key in candidates:
        raw = data.get(key)
        if not raw:
            continue

        # 格式1：{"fields": [...], "items": [[...]]}（Tushare 原始格式）
        if isinstance(raw, dict) and "fields" in raw and "items" in raw:
            fields = raw["fields"]
            items = raw["items"]
            if not items:
                continue
            # 找到 trade_date / nav_date 列和 close / unit_nav 列
            date_idx = None
            close_idx = None
            for idx, f in enumerate(fields):
                if f in ("trade_date", "nav_date", "end_date"):
                    date_idx = idx
                if f in ("close", "unit_nav", "adj_close"):
                    close_idx = idx
            if date_idx is None or close_idx is None:
                continue
            for row in items:
                try:
                    d = str(row[date_idx])
                    c = float(row[close_idx])
                    if d and c:
                        dates.append(d)
                        closes.append(c)
                except (TypeError, ValueError, IndexError):
                    continue
            if dates:
                break

        # 格式2：[{trade_date: ..., close: ...}, ...]（dict 列表）
        elif isinstance(raw, list) and raw and isinstance(raw[0], dict):
            for row in raw:
                d = row.get("trade_date") or row.get("nav_date") or row.get("end_date")
                c = row.get("close") or row.get("unit_nav") or row.get("adj_close")
                if d and c:
                    try:
                        dates.append(str(d))
                        closes.append(float(c))
                    except (TypeError, ValueError):
                        continue
            if dates:
                break

    return dates, closes


def _chart_price_overlay(all_results, names):
    """归一化走势叠加图"""
    fig, ax = plt.subplots(figsize=(10, 5))

    for i, r in enumerate(all_results):
        data = r["data"]
        code_type = r["code_type"]

        dates, closes = _extract_daily_series(data, code_type)

        if len(closes) < 2:
            continue

        # 时间排序（从旧到新）
        if dates[0] > dates[-1]:
            dates.reverse()
            closes.reverse()

        # 归一化为涨跌幅百分比
        base = closes[0]
        pct = [(c / base - 1) * 100 for c in closes]

        ax.plot(range(len(pct)), pct, color=COLORS_HEX[i % len(COLORS_HEX)],
                linewidth=1.5, label=names[i], alpha=0.85)

    ax.axhline(y=0, color="grey", linestyle="--", linewidth=0.5, alpha=0.5)
    ax.set_title("走势叠加（归一化涨跌幅%）", fontsize=13)
    ax.set_ylabel("涨跌幅(%)")
    ax.set_xlabel("交易日")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _save_chart(fig, "price_overlay")


def _chart_bar_compare(names, values_dict, title, ylabel=""):
    """横向柱状图对比（多指标分组）"""
    fig, ax = plt.subplots(figsize=(10, 5))

    metrics = list(values_dict.keys())
    x = np.arange(len(metrics))
    n = len(names)
    width = 0.8 / n

    for i, name in enumerate(names):
        vals = [_safe_float(values_dict[m][i], 0) for m in metrics]
        bars = ax.bar(x + i * width - (n - 1) * width / 2, vals, width,
                      label=name, color=COLORS_HEX[i % len(COLORS_HEX)], alpha=0.85)
        # 在柱子上方标注数值
        for bar, v in zip(bars, vals):
            if v != 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f"{v:.1f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=9)
    ax.set_title(title, fontsize=13)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    return _save_chart(fig, "bar_compare")


# ── 数据提取辅助 ─────────────────────────────────────────────────────────────

def _to_dict_list(raw):
    """将 fields+items 格式转为 dict 列表；如果已经是 dict 列表则直接返回"""
    if isinstance(raw, dict) and "fields" in raw and "items" in raw:
        fields = raw["fields"]
        return [dict(zip(fields, row)) for row in raw.get("items", [])]
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        # 单个 dict，包装成列表
        return [raw]
    return []


def _get_rows(data, key):
    """从完整数据中取出某个 key 并转为 dict 列表"""
    raw = data.get(key)
    if raw is None:
        return []
    return _to_dict_list(raw)


def _get_realtime_quote(data):
    quote = data.get("realtime_quote")
    return quote if isinstance(quote, dict) else {}


def _display_name(r):
    data = r.get("data", {})
    for key in ("basic", "fund_basic", "hk_basic", "basic_info"):
        rows = _get_rows(data, key)
        if rows:
            name = rows[0].get("name") or rows[0].get("fullname")
            if name:
                return str(name)
    return str(r.get("name") or r.get("ts_code") or "未知标的")


def _display_code(r):
    data = r.get("data", {})
    for key in ("basic", "fund_basic", "hk_basic", "basic_info"):
        rows = _get_rows(data, key)
        if rows and rows[0].get("ts_code"):
            return str(rows[0].get("ts_code"))
    return str(r.get("ts_code") or "N/A")


def _extract_stock_summary(r):
    """从单只股票的完整数据中提取对比所需的关键指标"""
    data = r["data"]
    meta = r.get("meta", {})

    # 基本信息（尝试多个可能的 key）
    basic_rows = _get_rows(data, "basic") or _get_rows(data, "basic_info")
    basic = basic_rows[0] if basic_rows else {}

    # 日线估值
    db_rows = _get_rows(data, "daily_basic")
    latest_db = db_rows[0] if db_rows else {}

    # 财务数据
    income_rows = _get_rows(data, "income")
    latest_income = income_rows[0] if len(income_rows) >= 1 else {}
    prev_income = income_rows[1] if len(income_rows) >= 2 else {}

    fina_rows = _get_rows(data, "fina_indicator")
    latest_fina = fina_rows[0] if fina_rows else {}

    bs_rows = _get_rows(data, "balancesheet") or _get_rows(data, "balance_sheet")
    latest_bs = bs_rows[0] if bs_rows else {}

    cf_rows = _get_rows(data, "cashflow")
    latest_cf = cf_rows[0] if cf_rows else {}

    # 计算增速
    rev_growth = "N/A"
    profit_growth = "N/A"
    if latest_income and prev_income:
        try:
            cur_rev = float(latest_income.get("revenue", 0))
            prev_rev = float(prev_income.get("revenue", 0))
            if prev_rev > 0:
                rev_growth = round((cur_rev / prev_rev - 1) * 100, 2)
        except (TypeError, ValueError):
            pass
        try:
            cur_np = float(latest_income.get("n_income_attr_p", 0) or latest_income.get("n_income", 0))
            prev_np = float(prev_income.get("n_income_attr_p", 0) or prev_income.get("n_income", 0))
            if prev_np > 0:
                profit_growth = round((cur_np / prev_np - 1) * 100, 2)
        except (TypeError, ValueError):
            pass

    # 现金流/净利润
    cfo_ratio = "N/A"
    try:
        cfo = float(latest_cf.get("n_cashflow_act", 0))
        nip = float(latest_income.get("n_income_attr_p", 0) or latest_income.get("n_income", 0))
        if nip != 0:
            cfo_ratio = round(cfo / nip, 2)
    except (TypeError, ValueError):
        pass

    # 市值（亿元）
    market_cap = "N/A"
    try:
        mc = float(latest_db.get("total_mv", 0))
        if mc > 0:
            market_cap = round(mc / 10000, 1)  # 万元 → 亿元
    except (TypeError, ValueError):
        pass

    quote = _get_realtime_quote(data)
    cur_price = quote.get("price") if quote.get("price") is not None else latest_db.get("close", "N/A")

    return {
        "name": _display_name(r),
        "ts_code": _display_code(r),
        "industry": meta.get("industry") or basic.get("industry", "未知"),
        "market_cap": market_cap,
        "list_date": meta.get("list_date") or basic.get("list_date", "N/A"),
        "pe_ttm": latest_db.get("pe_ttm", "N/A"),
        "pb": latest_db.get("pb", "N/A"),
        "ps_ttm": latest_db.get("ps_ttm", "N/A"),
        "total_mv": latest_db.get("total_mv", "N/A"),
        "rev_growth": rev_growth,
        "profit_growth": profit_growth,
        "roe": latest_fina.get("roe", "N/A"),
        "gross_margin": latest_fina.get("grossprofit_margin", "N/A"),
        "netprofit_margin": latest_fina.get("netprofit_margin", "N/A"),
        "debt_ratio": latest_fina.get("debt_to_assets", latest_bs.get("total_liab_to_total_assets", "N/A")),
        "cfo_ratio": cfo_ratio,
        "dividend_yield": latest_db.get("dv_ttm", "N/A"),
        "cur_price": cur_price,
        "change_pct": quote.get("change_pct", "N/A"),
        "turnover_rate": quote.get("turnover_rate", "N/A"),
        "amount": quote.get("amount", "N/A"),
        "price_source": quote.get("source", "Tushare日线/估值"),
    }


def _extract_hk_stock_summary(r):
    """从港股数据中提取对比关键指标"""
    data = r["data"]
    meta = r.get("meta", {})

    basic_rows = _get_rows(data, "hk_basic") or _get_rows(data, "basic")
    basic = basic_rows[0] if basic_rows else {}

    daily_rows = _get_rows(data, "hk_daily") or _get_rows(data, "daily")
    latest = daily_rows[0] if daily_rows else {}
    quote = _get_realtime_quote(data)

    fina_rows = _get_rows(data, "hk_fina_indicator") or _get_rows(data, "fina_indicator")
    latest_fina = fina_rows[0] if fina_rows else {}

    income_rows = _get_rows(data, "hk_income") or _get_rows(data, "income")
    latest_income = income_rows[0] if income_rows else {}
    prev_income = income_rows[1] if len(income_rows) >= 2 else {}

    rev_growth = "N/A"
    profit_growth = "N/A"
    if latest_income and prev_income:
        try:
            cr = float(latest_income.get("revenue", 0))
            pr = float(prev_income.get("revenue", 0))
            if pr > 0:
                rev_growth = round((cr / pr - 1) * 100, 2)
        except (TypeError, ValueError):
            pass
        try:
            cn = float(latest_income.get("n_income", 0))
            pn = float(prev_income.get("n_income", 0))
            if pn > 0:
                profit_growth = round((cn / pn - 1) * 100, 2)
        except (TypeError, ValueError):
            pass

    return {
        "name": _display_name(r),
        "ts_code": _display_code(r),
        "industry": meta.get("industry", basic.get("industry", "未知")),
        "market_cap": "N/A",
        "list_date": basic.get("list_date", "N/A"),
        "pe_ttm": latest_fina.get("pe_ttm", latest.get("pe", "N/A")),
        "pb": latest_fina.get("pb", latest.get("pb", "N/A")),
        "ps_ttm": "N/A",
        "rev_growth": rev_growth,
        "profit_growth": profit_growth,
        "roe": latest_fina.get("roe_avg", "N/A"),
        "gross_margin": latest_fina.get("grossprofit_margin", "N/A"),
        "netprofit_margin": latest_fina.get("netprofit_margin", "N/A"),
        "debt_ratio": latest_fina.get("debt_to_assets", "N/A"),
        "cfo_ratio": "N/A",
        "dividend_yield": latest_fina.get("dividend_yield", "N/A"),
        "cur_price": quote.get("price") if quote.get("price") is not None else latest.get("close", "N/A"),
        "change_pct": quote.get("change_pct", "N/A"),
        "turnover_rate": quote.get("turnover_rate", "N/A"),
        "amount": quote.get("amount", "N/A"),
        "price_source": quote.get("source", "港股日线"),
    }


def _extract_etf_summary(r):
    """从 ETF 数据中提取对比关键指标"""
    data = r["data"]
    meta = r.get("meta", {})

    basic_rows = _get_rows(data, "fund_basic") or _get_rows(data, "basic")
    basic = basic_rows[0] if basic_rows else {}

    nav_rows = _get_rows(data, "nav_data") or _get_rows(data, "nav")
    quote = _get_realtime_quote(data)

    # 收益率计算 — 也需要尝试从 daily 的 fields+items 提取
    ret_1m, ret_3m, ret_1y = "N/A", "N/A", "N/A"

    # 提取净值序列
    navs = []
    if nav_rows:
        for row in nav_rows:
            try:
                navs.append(float(row.get("unit_nav") or row.get("close", 0)))
            except (TypeError, ValueError):
                pass
    if not navs:
        # fallback: 从 daily 的 fields+items 中提取 close
        _, close_list = _extract_daily_series(data, "etf")
        navs = close_list

    # 计算各区间收益率
    if len(navs) >= 2:
        cur = navs[0]
        if len(navs) >= 22 and navs[21] > 0:
            ret_1m = round((cur / navs[21] - 1) * 100, 2)
        if len(navs) >= 66 and navs[65] > 0:
            ret_3m = round((cur / navs[65] - 1) * 100, 2)
        if len(navs) >= 245 and navs[244] > 0:
            ret_1y = round((cur / navs[244] - 1) * 100, 2)

    # 费率
    mgmt_fee = basic.get("m_fee") or basic.get("management_fee", "N/A")
    custody_fee = basic.get("c_fee") or basic.get("custodian_fee", "N/A")
    total_fee = "N/A"
    try:
        total_fee = round(float(mgmt_fee) + float(custody_fee), 3)
    except (TypeError, ValueError):
        pass

    # 规模
    aum = "N/A"
    size_rows = _get_rows(data, "fund_size") or _get_rows(data, "share")
    if size_rows:
        try:
            raw_size = size_rows[0].get("net_asset") or size_rows[0].get("fd_share") or 0
            aum = round(float(raw_size) / 1e4, 2)
        except (TypeError, ValueError):
            pass

    return {
        "name": _display_name(r),
        "ts_code": _display_code(r),
        "fund_type": basic.get("fund_type", "ETF"),
        "benchmark": basic.get("benchmark", "N/A"),
        "found_date": basic.get("found_date") or basic.get("list_date", "N/A"),
        "management": basic.get("management", "N/A"),
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_1y": ret_1y,
        "total_fee": total_fee,
        "mgmt_fee": mgmt_fee,
        "custody_fee": custody_fee,
        "aum": aum,
        "tracking_error": data.get("tracking_error", "N/A"),
        "index_pe_pct": "N/A",
        "cur_price": quote.get("price", "N/A"),
        "change_pct": quote.get("change_pct", "N/A"),
        "turnover_rate": quote.get("turnover_rate", "N/A"),
        "amount": quote.get("amount", "N/A"),
        "price_source": quote.get("source", "N/A"),
    }


# ── 星级评分工具 ─────────────────────────────────────────────────────────────

def _stars(score):
    """数值(0-5)转星号文字"""
    full = int(round(score))
    full = max(0, min(5, full))
    return "★" * full + "☆" * (5 - full)


def _score_rank(values, higher_is_better=True):
    """对一组数值打分(1-5)，排名第一得5分"""
    valid = [(i, v) for i, v in enumerate(values) if v is not None]
    if not valid:
        return [3] * len(values)
    valid.sort(key=lambda x: x[1], reverse=higher_is_better)
    scores = [3] * len(values)
    n = len(valid)
    for rank, (idx, _) in enumerate(valid):
        scores[idx] = max(1, 5 - int(rank * 4 / max(n - 1, 1)))
    return scores


# ══════════════════════════════════════════════════════════════════════════════
# 主入口：create_comparison_pdf
# ══════════════════════════════════════════════════════════════════════════════

def create_comparison_pdf(all_results, compare_type, output_path):
    """
    生成多标的对比分析PDF报告。

    参数:
        all_results: [{ts_code, code_type, name, meta, data, data_file}, ...]
        compare_type: "etf" / "stock" / "hk_stock" / "mixed"
        output_path: 输出PDF路径
    """
    st = _styles()
    story = []
    count = len(all_results)
    date_str = datetime.now().strftime("%Y年%m月%d日")

    # ── 提取各标的摘要数据 ──
    summaries = []
    for r in all_results:
        ct = r["code_type"]
        if ct == "etf":
            summaries.append(_extract_etf_summary(r))
        elif ct == "hk_stock":
            summaries.append(_extract_hk_stock_summary(r))
        else:
            summaries.append(_extract_stock_summary(r))
    names = [s.get("name", _display_name(r)) for s, r in zip(summaries, all_results)]

    # ── 封面 ──
    if compare_type == "etf":
        title_text = "ETF基金对比分析报告"
    elif compare_type == "stock":
        industries = list(set(s.get("industry", "未知") for s in summaries))
        if len(industries) == 1 and industries[0] != "未知":
            title_text = f"{industries[0]}行业对比分析报告"
        else:
            title_text = "股票对比分析报告"
    elif compare_type == "hk_stock":
        title_text = "港股对比分析报告"
    else:
        title_text = "跨市场对比分析报告"

    cover_kind = _cover_kind(compare_type)
    add_cover(
        story,
        title_text,
        "多标的横向研究报告",
        [
            ["对比标的", f"{count} 个"],
            ["报告日期", date_str],
            ["标的范围", " / ".join(names)[:42]],
        ],
        kind=cover_kind,
        notes=_comparison_cover_notes(compare_type, summaries, names),
        questions=_comparison_cover_questions(compare_type),
    )

    add_report_reading_guide(story, kind=cover_kind, report_type="comparison")

    # ── 根据对比类型生成不同内容 ──
    if compare_type == "etf":
        _build_etf_comparison(story, st, all_results, summaries, names, count)
    else:
        _build_stock_comparison(story, st, all_results, summaries, names, count, compare_type)

    # ── 构建 PDF ──
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    doc.build(story, onFirstPage=lambda c, d: draw_report_footer(c, d, cover_kind), onLaterPages=lambda c, d: draw_report_footer(c, d, cover_kind))
    print(f"  ✓ PDF 已生成：{output_path}")


# ══════════════════════════════════════════════════════════════════════════════
# 股票对比报告（10章）
# ══════════════════════════════════════════════════════════════════════════════

def _build_stock_comparison(story, st, all_results, summaries, names, count, compare_type):
    """构建股票对比报告的全部章节"""

    # ── 第1章：对比概览 ──
    story.append(Paragraph("一、对比概览", st["h1"]))
    header = ["指标"] + names
    rows = [header]
    rows.append(["行业"] + [s.get("industry", "N/A") for s in summaries])
    rows.append(["市值(亿元)"] + [_safe(s.get("market_cap"), ".1f") for s in summaries])
    rows.append(["当前股价"] + [_safe(s.get("cur_price"), ".2f") for s in summaries])
    rows.append(["盘中涨跌(%)"] + [_safe(s.get("change_pct"), ".2f") for s in summaries])
    rows.append(["价格来源"] + [str(s.get("price_source", "N/A"))[:14] for s in summaries])
    rows.append(["PE(TTM)"] + [_safe(s.get("pe_ttm"), ".1f") for s in summaries])
    rows.append(["PB"] + [_safe(s.get("pb"), ".2f") for s in summaries])
    rows.append(["ROE(%)"] + [_safe(s.get("roe"), ".1f", "%") for s in summaries])
    rows.append(["股息率(%)"] + [_safe(s.get("dividend_yield"), ".2f", "%") for s in summaries])

    col_w = [3 * cm] + [3.5 * cm] * count
    story.append(_tbl(rows, col_widths=col_w))
    story.append(Spacer(1, 0.3 * cm))

    # 说人话
    industries = list(set(s.get("industry", "未知") for s in summaries))
    if len(industries) == 1 and industries[0] != "未知":
        explain = f"💡 这{count}家公司都属于{industries[0]}行业，规模和业务模式相近，适合直接对比。"
    else:
        explain = (f"💡 这{count}家公司分属不同行业（{'、'.join(industries)}），"
                   "估值标准不同，后续分析会考虑行业差异。")
    story.append(Paragraph(explain, st["explain"]))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第2章：模型对比解读 ──
    story.append(Paragraph("二、模型对比研究解读", st["h1"]))
    story.append(Paragraph(
        "以下由模型基于当前可见数据整理为对比研究解读，重点帮助理解差异来源，不构成任何交易判断。",
        st["explain"]
    ))
    story.append(Spacer(1, 0.2 * cm))

    ai_advice = _sanitize_guidance_text(get_comparison_advice(compare_type, summaries))
    story.extend(md_to_story(ai_advice, st["body"], table_builder=_tbl))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第3章：股价走势叠加 ──
    story.append(Paragraph("三、股价走势叠加", st["h1"]))
    try:
        chart_path = _chart_price_overlay(all_results, names)
        story.append(Image(chart_path, width=16 * cm, height=8 * cm))
    except Exception as e:
        story.append(Paragraph(f"（图表生成失败：{e}）", st["caption"]))
    story.append(Spacer(1, 0.2 * cm))

    # 说人话
    story.append(Paragraph(
        '这张图把所有股票的起点对齐到0%，用于观察同一时间窗口下的相对强弱。'
        '线在上方说明阶段表现更强，线在下方说明阶段表现更弱，但不代表后续走势判断。',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第4章：估值对比 ──
    story.append(Paragraph("四、估值对比", st["h1"]))

    val_data = {
        "PE(TTM)": [_safe_float(s.get("pe_ttm")) for s in summaries],
        "PB": [_safe_float(s.get("pb")) for s in summaries],
    }
    # PS 仅 A 股有
    ps_vals = [_safe_float(s.get("ps_ttm")) for s in summaries]
    if any(v is not None for v in ps_vals):
        val_data["PS(TTM)"] = ps_vals

    try:
        chart_path = _chart_bar_compare(names, val_data, "估值指标对比", "倍数")
        story.append(Image(chart_path, width=16 * cm, height=8 * cm))
    except Exception as e:
        story.append(Paragraph(f"（图表生成失败：{e}）", st["caption"]))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        '💡 PE（市盈率）= 你花多少年能靠公司利润「回本」。PE=25意味着「25年回本」，越低越「便宜」。'
        '但PE低不一定好——如果公司在走下坡路，便宜也有便宜的道理。'
        'PB（市净率）= 市场价是「家底」的几倍。PB=1说明「按成本价在卖」，PB=8说明市场非常看好。',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第5章：成长性对比 ──
    story.append(Paragraph("五、成长性对比", st["h1"]))

    growth_data = {
        "营收增速(%)": [_safe_float(s.get("rev_growth")) for s in summaries],
        "净利增速(%)": [_safe_float(s.get("profit_growth")) for s in summaries],
    }
    try:
        chart_path = _chart_bar_compare(names, growth_data, "成长性对比", "%")
        story.append(Image(chart_path, width=16 * cm, height=8 * cm))
    except Exception as e:
        story.append(Paragraph(f"（图表生成失败：{e}）", st["caption"]))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        '💡 营收增速 = 今年比去年多卖了多少钱（好比奶茶店去年卖100万今年卖120万，增速就是20%）。'
        '净利增速 = 扣掉所有成本后多赚了多少。增速高说明公司「越来越能赚钱」。'
        '如果一家公司PE高但增速也高，说明「贵得有道理」。',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第6章：盈利质量对比 ──
    story.append(Paragraph("六、盈利质量对比（DuPont视角）", st["h1"]))

    profit_rows = [["指标"] + names]
    profit_rows.append(["ROE(%)"] + [_safe(s.get("roe"), ".1f") for s in summaries])
    profit_rows.append(["毛利率(%)"] + [_safe(s.get("gross_margin"), ".1f") for s in summaries])
    profit_rows.append(["净利率(%)"] + [_safe(s.get("netprofit_margin"), ".1f") for s in summaries])
    profit_rows.append(["经营现金流/净利润"] + [_safe(s.get("cfo_ratio"), ".2f") for s in summaries])

    story.append(_tbl(profit_rows, col_widths=col_w))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph(
        '💡 ROE（净资产收益率）= 股东每投入100元一年能赚多少。ROE=30%表示「投100赚30」，非常优秀。'
        'ROE可以拆解为三个部分理解（DuPont分析法）：'
        '①净利率 = 每卖100元能剩多少利润（赚钱能力）；'
        '②资产周转率 = 一年能把钱转几圈（经营效率）；'
        '③杠杆 = 借了多少倍的钱（财务风险）。'
        '好比开奶茶店：净利率是「每杯赚多少」，周转率是「一天卖几杯」，杠杆是「借了多少钱开店」。',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第7章：财务健康度对比 ──
    story.append(Paragraph("七、财务健康度对比", st["h1"]))

    health_rows = [["指标"] + names]
    health_rows.append(["资产负债率(%)"] + [_safe(s.get("debt_ratio"), ".1f") for s in summaries])
    health_rows.append(["经营现金流/净利润"] + [_safe(s.get("cfo_ratio"), ".2f") for s in summaries])

    story.append(_tbl(health_rows, col_widths=col_w))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph(
        '💡 资产负债率 = 公司有多少钱是借的。50%意味着「家底的一半是借来的」。'
        '低了安全但可能太保守，高了进取但有风险。一般来说低于60%比较健康。'
        '经营现金流/净利润 = 赚的钱是不是「真金白银」。大于1说明赚的都是真钱，'
        '小于1说明有些利润可能是「赊账」赚来的（卖了东西但钱还没收到）。',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第8章：分红与股东回报 ──
    story.append(Paragraph("八、分红与股东回报", st["h1"]))

    div_rows = [["指标"] + names]
    div_rows.append(["股息率(%)"] + [_safe(s.get("dividend_yield"), ".2f") for s in summaries])

    story.append(_tbl(div_rows, col_widths=col_w))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph(
        '股息率 = 按当前价格估算的年度现金分红比例。股息率2%意味着名义上每10万元市值对应约2000元年度分红。'
        '股息率高的公司通常更成熟，但仍需观察盈利稳定性、分红持续性和再投资空间。',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第9章：资金面对比（仅A股有意义）──
    has_stock = any(r["code_type"] == "stock" for r in all_results)
    if has_stock:
        story.append(Paragraph("九、资金面信号（仅A股）", st["h1"]))
        story.append(Paragraph(
            '资金面反映的是不同资金在一段时间内的流入流出状态。主力净流入可作为风险偏好改善的观察线索，'
            '股东人数减少可能意味着筹码集中度提升，但这些指标都需要和价格、成交额及基本面交叉验证。'
            '（注：港股标的不显示此数据）',
            st["explain"]
        ))
        story.append(Spacer(1, 0.3 * cm))

        mf_rows = [["指标"] + names]
        for r, s in zip(all_results, summaries):
            pass  # 资金面数据需要从原始数据提取，此处简化
        story.append(Paragraph("（资金面数据详见各标的单独报告）", st["body"]))
        story.append(Spacer(1, 0.5 * cm))

    # ── 第10章：综合评分 ──
    chapter_num = "十" if has_stock else "九"
    story.append(Paragraph(f"{chapter_num}、综合评分表", st["h1"]))

    # 计算各维度分数
    pe_scores = _score_rank([_safe_float(s.get("pe_ttm")) for s in summaries], higher_is_better=False)
    growth_scores = _score_rank([_safe_float(s.get("profit_growth")) for s in summaries], higher_is_better=True)
    roe_scores = _score_rank([_safe_float(s.get("roe")) for s in summaries], higher_is_better=True)
    health_scores = _score_rank([_safe_float(s.get("debt_ratio")) for s in summaries], higher_is_better=False)
    div_scores = _score_rank([_safe_float(s.get("dividend_yield")) for s in summaries], higher_is_better=True)

    score_rows = [["维度"] + names]
    score_rows.append(["估值性价比"] + [_stars(s) for s in pe_scores])
    score_rows.append(["成长性"] + [_stars(s) for s in growth_scores])
    score_rows.append(["盈利质量"] + [_stars(s) for s in roe_scores])
    score_rows.append(["财务健康"] + [_stars(s) for s in health_scores])
    score_rows.append(["分红回报"] + [_stars(s) for s in div_scores])

    # 综合得分
    total_scores = []
    for i in range(count):
        total = (pe_scores[i] * 25 + growth_scores[i] * 25 +
                 roe_scores[i] * 20 + health_scores[i] * 15 + div_scores[i] * 15)
        total_scores.append(total)
    score_rows.append(["综合得分"] + [str(s) for s in total_scores])

    story.append(_tbl(score_rows, col_widths=col_w))
    story.append(Spacer(1, 0.2 * cm))

    # 找出综合得分最高的
    best_idx = total_scores.index(max(total_scores))
    story.append(Paragraph(
        f"综合来看，{names[best_idx]}在本报告的量化维度中得分最高（{total_scores[best_idx]}分），代表当前可见证据相对更充分。"
        f"评分权重：估值性价比25% + 成长性25% + 盈利质量20% + 财务健康15% + 分红回报15%。"
        f"★越多越好，综合得分满分500分。"
        f"请注意：评分仅基于历史数据和已接入指标的相对比较，不构成投资建议。",
        st["explain"]
    ))


# ══════════════════════════════════════════════════════════════════════════════
# ETF 对比报告（10章）
# ══════════════════════════════════════════════════════════════════════════════

def _build_etf_comparison(story, st, all_results, summaries, names, count):
    """构建 ETF 对比报告的全部章节"""

    col_w = [3 * cm] + [3.5 * cm] * count

    # ── 第1章：基金概览 ──
    story.append(Paragraph("一、基金概览", st["h1"]))

    rows = [["指标"] + names]
    rows.append(["基金代码"] + [s.get("ts_code", "N/A") for s in summaries])
    rows.append(["基金公司"] + [str(s.get("management", "N/A"))[:8] for s in summaries])
    rows.append(["成立日期"] + [str(s.get("found_date", "N/A")) for s in summaries])
    rows.append(["规模(亿元)"] + [_safe(s.get("aum"), ".2f") for s in summaries])
    rows.append(["综合费率(%/年)"] + [_safe(s.get("total_fee"), ".3f") for s in summaries])
    rows.append(["场内价格"] + [_safe(s.get("cur_price"), ".3f") for s in summaries])
    rows.append(["盘中涨跌(%)"] + [_safe(s.get("change_pct"), ".2f") for s in summaries])

    story.append(_tbl(rows, col_widths=col_w))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        'ETF可以理解为跟踪一篮子资产的工具，不同ETF对应不同指数暴露。'
        '不同ETF追踪不同的指数（比如沪深300=最大的300家公司、中证500=排名301-800的中型公司）。'
        '规模越大的ETF通常流动性和存续稳定性更好。',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第2章：模型对比解读 ──
    story.append(Paragraph("二、模型对比研究解读", st["h1"]))
    story.append(Paragraph(
        "以下由模型基于当前可见数据整理为对比研究解读，重点帮助理解产品差异，不构成任何配置或交易判断。",
        st["explain"]
    ))

    ai_advice = _sanitize_guidance_text(get_comparison_advice("etf", summaries))
    story.extend(md_to_story(ai_advice, st["body"], table_builder=_tbl))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第3章：走势叠加图 ──
    story.append(Paragraph("三、净值走势叠加", st["h1"]))
    try:
        chart_path = _chart_price_overlay(all_results, names)
        story.append(Image(chart_path, width=16 * cm, height=8 * cm))
    except Exception as e:
        story.append(Paragraph(f"（图表生成失败：{e}）", st["caption"]))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "这张图把各基金放在同一时间窗口里观察相对表现。"
        "线在上方代表阶段表现更强，线在下方代表阶段表现更弱，但不代表未来表现。",
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第4章：收益率对比 ──
    story.append(Paragraph("四、收益率对比", st["h1"]))

    ret_data = {
        "近1月(%)": [_safe_float(s.get("ret_1m")) for s in summaries],
        "近3月(%)": [_safe_float(s.get("ret_3m")) for s in summaries],
        "近1年(%)": [_safe_float(s.get("ret_1y")) for s in summaries],
    }
    try:
        chart_path = _chart_bar_compare(names, ret_data, "收益率对比", "%")
        story.append(Image(chart_path, width=16 * cm, height=8 * cm))
    except Exception as e:
        story.append(Paragraph(f"（图表生成失败：{e}）", st["caption"]))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        '收益率用于观察基金在不同周期里的净值变化。'
        '近1年收益率10%意味着过去一年净值大约上涨10%。'
        '较长周期通常比单月表现更能反映产品与指数暴露的阶段特征。',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第5章：风险指标对比 ──
    story.append(Paragraph("五、风险指标对比", st["h1"]))
    story.append(Paragraph(
        '💡 投资不能只看收益，还要看风险。好比坐车：收益是「目的地有多远」，风险是「路上有多颠」。',
        st["explain"]
    ))
    story.append(Paragraph(
        "波动率 = 价格上下波动的程度。高波动 = 坐过山车，低波动 = 坐高铁。\n"
        "最大回撤 = 从阶段最高点到最低点的最大跌幅。-20%意味着历史区间内曾从高点回落约两成。\n"
        "夏普比率 = 每承受1份风险换来多少收益。大于1表示值得，小于0表示冒了险还亏钱。",
        st["body"]
    ))
    story.append(Paragraph("（风险指标需要较长时间序列计算，详见各基金单独报告）", st["caption"]))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第6章：跟踪效率对比 ──
    story.append(Paragraph("六、跟踪效率对比", st["h1"]))

    te_rows = [["指标"] + names]
    te_rows.append(["年化跟踪误差(%)"] + [_safe(s.get("tracking_error"), ".2f") for s in summaries])

    story.append(_tbl(te_rows, col_widths=col_w))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        '💡 ETF的本质是「复印机」——它的工作是精确复制指数的走势。跟踪误差就是「复印的清晰度」：\n'
        '误差 <0.5% = 复印得很清楚（优秀）；0.5-1% = 有点模糊但还行；>1% = 复制偏差需要重点复核。'
        '误差越小说明基金管理人越尽职。',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第7章：成本对比 ──
    story.append(Paragraph("七、成本对比", st["h1"]))

    fee_rows = [["指标"] + names]
    fee_rows.append(["管理费(%/年)"] + [_safe(s.get("mgmt_fee"), ".3f") for s in summaries])
    fee_rows.append(["托管费(%/年)"] + [_safe(s.get("custody_fee"), ".3f") for s in summaries])
    fee_rows.append(["合计费率(%/年)"] + [_safe(s.get("total_fee"), ".3f") for s in summaries])

    story.append(_tbl(fee_rows, col_widths=col_w))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        '💡 费率就是基金公司每年从你的收益里扣掉的「服务费」。'
        '0.5%和0.15%看起来差别小，但投10万持有10年，差距能到3000-5000元。'
        '在指数暴露和跟踪质量相近时，费率越低通常越有成本优势。',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第8章：流动性对比 ──
    story.append(Paragraph("八、流动性对比", st["h1"]))

    liq_rows = [["指标"] + names]
    liq_rows.append(["基金规模(亿元)"] + [_safe(s.get("aum"), ".2f") for s in summaries])
    liq_rows.append(["换手率(%)"] + [_safe(s.get("turnover_rate"), ".2f") for s in summaries])
    liq_rows.append(["成交额(元)"] + [_safe(s.get("amount"), ".0f") for s in summaries])

    story.append(_tbl(liq_rows, col_widths=col_w))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "流动性 = 场内成交是否活跃、价格是否容易偏离净值。"
        "规模和成交额较大的ETF通常成交体验更稳定。"
        "规模太小（<2亿元）的ETF有被清盘的风险（基金公司觉得不赚钱就关掉了，你的钱会按净值退回来但很被动）。",
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第9章：持仓分析对比 ──
    story.append(Paragraph("九、持仓分析对比", st["h1"]))
    story.append(Paragraph(
        'ETF背后是一篮子成分证券，这部分用于观察指数暴露、行业结构和集中度。'
        '（持仓明细详见各基金单独报告）',
        st["explain"]
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── 第10章：综合评分 ──
    story.append(Paragraph("十、综合评分表", st["h1"]))

    ret_1y_scores = _score_rank([_safe_float(s.get("ret_1y")) for s in summaries], higher_is_better=True)
    fee_scores = _score_rank([_safe_float(s.get("total_fee")) for s in summaries], higher_is_better=False)
    te_scores = _score_rank([_safe_float(s.get("tracking_error")) for s in summaries], higher_is_better=False)
    aum_scores = _score_rank([_safe_float(s.get("aum")) for s in summaries], higher_is_better=True)

    score_rows = [["维度"] + names]
    score_rows.append(["近1年收益"] + [_stars(s) for s in ret_1y_scores])
    score_rows.append(["费率成本"] + [_stars(s) for s in fee_scores])
    score_rows.append(["跟踪精度"] + [_stars(s) for s in te_scores])
    score_rows.append(["规模流动性"] + [_stars(s) for s in aum_scores])

    total_scores = []
    for i in range(count):
        total = (ret_1y_scores[i] * 30 + fee_scores[i] * 25 +
                 te_scores[i] * 25 + aum_scores[i] * 20)
        total_scores.append(total)
    score_rows.append(["综合得分"] + [str(s) for s in total_scores])

    story.append(_tbl(score_rows, col_widths=col_w))
    story.append(Spacer(1, 0.2 * cm))

    best_idx = total_scores.index(max(total_scores))
    story.append(Paragraph(
        f"综合来看，{names[best_idx]}在本报告的量化维度中得分最高（{total_scores[best_idx]}分），代表当前可见证据相对更充分。"
        f"评分权重：近1年收益30% + 费率成本25% + 跟踪精度25% + 规模流动性20%。"
        f"★越多越好，综合得分满分500分。"
        f"请注意：评分仅基于历史数据和已接入指标的相对比较，不构成投资建议。",
        st["explain"]
    ))
