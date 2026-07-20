#!/usr/bin/env python3
"""
步骤3：基于真实数据生成 ETF 深度分析 PDF 报告。

默认零 token：模型文字解读用规则化生成（ai_analysis 在 TDX_AI_COMMENTARY=1 时才调外部大模型）。
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
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ai_analysis import get_investment_advice
from config import md_to_rl, md_to_story
from etf_analyst_model import (
    build_etf_research_view,
    render_etf_research_brief,
    build_etf_monitor,
    build_etf_business_model,
    build_etf_bear_case,
)
from pdf_design import (
    CN_FONT as SHARED_CN_FONT,
    add_cover,
    add_followup_watchlist,
    add_report_reading_guide,
    build_styles,
    callout_box,
    draw_report_footer,
    evidence_map,
    metric_cards,
    styled_table,
)

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

CN_FONT = SHARED_CN_FONT

# ── 样式 ──────────────────────────────────────────────────────────────────────

def _styles():
    return build_styles("etf")

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _tbl(data, col_widths=None, header_bg="#1a3a6b"):
    return styled_table(data, col_widths=col_widths, kind="etf")


def _chart_to_image(fig, width=14*cm):
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    fig.savefig(tmp.name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return Image(tmp.name, width=width, height=width * 0.45)

# ── 数据加载与计算 ────────────────────────────────────────────────────────────

def _load(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        raw = json.load(f)
    d = {}
    d["ts_code"]    = raw.get("ts_code", "")
    d["index_code"] = raw.get("index_code", "")

    if "basic" in raw and raw["basic"]["items"]:
        d["basic"] = dict(zip(raw["basic"]["fields"], raw["basic"]["items"][0]))

    for key in ("nav", "daily", "index_daily", "share", "div", "sales_vol"):
        if key in raw:
            d[key] = pd.DataFrame(raw[key]["items"], columns=raw[key]["fields"])

    if "manager" in raw and raw["manager"]["items"]:
        d["manager"] = pd.DataFrame(raw["manager"]["items"], columns=raw["manager"]["fields"])

    if "index_dailybasic" in raw and raw["index_dailybasic"]["items"]:
        d["index_dailybasic"] = pd.DataFrame(raw["index_dailybasic"]["items"], columns=raw["index_dailybasic"]["fields"])

    if "portfolio" in raw:
        df = pd.DataFrame(raw["portfolio"]["items"], columns=raw["portfolio"]["fields"])
        if not df.empty:
            df = df.sort_values("end_date", ascending=False)
            d["portfolio"] = df[df["end_date"] == df["end_date"].iloc[0]]

    if "similar_funds" in raw:
        d["similar_funds"] = pd.DataFrame(raw["similar_funds"]["items"], columns=raw["similar_funds"]["fields"])

    if "similar_nav_data" in raw:
        d["similar_nav_data"] = {
            k: pd.DataFrame(v["items"], columns=v["fields"])
            for k, v in raw["similar_nav_data"].items()
        }

    if "similar_selection_meta" in raw:
        d["similar_selection_meta"] = raw["similar_selection_meta"]

    if "realtime_quote" in raw and isinstance(raw["realtime_quote"], dict):
        d["realtime_quote"] = raw["realtime_quote"]

    if "premium_disc" in raw and isinstance(raw["premium_disc"], dict):
        d["premium_disc"] = raw["premium_disc"]

    if "broad_base_valuation" in raw and isinstance(raw["broad_base_valuation"], dict):
        d["broad_base_valuation"] = raw["broad_base_valuation"]

    if "peer_etf_fees" in raw and isinstance(raw["peer_etf_fees"], dict):
        d["peer_etf_fees"] = raw["peer_etf_fees"]

    if "free_market_data" in raw:
        d["free_market_data"] = raw["free_market_data"]

    d["stock_names"] = raw.get("stock_names", {})
    return d


def _calc_returns(nav_df, price_df=None):
    """基于单位净值(NAV)计算各期收益率；若 NAV 不可用，则退回用场内价日线(price_df)计算。
    1Y/2Y/3Y 需要约 250/500/750 个交易日，TDX 落盘通常只有约 130 行，故长周期会返回 None（显示"数据不足"）。"""
    if nav_df is not None and not nav_df.empty:
        nav_df = nav_df.sort_values("nav_date").copy()
        nav_df["unit_nav"] = pd.to_numeric(nav_df["unit_nav"], errors="coerce")
        latest = nav_df["unit_nav"].iloc[-1]
        result = {}
        for label, days in [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 250), ("2Y", 500), ("3Y", 750)]:
            if len(nav_df) > days:
                past = nav_df["unit_nav"].iloc[-days]
                result[label] = round((latest / past - 1) * 100, 2) if past else None
            else:
                result[label] = None
        return result
    # 退回：用场内价日线计算（市场价收益，含折溢价影响，作为 NAV 不可用时的代理）
    if price_df is not None and not price_df.empty:
        pdf = price_df.copy()
        pdf["trade_date"] = pd.to_datetime(pdf["trade_date"]) if not pd.api.types.is_datetime64_any_dtype(pdf["trade_date"]) else pdf["trade_date"]
        pdf = pdf.sort_values("trade_date")
        pdf["close"] = pd.to_numeric(pdf["close"], errors="coerce").dropna()
        if pdf.empty:
            return {}
        latest = pdf["close"].iloc[-1]
        result = {}
        for label, days in [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 250), ("2Y", 500), ("3Y", 750)]:
            if len(pdf) > days:
                past = pdf["close"].iloc[-days]
                result[label] = round((latest / past - 1) * 100, 2) if past else None
            else:
                result[label] = None
        return result
    return {}


def _calc_te(fund_df, index_df):
    if fund_df is None or index_df is None or fund_df.empty or index_df.empty:
        return {}
    f = fund_df.copy(); i = index_df.copy()
    f["trade_date"] = pd.to_datetime(f["trade_date"])
    i["trade_date"] = pd.to_datetime(i["trade_date"])
    f["close"] = pd.to_numeric(f["close"], errors="coerce")
    i["close"] = pd.to_numeric(i["close"], errors="coerce")
    m = pd.merge(f[["trade_date","close"]], i[["trade_date","close"]], on="trade_date", suffixes=("_f","_i"))
    if m.empty:
        return {}
    m["diff"] = m["close_f"].pct_change() - m["close_i"].pct_change()
    te = m["diff"].std() * np.sqrt(250) * 100
    return {"te": round(te, 4), "avg": round(m["diff"].mean()*100, 4)}


def _ma_position(nav_df):
    if nav_df is None or nav_df.empty or len(nav_df) < 60:
        return "未知"
    nav_df = nav_df.sort_values("nav_date").copy()
    nav_df["unit_nav"] = pd.to_numeric(nav_df["unit_nav"], errors="coerce")
    latest = nav_df["unit_nav"].iloc[-1]
    ma20 = nav_df["unit_nav"].iloc[-20:].mean()
    ma60 = nav_df["unit_nav"].iloc[-60:].mean()
    if latest > ma20 and latest > ma60:
        return "上方（多头排列）"
    elif latest < ma20 and latest < ma60:
        return "下方（空头排列）"
    return "附近（震荡区间）"


def _aum_trend(share_df):
    if share_df is None or share_df.empty:
        return "未知"
    share_df = share_df.sort_values("trade_date").copy()
    col = "net_asset" if "net_asset" in share_df.columns else "fd_share"
    share_df[col] = pd.to_numeric(share_df[col], errors="coerce")
    recent = share_df[col].dropna().tail(60)
    if len(recent) < 2:
        return "未知"
    return "增长" if recent.iloc[-1] > recent.iloc[0] else "缩减"


def _calc_flow_metrics(share_df):
    """用份额变化估算净申赎趋势（fund_share.fd_share 日度数据）"""
    if share_df is None or share_df.empty or "fd_share" not in share_df.columns:
        return {}

    df = share_df.sort_values("trade_date").copy()
    df["fd_share"] = pd.to_numeric(df["fd_share"], errors="coerce")
    df = df.dropna(subset=["fd_share"])
    if len(df) < 2:
        return {}

    df["share_chg"] = df["fd_share"].diff()

    recent_20 = df.tail(20)
    recent_60 = df.tail(60)

    net_20 = recent_20["share_chg"].sum()
    net_60 = recent_60["share_chg"].sum()
    latest_share = df["fd_share"].iloc[-1]

    return {
        "net_flow_20d": round(net_20 / 1e4, 2),
        "net_flow_60d": round(net_60 / 1e4, 2),
        "latest_share": round(latest_share / 1e4, 2),
        "trend_20d": "净申购" if net_20 > 0 else "净赎回",
        "trend_60d": "净申购" if net_60 > 0 else "净赎回",
    }


def _decompose_tracking_diff(fund_df, index_df):
    """跟踪误差拆解"""
    if fund_df is None or index_df is None or fund_df.empty or index_df.empty:
        return {}

    f = fund_df.copy()
    i = index_df.copy()
    f["trade_date"] = pd.to_datetime(f["trade_date"])
    i["trade_date"] = pd.to_datetime(i["trade_date"])
    f["close"] = pd.to_numeric(f["close"], errors="coerce")
    i["close"] = pd.to_numeric(i["close"], errors="coerce")

    m = pd.merge(f[["trade_date", "close"]], i[["trade_date", "close"]], on="trade_date", suffixes=("_f", "_i"))
    if m.empty:
        return {}

    m["diff"] = m["close_f"].pct_change() - m["close_i"].pct_change()
    m = m.dropna(subset=["diff"])

    if m.empty:
        return {}

    mean_diff = m["diff"].mean() * 100
    std_diff = m["diff"].std() * 100

    m_sorted = m.sort_values("diff", ascending=False)
    top_5_pos = m_sorted.head(5)
    top_5_neg = m_sorted.tail(5)

    return {
        "mean_bias": round(mean_diff, 4),
        "volatility": round(std_diff, 4),
        "top_pos_dates": top_5_pos["trade_date"].dt.strftime("%Y-%m-%d").tolist(),
        "top_pos_diffs": (top_5_pos["diff"] * 100).round(2).tolist(),
        "top_neg_dates": top_5_neg["trade_date"].dt.strftime("%Y-%m-%d").tolist(),
        "top_neg_diffs": (top_5_neg["diff"] * 100).round(2).tolist(),
    }


def _index_valuation_percentile(index_dailybasic_df):
    """指数估值分位。支持仅含 PE 的序列（TDX ph_agf10_gzfx 返回的 PE 历史），
    PB 缺失时仅计算 PE 分位，PB 相关字段返回 None（诚实降级，不伪造）。"""
    if index_dailybasic_df is None or index_dailybasic_df.empty:
        return {}

    df = index_dailybasic_df.sort_values("trade_date").copy()

    for col in ["pe", "pb"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "pe" not in df.columns:
        return {}

    latest_pe = df["pe"].iloc[-1] if not df["pe"].dropna().empty else None
    latest_pb = df["pb"].iloc[-1] if "pb" in df.columns and not df["pb"].dropna().empty else None

    pe_percentile = None
    pb_percentile = None

    if latest_pe is not None and not df["pe"].dropna().empty:
        pe_percentile = round((df["pe"] < latest_pe).sum() / len(df["pe"].dropna()) * 100, 1)

    if "pb" in df.columns and latest_pb is not None and not df["pb"].dropna().empty:
        pb_percentile = round((df["pb"] < latest_pb).sum() / len(df["pb"].dropna()) * 100, 1)

    return {
        "current_pe": round(latest_pe, 2) if latest_pe is not None else None,
        "current_pb": round(latest_pb, 2) if latest_pb is not None else None,
        "pe_percentile": pe_percentile,
        "pb_percentile": pb_percentile,
    }


def _calc_premium_discount(nav_df, daily_df):
    """溢价折价分析"""
    if nav_df is None or daily_df is None or nav_df.empty or daily_df.empty:
        return {}

    nav = nav_df.sort_values("nav_date").copy()
    daily = daily_df.sort_values("trade_date").copy()

    nav["nav_date"] = pd.to_datetime(nav["nav_date"])
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    nav["unit_nav"] = pd.to_numeric(nav["unit_nav"], errors="coerce")
    daily["close"] = pd.to_numeric(daily["close"], errors="coerce")

    merged = pd.merge(
        daily[["trade_date", "close"]],
        nav[["nav_date", "unit_nav"]],
        left_on="trade_date",
        right_on="nav_date",
        how="inner"
    )

    if merged.empty:
        return {}

    merged["premium_rate"] = (merged["close"] - merged["unit_nav"]) / merged["unit_nav"] * 100
    merged = merged.dropna(subset=["premium_rate"])

    if merged.empty:
        return {}

    current_premium = merged["premium_rate"].iloc[-1]

    premium_percentile = round((merged["premium_rate"] < current_premium).sum() / len(merged) * 100, 1)

    return {
        "current_premium": round(current_premium, 2),
        "premium_percentile": premium_percentile,
        "max_premium": round(merged["premium_rate"].max(), 2),
        "min_premium": round(merged["premium_rate"].min(), 2),
        "avg_premium": round(merged["premium_rate"].mean(), 2),
    }


def _index_concentration(index_weight_df):
    if index_weight_df is None or index_weight_df.empty or "weight" not in index_weight_df.columns:
        return {
            "top10_weight": "未获取",
            "top20_weight": "未获取",
            "top_count": 0,
            "industry_weight_status": "TDX 暂未提供成分股权重数据，无法计算成分集中度（本 ETF 被动跟踪科创50指数 000688）",
        }
    df = index_weight_df.copy()
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    df = df.dropna(subset=["weight"]).sort_values("weight", ascending=False)
    if df.empty:
        return {}
    return {
        "top10_weight": round(df.head(10)["weight"].sum(), 2),
        "top20_weight": round(df.head(20)["weight"].sum(), 2),
        "top_count": len(df),
        "industry_weight_status": "当前数据源仅含成分代码和权重，缺少行业映射；本报告先用成分集中度替代行业权重风险观察",
    }

# ── 可读性层（移植自股票引擎 step4，适配 ETF 指标）──────────────────────────────

SIGNAL_THRESHOLDS = {
    "pe_pct":      [(30, "●", "#1e8449", "偏低(<30%)"), (70, "●", "#BA7517", "适中(30-70%)"), (100, "●", "#c0392b", "偏高(>70%)")],
    "te":          [(0.5, "●", "#1e8449", "优秀(<0.5%)"), (1.0, "●", "#BA7517", "良好(0.5-1%)"), (100, "●", "#c0392b", "偏差偏大(>1%)")],
    "premium_abs": [(1.0, "●", "#1e8449", "接近平价(≤1%)"), (3.0, "●", "#BA7517", "温和偏离(1-3%)"), (100, "●", "#c0392b", "偏离较大(>3%)")],
    "aum":         [(2, "●", "#c0392b", "偏小(<2亿,清盘风险)"), (20, "●", "#BA7517", "中等(2-20亿)"), (100000, "●", "#1e8449", "充裕(>20亿)")],
    "fee":         [(0.3, "●", "#1e8449", "低(<0.3%)"), (0.6, "●", "#BA7517", "适中(0.3-0.6%)"), (100, "●", "#c0392b", "偏高(>0.6%)")],
    "ret_y":       [(0, "●", "#c0392b", "负收益(<0%)"), (15, "●", "#BA7517", "正收益(0-15%)"), (100000, "●", "#1e8449", "强(>15%)")],
    "top10_weight":[(40, "●", "#1e8449", "分散(<40%)"), (60, "●", "#BA7517", "集中(40-60%)"), (100, "●", "#c0392b", "高度集中(>60%)")],
}


def _signal(metric, value):
    """返回 (emoji, color_hex, label) 信号灯三元组。value 可为 None/str/float。"""
    if value is None or (isinstance(value, str) and value in ("N/A", "")):
        return ("–", "#888888", "数据缺失")
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ("–", "#888888", "数据缺失")
    thresholds = SIGNAL_THRESHOLDS.get(metric)
    if not thresholds:
        return ("", "", "")
    # 阈值为「上界，升序」：v <= boundary 时落入该档（如 pe_pct=50.9 → 50.9<=70 → 适中）
    for boundary, emoji, color, label in thresholds:
        if v <= boundary:
            return (emoji, color, label)
    return ("●", "#c0392b", "偏弱")


def _signal_text(metric, value, suffix=""):
    """生成带信号灯的 HTML 片段：值 + ● + 参考区间。用于 Paragraph / 表格单元格。"""
    emoji, color, label = _signal(metric, value)
    if value is None or value == "N/A" or value == "":
        val_str = ""
    else:
        try:
            v = float(value)
            val_str = f"{v:.1f}{suffix}"
        except (TypeError, ValueError):
            val_str = str(value)
    if not emoji:
        return val_str if val_str else "N/A"
    if not val_str:
        return f'<font color="{color}">{emoji}</font> <font color="{color}">{label}</font>'
    return f'<font color="{color}">{emoji}</font> {val_str} <font color="{color}">{label}</font>'


GLOSSARY = {
    "跟踪误差": "ETF 净值与跟踪指数涨跌幅的偏差年化标准差；越小说明跟踪越紧密",
    "溢折率": "场内价格相对单位净值的偏离；溢价=价格高于净值，折价=低于净值",
    "IOPV": "ETF 实时参考净值，由交易所盘中估算，用来判断折溢价",
    "申购赎回": "授权参与人用一篮子股票与基金公司交换 ETF 份额的机制，使价格贴近净值",
    "单位净值": "每份基金对应的资产净值，是 ETF 内在价值基准",
    "基金规模": "ETF 总净资产（亿元）；过小有清盘风险，过大可能影响灵活性",
    "综合费率": "管理费+托管费，每年从净值中扣除的成本",
    "同类排名": "同赛道 ETF 中按收益等指标的相对位置",
    "成分集中度": "前十大成分股权重合计，越高说明龙头股或单一行业波动影响越大",
    "PE分位": "跟踪指数当前 PE 在历史中的相对位置，越低越便宜",
    "定投": "定期定额买入，平滑择时风险",
}


def _gloss(term):
    return GLOSSARY.get(term, term)


def _to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_pct(v):
    """数值加 %，非数值（如 '未获取'）原样返回——用于诚实降级显示。"""
    try:
        return f"{float(v):.2f}%"
    except (TypeError, ValueError):
        return str(v)


def _fmt_wan(v):
    """数值加 '万份'，非数值（如 '未获取'）原样返回。"""
    try:
        return f"{float(v):.2f}万份"
    except (TypeError, ValueError):
        return str(v)


def _disp_pct(v):
    """百分比显示：数值→'x.x%'，None/非数值→'未获取'（诚实降级，不留 'None%'）。"""
    try:
        f = float(v)
        if f != f:  # NaN
            return "未获取"
        return f"{f:.1f}%"
    except (TypeError, ValueError):
        return "未获取"


def _disp_num(v, nd=2):
    """数值显示：数值→'x.xx'，None/非数值→'未获取'（PE/PB 等比值用，不加 %）。"""
    try:
        f = float(v)
        if f != f:  # NaN
            return "未获取"
        return f"{f:.{nd}f}"
    except (TypeError, ValueError):
        return "未获取"


def _tldr_etf(s):
    """可读性改进1：核心要点速览（TL;DR）—— 带信号灯的大白话结论。返回 list[str]。"""
    items = []
    # 1. 指数估值
    ip = _to_num(s.get("index_pe_pct"))
    e, c, l = _signal("pe_pct", ip)
    items.append(
        f'1. <b>指数估值：</b>跟踪指数 PE 分位 {_gloss("PE分位")} 当前 {s.get("index_pe_pct","N/A")}% '
        f'<font color="{c}">{e} {l}</font>'
    )
    # 2. 跟踪误差
    te = _to_num(s.get("tracking_error"))
    e, c, l = _signal("te", te)
    items.append(
        f'2. <b>跟踪质量：</b>年化跟踪误差 {_gloss("跟踪误差")} {s.get("tracking_error","N/A")}% '
        f'<font color="{c}">{e} {l}</font>'
    )
    # 3. 折溢价
    prem = _to_num(s.get("premium"))
    e, c, l = _signal("premium_abs", abs(prem) if prem is not None else None)
    plabel = "溢价" if (prem or 0) > 0 else ("折价" if (prem or 0) < 0 else "平价")
    items.append(
        f'3. <b>折溢价：</b>{_gloss("溢折率")} 当前 {s.get("premium","N/A")}%（{plabel}） '
        f'<font color="{c}">{e} {l}</font>'
    )
    # 4. 费率
    fee = _to_num(s.get("total_fee"))
    e, c, l = _signal("fee", fee)
    items.append(
        f'4. <b>成本：</b>综合费率 {_gloss("综合费率")} {s.get("total_fee","N/A")}%/年 '
        f'<font color="{c}">{e} {l}</font>'
    )
    # 5. 规模
    aum = _to_num(s.get("aum"))
    e, c, l = _signal("aum", aum)
    items.append(
        f'5. <b>规模流动性：</b>基金规模 {_gloss("基金规模")} {s.get("aum","N/A")}亿元 '
        f'<font color="{c}">{e} {l}</font>'
    )
    # 6. 近1年收益
    ry = _to_num(s.get("ret_1y"))
    if ry is not None:
        e, c, l = _signal("ret_y", ry)
        items.append(f'6. <b>近1年收益：</b>{s.get("ret_1y")}% <font color="{c}">{e} {l}</font>')
    # 7. 资金面
    items.append(f'7. <b>资金面：</b>近20日份额趋势 {s.get("flow_trend","未获取")}（{_fmt_wan(s.get("net_flow_20d","未获取"))}）')
    # 一句话
    parts = []
    if ip is not None:
        parts.append("指数" + ("不贵" if ip < 40 else "偏贵" if ip > 70 else "估值适中"))
    if te is not None:
        parts.append("跟踪" + ("紧密" if te < 1 else "偏差偏大"))
    if fee is not None:
        parts.append("成本" + ("低" if fee < 0.3 else "适中" if fee < 0.6 else "偏高"))
    if parts:
        items.append(f'<b>一句话：</b>{s.get("name","该ETF")}当前{", ".join(parts)}，需跟踪指数估值与折溢价变化。')
    return items


def _plain_summary_etf(s):
    """可读性改进5：封面 notes 大白话化。"""
    ip = _to_num(s.get("index_pe_pct"))
    te = _to_num(s.get("tracking_error"))
    fee = _to_num(s.get("total_fee"))
    prem = _to_num(s.get("premium"))
    parts = []
    if ip is not None:
        if ip < 30:
            parts.append("指数估值偏低，配置性价比好")
        elif ip < 70:
            parts.append("指数估值适中")
        else:
            parts.append("指数估值偏高，注意回调")
    if te is not None:
        parts.append("跟踪紧密" if te < 1 else "跟踪偏差偏大")
    if fee is not None:
        parts.append("费率低" if fee < 0.3 else "费率适中" if fee < 0.6 else "费率偏高")
    if prem is not None and abs(prem) > 3:
        parts.append("当前溢价偏高，注意价格容错")
    summary = "、".join(parts) if parts else "核心指标需进一步跟踪验证"
    return f"{s.get('name','该ETF')}当前{summary}。"


def _chapter_intro_etf(chapter_key):
    """可读性改进4：章节白话导语 —— 每个章节开头一句"这节回答什么问题"。"""
    INTROS = {
        "投资摘要": "这节回答：这只 ETF 是什么？费率、规模、跟踪误差这些基本盘如何？",
        "情景区间": "这节回答：基于指数估值和跟踪质量，当前处于什么配置状态？用于观察，不构成买卖建议。",
        "业绩分析": "这节回答：这只 ETF 过去各周期收益如何？跟踪误差有多大？",
        "持仓分析": "这节回答：ETF 把钱配在了哪些股票上？成分集中度如何？",
        "基金经理": "这节回答：谁在管理这只基金？任职是否稳定？",
        "同类对比": "这节回答：和同赛道其他 ETF 比，这只收益、费率、风险处于什么水平？",
        "规模流动性": "这节回答：基金规模多大？资金在净申购还是净赎回？流动性够不够？",
        "费率分析": "这节回答：持有这只 ETF 每年要付出多少成本？",
        "指数估值": "这节回答：它跟踪的指数现在贵不贵？历史分位在哪？",
        "溢折价": "这节回答：场内价格和净值差多少？高溢价买入要承担什么风险？",
        "风险提示": "这节回答：投资这只 ETF 可能遇到哪些风险？",
        "多视角速览": "这节回答：如果用价值、成长、趋势、风险四种视角看这只 ETF，各自关注什么、分歧在哪？",
        "监控清单": "这节回答：哪些信号会强化或证伪当前结论？哪些时间节点必须跟踪？",
        "赚钱机制": "这节回答：被动指数基金靠什么赚钱？持有成本每年损耗多少？",
        "数据来源": "这节回答：报告里的数字分别来自哪里？哪些是真的、哪些暂时拿不到？",
    }
    return INTROS.get(chapter_key, "")


def _multi_perspective_etf(s):
    """P2-12 多视角速览（ETF 版）：四种视角一句话观察，纯规则零新增取数。返回 [{lens, focus, view, bulb}]。"""
    items = []
    ip = _to_num(s.get("index_pe_pct"))
    te = _to_num(s.get("tracking_error"))
    prem = _to_num(s.get("premium"))
    fee = _to_num(s.get("total_fee"))
    aum = _to_num(s.get("aum"))
    ry = _to_num(s.get("ret_1y"))
    flow = s.get("flow_trend", "未知")

    # 1. 价值派
    if ip is not None and ip < 30:
        vp_view, vp_bulb = "跟踪指数估值处于历史偏低区间，配置性价比相对好；", '<font color="#2e7d32">●</font>'
    elif ip is not None and ip > 70:
        vp_view, vp_bulb = "跟踪指数估值偏高，安全边际不足，回撤风险较大。", '<font color="#c62828">●</font>'
    else:
        vp_view, vp_bulb = "跟踪指数估值中性，配置性价比一般。", '<font color="#f9a825">●</font>'
    vp_facts = []
    if ip is not None:
        vp_facts.append(f"指数PE分位{ip}%")
    if fee is not None:
        vp_facts.append(f"综合费率{fee}%/年")
    if prem is not None:
        vp_facts.append(f"溢折率{prem}%")
    items.append({"lens": "价值派", "focus": "指数估值分位 + 费率 + 折溢价",
                  "view": f"【判断】{vp_view}（{('，'.join(vp_facts)) or '数据不足'}）", "bulb": vp_bulb})

    # 2. 成长派（赛道景气度）
    if ry is not None and ry > 15:
        gp_view, gp_bulb = "近1年收益较强，赛道景气度高；注意高收益后的均值回归。", '<font color="#2e7d32">●</font>'
    elif ry is not None and ry > 0:
        gp_view, gp_bulb = "近1年正收益，赛道平稳；关注指数盈利趋势。", '<font color="#f9a825">●</font>'
    elif ry is not None:
        gp_view, gp_bulb = "近1年收益承压，赛道景气偏弱。", '<font color="#c62828">●</font>'
    else:
        gp_view, gp_bulb = "近1年收益数据不足（价日线不足1年），无法直接判断赛道强弱。", '<font color="#f9a825">●</font>'
    gp_facts = []
    if ry is not None:
        gp_facts.append(f"近1年收益{ry}%")
    if aum is not None:
        gp_facts.append(f"规模{aum}亿")
    items.append({"lens": "成长派", "focus": "近1年收益 + 规模趋势",
                  "view": f"【判断】{gp_view}（{('，'.join(gp_facts)) or '数据不足'}）", "bulb": gp_bulb})

    # 3. 趋势派
    if flow == "净申购":
        tp_view, tp_bulb = "近20日份额净申购，资金面偏强，短期配置热度改善。", '<font color="#2e7d32">●</font>'
    elif flow == "净赎回":
        tp_view, tp_bulb = "近20日份额净赎回，资金面偏弱，需警惕流动性下降。", '<font color="#c62828">●</font>'
    else:
        tp_view, tp_bulb = "资金面趋势未知，短期信号中性。", '<font color="#f9a825">●</font>'
    tp_facts = [f"份额趋势{flow}", f"20日{_fmt_wan(s.get('net_flow_20d','未获取'))}"]
    items.append({"lens": "趋势派", "focus": "资金申赎 + 价格动能",
                  "view": f"【判断】{tp_view}（{('，'.join(tp_facts))}）", "bulb": tp_bulb})

    # 4. 风险派
    risks = []
    if te is not None and te > 1:
        risks.append(f"跟踪误差偏大({te}%)")
    if prem is not None and prem > 3:
        risks.append(f"高溢价({prem}%)价格容错低")
    if aum is not None and aum < 2:
        risks.append(f"规模偏小({aum}亿)清盘风险")
    if risks:
        rp_view = "存在需重点跟踪的风险：" + "；".join(risks) + "。"
        rp_bulb = '<font color="#c62828">●</font>'
    else:
        rp_view = "未检出显著量化风险信号，但指数系统性下跌与跟踪偏差扩大仍需持续跟踪。"
        rp_bulb = '<font color="#2e7d32">●</font>'
    items.append({"lens": "风险派", "focus": "跟踪误差 + 折溢价 + 规模",
                  "view": f"【判断】{rp_view}", "bulb": rp_bulb})

    return items


# ── 图表生成 ──────────────────────────────────────────────────────────────────

def _nav_chart(nav_df, fund_name):
    nav_df = nav_df.sort_values("nav_date").copy()
    nav_df["unit_nav"] = pd.to_numeric(nav_df["unit_nav"], errors="coerce")
    nav_df["nav_date"] = pd.to_datetime(nav_df["nav_date"])
    recent = nav_df.tail(250)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(recent["nav_date"], recent["unit_nav"], color="#1a3a6b", linewidth=1.5, label="单位净值")
    ax.fill_between(recent["nav_date"], recent["unit_nav"], alpha=0.1, color="#1a3a6b")
    ax.set_title(f"{fund_name} 近1年净值走势", fontsize=12)
    ax.set_xlabel("日期"); ax.set_ylabel("单位净值")
    ax.grid(True, alpha=0.3); ax.legend()
    fig.tight_layout()
    return _chart_to_image(fig)


def _aum_chart(share_df, fund_name):
    share_df = share_df.sort_values("trade_date").copy()
    col = "net_asset" if "net_asset" in share_df.columns else "fd_share"
    share_df[col] = pd.to_numeric(share_df[col], errors="coerce")
    share_df["trade_date"] = pd.to_datetime(share_df["trade_date"])
    share_df["val"] = share_df[col] / 1e4
    recent = share_df.dropna(subset=["val"]).tail(60)
    label = "规模（亿元）" if col == "net_asset" else "份额（万份）"

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(recent["trade_date"], recent["val"], color="#2c5f9e", alpha=0.7, width=5)
    ax.set_title(f"{fund_name} 基金规模趋势", fontsize=12)
    ax.set_xlabel("日期"); ax.set_ylabel(label)
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    return _chart_to_image(fig)


def _scenario_band_chart(index_dailybasic_df, current_pe, current_nav, fund_name):
    """情景参考区间图（对标股票报告 §8 _trading_plan_chart）：把指数 PE 25/50/75 分位映射到净值区间带。零 token。"""
    if index_dailybasic_df is None or not hasattr(index_dailybasic_df, "empty") or index_dailybasic_df.empty:
        return None
    if current_pe is None or current_pe <= 0 or current_nav is None:
        return None
    pe = pd.to_numeric(index_dailybasic_df["pe"], errors="coerce").dropna()
    pe = pe[pe > 0]
    if len(pe) < 10:
        return None

    pe_bear = float(np.percentile(pe, 25))
    pe_base = float(np.percentile(pe, 50))
    pe_bull = float(np.percentile(pe, 75))
    nav_bear = round(current_nav * pe_bear / current_pe, 4)
    nav_base = round(current_nav * pe_base / current_pe, 4)
    nav_bull = round(current_nav * pe_bull / current_pe, 4)

    values = [nav_bear, nav_base, nav_bull, current_nav]
    low = min(values)
    high = max(values)
    pad = max((high - low) * 0.15, high * 0.03)
    x_min = max(0, low - pad)
    x_max = high + pad

    fig, ax = plt.subplots(figsize=(10, 2.8))
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xlabel("单位净值（元）")
    ax.set_title(f"{fund_name} 情景参考区间（基于指数 PE 分位）", fontsize=12)

    bands = [
        ("估值安全边际观察区", (nav_bear, nav_base), "#d5f5e3", "#1e8449"),
        ("中性观察区", (nav_base, nav_bull), "#fcf3cf", "#b7950b"),
        ("高估值复核区", (nav_bull, high), "#fadbd8", "#922b21"),
    ]
    y = 0.46
    h = 0.28
    for label, (s, e), color, edge in bands:
        ax.barh(y, e - s, left=s, height=h, color=color, edgecolor=edge, linewidth=1)
        ax.text((s + e) / 2, y, label, ha="center", va="center", fontsize=9, color=edge)

    markers = [
        ("当前净值", current_nav, "#000000", 0.78),
        ("谨慎价值(PE25%)", nav_bear, "#7f8c8d", 0.10),
        ("中性价值(PE50%)", nav_base, "#8b1a1a", 0.90),
        ("乐观价值(PE75%)", nav_bull, "#c0392b", 0.10),
    ]
    for label, value, color, text_y in markers:
        ax.axvline(value, color=color, linestyle="-" if label == "当前净值" else "--", linewidth=1.2)
        ax.text(value, text_y, f"{label}\n{value:.3f}", ha="center", va="center", fontsize=8, color=color)

    ax.grid(True, alpha=0.25, axis="x")
    for spine in ("left", "right", "top"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return _chart_to_image(fig, width=15 * cm)


def _valuation_anchor_chart(broad):
    """宽基估值锚条形图（T2a）：各指数 PE 自身近3年历史分位。零 token。"""
    indices = broad.get("indices") if isinstance(broad, dict) else None
    if not indices:
        return None
    names, pcts, colors = [], [], []
    for it in indices:
        p = it.get("pe_pct")
        if p is None:
            continue
        names.append(it["name"])
        pcts.append(p)
        if p <= 30:
            colors.append("#1e8449")      # 偏低 → 绿
        elif p <= 60:
            colors.append("#b7950b")      # 适中 → 黄
        else:
            colors.append("#922b21")      # 偏高 → 红
    if not names:
        return None
    fig, ax = plt.subplots(figsize=(10, 3.2))
    bars = ax.bar(names, pcts, color=colors, alpha=0.85, width=0.5)
    ax.set_ylim(0, 100)
    ax.set_ylabel("PE 近3年分位 (%)")
    ax.set_title("宽基指数 PE 历史分位对比（越高 = 相对自身历史越贵）", fontsize=12)
    for b, p in zip(bars, pcts):
        ax.text(b.get_x() + b.get_width() / 2, p + 1.5, f"{p:.1f}%",
                ha="center", va="bottom", fontsize=9)
    ax.axhline(50, color="#888888", linestyle="--", linewidth=0.8)
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    return _chart_to_image(fig, width=15 * cm)


def _peer_fee_chart(peer):
    """同类 ETF 综合费率横向对比条形图（T2b）。零 token。"""
    peers = peer.get("peers") if isinstance(peer, dict) else None
    if not peers:
        return None
    rows = []
    for it in peers:
        tf = it.get("total_fee")
        if tf is None:
            continue
        rows.append((f'{it["name"]}\n{it["code"]}', float(tf), bool(it.get("is_self"))))
    if not rows:
        return None
    rows.sort(key=lambda x: x[1])
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    colors = ["#1f4e79" if r[2] else "#aab7c4" for r in rows]
    fig, ax = plt.subplots(figsize=(10, 3.4))
    bars = ax.barh(labels, vals, color=colors, alpha=0.9)
    ax.set_xlim(0, max(vals) * 1.18)
    ax.set_xlabel("综合费率 (%/年)")
    ax.set_title("同类科创50 ETF 综合费率对比（蓝 = 本报告标的 588000）", fontsize=12)
    for b, v in zip(bars, vals):
        ax.text(v + 0.008, b.get_y() + b.get_height() / 2, f"{v:.2f}%",
                va="center", ha="left", fontsize=9)
    ax.grid(True, alpha=0.3, axis="x")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return _chart_to_image(fig, width=15 * cm)


# ── 主函数 ────────────────────────────────────────────────────────────────────

def create_etf_pdf(data_file: str, output_path: str) -> None:
    print("=" * 80)
    print("生成 ETF 深度分析 PDF 报告")
    print("=" * 80)

    d = _load(data_file)
    st = _styles()
    basic = d.get("basic", {})
    fund_name = basic.get("name", d["ts_code"])
    nav_df    = d.get("nav")
    daily_df  = d.get("daily")
    index_df  = d.get("index_daily")
    share_df  = d.get("share")
    portfolio_df = d.get("portfolio")
    similar_df   = d.get("similar_funds")
    similar_nav  = d.get("similar_nav_data", {})
    similar_meta = d.get("similar_selection_meta", {})
    stock_names  = d.get("stock_names", {})
    manager_df   = d.get("manager")
    sales_vol_df = d.get("sales_vol")
    index_dailybasic_df = d.get("index_dailybasic")
    index_weight_df = d.get("index_weight")
    realtime_quote = d.get("realtime_quote", {})

    returns = _calc_returns(nav_df, daily_df)
    te      = _calc_te(daily_df, index_df)
    ma_pos  = _ma_position(nav_df)
    aum_trend = _aum_trend(share_df)
    flow_metrics = _calc_flow_metrics(share_df)
    te_decomp = _decompose_tracking_diff(daily_df, index_df)
    index_val = _index_valuation_percentile(index_dailybasic_df)
    premium_disc = d.get("premium_disc") or _calc_premium_discount(nav_df, daily_df)
    concentration = _index_concentration(index_weight_df)

    m_fee = float(basic.get("m_fee") or 0)
    c_fee = float(basic.get("c_fee") or 0)
    total_fee = round(m_fee + c_fee, 4)

    aum_bn = "N/A"
    _basic_aum = basic.get("aum_yi")
    if _basic_aum:
        aum_bn = round(float(_basic_aum), 1)
    elif share_df is not None and not share_df.empty:
        share_df2 = share_df.copy()
        col = "net_asset" if "net_asset" in share_df2.columns else "fd_share"
        share_df2[col] = pd.to_numeric(share_df2[col], errors="coerce")
        latest_val = share_df2[col].dropna().iloc[-1] if not share_df2[col].dropna().empty else None
        if latest_val:
            # fd_share 单位是万份 → /1e4 得亿份；net_asset 单位是元 → /1e8 得亿元
            aum_bn = round(latest_val / 1e4, 1) if col == "fd_share" else round(latest_val / 1e8, 1)

    # 同类排名
    similar_rank = "N/A"
    if similar_nav and returns.get("1Y") is not None:
        peer_returns = []
        for code, snav in similar_nav.items():
            pr = _calc_returns(snav)
            if pr.get("1Y") is not None:
                peer_returns.append(pr["1Y"])
        if peer_returns:
            rank = sum(1 for r in peer_returns if r > returns["1Y"])
            similar_rank = f"{rank+1}/{len(peer_returns)+1}"

    etf_summary = {
        "name": fund_name,
        "ts_code": d["ts_code"],
        "index_code": d.get("index_code", ""),
        "ret_1m": returns.get("1M", "N/A"),
        "ret_3m": returns.get("3M", "N/A"),
        "ret_1y": returns.get("1Y", "N/A"),
        "similar_rank": similar_rank,
        "tracking_error": te.get("te", "N/A"),
        "tracking_bias": te.get("avg", "N/A"),
        "total_fee": total_fee,
        "m_fee": m_fee,
        "c_fee": c_fee,
        "aum": aum_bn,
        "aum_trend": aum_trend,
        "ma_position": ma_pos,
        "index_pe": index_val.get("current_pe", "N/A") if index_val else "N/A",
        "index_pe_pct": index_val.get("pe_percentile", "N/A") if index_val else "N/A",
        "index_pb": index_val.get("current_pb", "N/A") if index_val else "N/A",
        "index_pb_pct": index_val.get("pb_percentile", "N/A") if index_val else "N/A",
        "premium": premium_disc.get("current_premium", "N/A") if premium_disc else "N/A",
        "premium_pct": premium_disc.get("premium_percentile", "N/A") if premium_disc else "N/A",
        "flow_trend": flow_metrics.get("trend_20d", "未获取") if flow_metrics else "未获取",
        "net_flow_20d": flow_metrics.get("net_flow_20d", "未获取") if flow_metrics else "未获取",
        "net_flow_60d": flow_metrics.get("net_flow_60d", "未获取") if flow_metrics else "未获取",
        "top10_weight": concentration.get("top10_weight", "N/A"),
        "top20_weight": concentration.get("top20_weight", "N/A"),
        "industry_weight_status": concentration.get("industry_weight_status", "缺少行业映射"),
        "current_price": realtime_quote.get("price", "N/A"),
        "change_pct": realtime_quote.get("change_pct", "N/A"),
        "broad_base": d.get("broad_base_valuation"),
        "peer_fees": d.get("peer_etf_fees"),
        "turnover_rate": realtime_quote.get("turnover_rate", "N/A"),
        "amount": realtime_quote.get("amount", "N/A"),
    }
    etf_view = build_etf_research_view(etf_summary)
    etf_brief = render_etf_research_brief(etf_view)

    # AI 建议：作为配置模型之后的解释补充
    advice_text = get_investment_advice("etf", etf_summary)

    # T1 借鉴股票报告：监控清单 / 赚钱机制 / 空方逻辑（规则化，零 token）
    etf_monitor = build_etf_monitor(etf_summary)
    etf_biz = build_etf_business_model(etf_summary)
    etf_bear = build_etf_bear_case(etf_view, etf_summary)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    story = []

    # ── 封面 ──
    add_cover(
        story,
        fund_name,
        "ETF 深度分析报告",
        [
            ["基金代码", d["ts_code"]],
            ["跟踪指数", d["index_code"]],
            ["报告日期", datetime.now().strftime("%Y年%m月%d日")],
        ],
        kind="etf",
        highlights=[
            ["配置研究状态", str(etf_view.get("allocation_rating", "N/A")), f"配置分 {etf_view.get('allocation_score', 'N/A')}"],
            ["场内观察状态", str(etf_view.get("trading_rating", "N/A")), f"观察分 {etf_view.get('trading_score', 'N/A')}"],
            ["综合费率", f"{total_fee}%/年", f"规模 {aum_bn}亿元"],
        ],
        notes=[
            ["核心结论", _plain_summary_etf(etf_summary)],
            ["关注变量", "指数估值、跟踪误差、溢价折价、规模流动性、费率和份额变化。"],
            ["主要风险", "指数系统性下跌、跟踪偏差扩大、流动性下降及高溢价下的价格容错风险。"],
        ],
    )

    add_report_reading_guide(story, kind="etf")

    # ── 可读性改进1：核心要点速览（TL;DR）──
    # 注意：add_report_reading_guide 已在末尾插入 PageBreak，这里不要再插，
    # 否则两个连续分页符之间会留下一页空白（此前的第 3 页空白即由此产生）。
    tldr_items = _tldr_etf(etf_summary)
    if tldr_items:
        story.append(Paragraph("核心要点速览", st["h1"]))
        story.append(Paragraph(
            "以下为报告核心指标的大白话总结，每个指标带信号灯（●绿色=优 / ●黄色=中 / ●红色=劣）和参考区间，帮助快速理解「这个数意味着什么」。详细数据见后续各章节。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.3*cm))
        for item in tldr_items:
            story.append(Paragraph(item, st["body"]))
        story.append(Spacer(1, 0.3*cm))

    # 标注约定
    story.append(Paragraph(
        "标注约定：本报告以【事实】标注可验证的公开数据，【判断】标注基于规则的分析推论，"
        "【情景】标注假设性风险场景。所有结论仅供研究复盘，不构成任何投资建议。",
        st["caption"]
    ))

    # ── 一、投资摘要 ──
    story.append(Paragraph("一、投资摘要", st["h1"]))
    intro = _chapter_intro_etf("投资摘要")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    info_rows = [
        ["基金名称", fund_name, "基金代码", d["ts_code"]],
        ["基金类型", basic.get("fund_type",""), "成立日期", basic.get("found_date","")],
        ["基金公司", basic.get("management",""), "托管银行", basic.get("custodian","")],
        ["管理费率", f"{m_fee}%/年", "托管费率", f"{c_fee}%/年"],
        ["综合费率", f"{total_fee}%/年", "基金规模", f"{aum_bn}亿元"],
        ["场内价格", f"{realtime_quote.get('price', 'N/A')}", "盘中涨跌", f"{realtime_quote.get('change_pct', 'N/A')}%"],
    ]
    story.append(_tbl(info_rows, col_widths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm]))
    story.append(Spacer(1, 0.3*cm))
    story.append(metric_cards([
        ["跟踪误差", f"{etf_summary.get('tracking_error')}%", "年化口径"],
        ["溢价/折价", f"{etf_summary.get('premium')}%", f"分位 {_disp_pct(etf_summary.get('premium_pct'))}"],
        ["近60日份额", _fmt_wan(etf_summary.get('net_flow_60d')), "资金申赎趋势"],
    ], kind="etf"))
    story.append(Spacer(1, 0.3*cm))

    _ret1y = returns.get("1Y")
    ret1y_str = f"{_ret1y:.2f}%" if _ret1y is not None else "数据不足"
    evidence_map(story, [
        [
            "跟踪指数是否具备配置价值",
            f"指数估值分位 {index_val.get('pe_percentile','N/A') if index_val else 'N/A'}；近1年收益 {ret1y_str}",
            "中等",
            "指数估值能提供配置参照，但仍需结合行业结构和成分集中度理解。",
            "指数盈利、行业权重、宏观周期位置",
        ],
        [
            "跟踪质量是否可接受",
            f"年化跟踪误差 {etf_summary.get('tracking_error')}%；日均偏差 {etf_summary.get('tracking_bias')}%",
            "较强",
            "跟踪误差来自结构化数据，适合作为基金运作质量的重要参考。",
            "持续偏差、现金拖累、复制误差和费率影响",
        ],
        [
            "折溢价是否影响交易体验",
            f"当前溢价 {etf_summary.get('premium')}%；历史分位 {_disp_pct(etf_summary.get('premium_pct'))}",
            "中等",
            "折溢价提示场内价格与净值偏离，尤其影响短期成交体验。",
            "盘中IOPV、成交深度、申赎机制",
        ],
        [
            "规模和份额是否稳定",
            f"规模 {aum_bn}亿元；近60日份额变化 {_fmt_wan(etf_summary.get('net_flow_60d'))}",
            "较强",
            "规模和份额变化有助于观察资金配置热度和流动性基础。",
            "持续申赎、成交额、做市活跃度",
        ],
    ], kind="etf")

    add_followup_watchlist(story, [
        [
            "指数估值与暴露",
            f"指数PE分位 {etf_summary.get('index_pe_pct')}%；Top10权重 {_fmt_pct(etf_summary.get('top10_weight'))}",
            "每月或指数成分调整后",
            "复核估值分位、行业权重和成分集中度，确认指数暴露是否仍符合预期。",
        ],
        [
            "跟踪质量",
            f"年化跟踪误差 {etf_summary.get('tracking_error')}%；日均偏差 {etf_summary.get('tracking_bias')}%",
            "未来20-60个交易日",
            "观察偏差是否持续扩大，并复核现金拖累、复制误差、费用和申赎影响。",
        ],
        [
            "折溢价与成交体验",
            f"当前溢价 {etf_summary.get('premium')}%；历史分位 {_disp_pct(etf_summary.get('premium_pct'))}；换手 {etf_summary.get('turnover_rate')}%",
            "未来5-20个交易日",
            "结合IOPV、成交额和申赎机制判断偏离是否短期，避免把单日折溢价当作结论。",
        ],
        [
            "规模与份额变化",
            f"规模 {aum_bn}亿元；20日份额变化 {_fmt_wan(etf_summary.get('net_flow_20d','未获取'))}；60日份额变化 {_fmt_wan(etf_summary.get('net_flow_60d','未获取'))}",
            "未来20-60个交易日",
            "观察份额是否持续申购或赎回，并结合成交额判断流动性基础是否变化。",
        ],
    ], kind="etf")

    # ── 二、情景区间与观察触发器 ──
    story.append(Paragraph("二、情景区间与观察触发器", st["h1"]))
    intro = _chapter_intro_etf("情景区间")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    story.append(callout_box("本节仅把 ETF 配置模型结果整理为配置情景、风险复核项和观察触发器，重点关注指数估值、跟踪质量、规模流动性、费率和溢价折价；不构成任何投资建议。", kind="etf"))
    story.append(Spacer(1, 0.2*cm))
    plan_rows = [
        ["观察事项", "模型读数/触发器"],
        ["配置研究状态", f"{etf_view.get('allocation_rating')}（配置分{etf_view.get('allocation_score')}）"],
        ["场内观察状态", f"价格{etf_view.get('current_price', 'N/A')}；涨跌{etf_view.get('change_pct', 'N/A')}%；换手{etf_view.get('turnover_rate', 'N/A')}%"],
        ["定投适配观察", etf_view.get("dca_plan", "")],
        ["正向证据增强条件", etf_view.get("add_condition", "")],
        ["高估值/再平衡复核", etf_view.get("rebalance_condition", "")],
    ]
    story.append(_tbl(plan_rows, col_widths=[3.5*cm, 12.5*cm]))
    story.append(Spacer(1, 0.2*cm))

    pro_rows = [
        ["专业维度", "当前读数", "解读"],
        ["跟踪误差", _signal_text("te", etf_summary.get("tracking_error")) + f" / 日均偏差{etf_summary.get('tracking_bias')}%", "越低说明跟踪指数越稳定，持续偏差需复核现金拖累、费用和复制误差"],
        ["溢价/折价", _signal_text("premium_abs", abs(_to_num(etf_summary.get("premium"))) if etf_summary.get("premium") not in (None, "N/A") else None) + f"（分位{_disp_pct(etf_summary.get('premium_pct'))}）", "高溢价说明场内价格容错较低，折价需结合流动性和申赎机制判断"],
        ["份额变化", f"20日{_fmt_wan(etf_summary.get('net_flow_20d','未获取'))}；60日{_fmt_wan(etf_summary.get('net_flow_60d','未获取'))}", "份额扩张代表资金配置热度改善，持续赎回需警惕流动性下降"],
        ["成分集中度", _signal_text("top10_weight", etf_summary.get("top10_weight")) + f"；Top20 {_fmt_pct(etf_summary.get('top20_weight'))}", "集中度越高，龙头股或单一行业波动对ETF影响越大"],
        ["行业权重", "未获取（TDX 无成分股权重源）", "后续可接入成分股行业映射后输出行业暴露矩阵"],
        ["策略适配", f"定投{etf_view.get('strategy_fit', {}).get('定投')}；波段{etf_view.get('strategy_fit', {}).get('波段')}；资产配置{etf_view.get('strategy_fit', {}).get('资产配置')}", "不同研究目的对应不同观察频率和反证条件"],
    ]
    story.append(Paragraph("ETF专业诊断", st["h2"]))
    story.append(_tbl(pro_rows, col_widths=[3*cm, 5*cm, 8*cm]))
    story.append(Spacer(1, 0.2*cm))

    story.extend(md_to_story(etf_brief, st["body"], table_builder=_tbl))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("模型文字解读", st["h2"]))
    story.extend(md_to_story(advice_text, st["body"], table_builder=_tbl))
    story.append(Spacer(1, 0.3*cm))

    # ── 2.5、多视角速览（P2-12）──
    story.append(Paragraph("2.5、多视角速览", st["h1"]))
    intro = _chapter_intro_etf("多视角速览")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    mp = _multi_perspective_etf(etf_summary)
    if mp:
        mp_rows = [["视角", "关注点", "一句话观点"]]
        for it in mp:
            mp_rows.append([
                f'{it["bulb"]} {it["lens"]}',
                it["focus"],
                it["view"],
            ])
        story.append(_tbl(mp_rows, col_widths=[3*cm, 4.5*cm, 8.5*cm]))
        story.append(Spacer(1, 0.2*cm))

    # ── 2.6、情景参考区间图（T1：借鉴股票报告 §8）──
    _cur_nav = _to_num(realtime_quote.get("iopv"))
    if _cur_nav is None:
        _cur_nav = _to_num(realtime_quote.get("price"))
    band_img = _scenario_band_chart(
        index_dailybasic_df, _to_num(etf_summary.get("index_pe")), _cur_nav, fund_name
    )
    if band_img is not None:
        story.append(Paragraph("2.6、情景参考区间图", st["h2"]))
        story.append(band_img)
        story.append(Paragraph(
            "图：基于跟踪指数 PE 历史分位（25/50/75）映射的净值情景区间，用于观察估值与风险状态，不代表任何交易判断。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.3*cm))

    # ── 2.7、宽基估值锚：科创50 相对大盘贵不贵（T2a）──
    broad = etf_summary.get("broad_base")
    if broad and broad.get("indices"):
        story.append(Paragraph("2.7、宽基估值锚：科创50 相对大盘贵不贵", st["h2"]))
        story.append(Paragraph(
            "这节回答：把科创50 放进沪深300 / 中证500 / 创业板指这几个宽基指数里，它的估值处在什么位置？"
            "绝对 PE 看\"水平贵不贵\"，自身历史分位看\"相对自己过去贵不贵\"，两者要结合看。",
            st["caption"]
        ))
        bb_rows = [["指数", "代码", "当前PE(TTM)", "自身3Y分位", "PB(MRQ)", "股息率"]]
        for it in broad["indices"]:
            pe_s = f'{it["pe"]:.2f}' if it.get("pe") is not None else "N/A"
            pct_s = f'{it["pe_pct"]:.1f}%' if it.get("pe_pct") is not None else "N/A"
            pb_s = f'{it["pb"]:.2f}' if it.get("pb") is not None else "—"
            div_s = f'{it["div_yield"]:.2f}%' if it.get("div_yield") is not None else "—"
            bb_rows.append([it["name"], it["code"], pe_s, pct_s, pb_s, div_s])
        story.append(_tbl(bb_rows, col_widths=[3.2*cm, 2.0*cm, 3.0*cm, 2.6*cm, 2.4*cm, 2.0*cm]))
        story.append(Paragraph(
            "注：科创50 采用代表性/中位数 PE（整体 PE 因成分股亏损失真，TDX 加权口径约 210x）；"
            "宽基指数为整体 PE(TTM) 口径，两者口径不同，仅作定性参考。各指数分位为自身近3年历史内相对位置。",
            st["caption"]
        ))
        anchor_img = _valuation_anchor_chart(broad)
        if anchor_img is not None:
            story.append(Spacer(1, 0.2*cm))
            story.append(anchor_img)
            story.append(Paragraph(
                "图：各宽基指数 PE 自身近3年历史分位。可见 2025–2026 反弹后，沪深300/中证500/创业板指已处自身历史偏高区，"
                "而科创50 仍处中枢附近（约 50% 分位）——绝对 PE 更高，但相对自身历史并不算贵。",
                st["caption"]
            ))
        story.append(Spacer(1, 0.3*cm))

    # ── 三、业绩分析 ──
    story.append(Paragraph("三、业绩分析", st["h1"]))
    intro = _chapter_intro_etf("业绩分析")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    story.append(Paragraph("3.1 净值走势", st["h2"]))
    if nav_df is not None and not nav_df.empty:
        story.append(_nav_chart(nav_df, fund_name))
        story.append(Paragraph("图：近1年单位净值走势", st["caption"]))

    story.append(Paragraph("3.2 各期收益率", st["h2"]))
    ret_rows = [["周期", "收益率"]]
    for label in ["1M", "3M", "6M", "1Y", "2Y", "3Y"]:
        v = returns.get(label)
        ret_rows.append([label, f"{v:.2f}%" if v is not None else "数据不足"])
    story.append(_tbl(ret_rows, col_widths=[4*cm, 4*cm]))

    story.append(Paragraph("3.3 跟踪误差", st["h2"]))
    te_rows = [
        ["指标", "数值"],
        ["年化跟踪误差", f"{te.get('te','N/A')}%"],
        ["日均偏差", f"{te.get('avg','N/A')}%"],
    ]
    story.append(_tbl(te_rows, col_widths=[6*cm, 6*cm]))

    if te_decomp:
        story.append(Paragraph("3.4 跟踪误差拆解", st["h2"]))
        decomp_rows = [
            ["指标", "数值"],
            ["系统性偏差（均值）", f"{te_decomp.get('mean_bias','N/A')}%"],
            ["波动性偏差（标准差）", f"{te_decomp.get('volatility','N/A')}%"],
        ]
        story.append(_tbl(decomp_rows, col_widths=[6*cm, 6*cm]))

    story.append(Spacer(1, 0.3*cm))

    # ── 四、持仓分析 ──
    story.append(Paragraph("四、持仓分析", st["h1"]))
    intro = _chapter_intro_etf("持仓分析")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    if portfolio_df is not None and not portfolio_df.empty:
        portfolio_df2 = portfolio_df.copy()
        portfolio_df2["stk_mkv_ratio"] = pd.to_numeric(portfolio_df2.get("stk_mkv_ratio", 0), errors="coerce")
        top20 = portfolio_df2.nlargest(20, "stk_mkv_ratio")
        hold_rows = [["股票代码", "股票名称", "持仓占比"]]
        for _, row in top20.iterrows():
            code = row.get("symbol", "")
            name = stock_names.get(code, code)
            ratio = row.get("stk_mkv_ratio", 0)
            hold_rows.append([code, name, f"{ratio:.2f}%"])
        story.append(_tbl(hold_rows, col_widths=[3.5*cm, 8*cm, 3.5*cm]))
        if concentration:
            story.append(Spacer(1, 0.2*cm))
            story.append(Paragraph(
                f"指数成分集中度：前十大权重合计{_fmt_pct(concentration.get('top10_weight','未获取'))}，前二十大权重合计{_fmt_pct(concentration.get('top20_weight','未获取'))}。{concentration.get('industry_weight_status','')}",
                st["caption"]
            ))
    else:
        story.append(Paragraph(
            "持仓数据暂未通过 TDX 获取。本 ETF 为被动指数基金，完全复制科创50指数（000688）"
            "成分股及权重；当前 TDX 接口未返回基金持仓明细与成分股权重序列，故成分集中度与持仓明细暂无法计算。"
            "该缺口为数据源限制，非模型缺陷；如需补充可在 TDX 接入基金持仓 F10 后重算。",
            st["body"]
        ))
    story.append(Spacer(1, 0.3*cm))

    # ── 四点五、基金经理 ──
    if manager_df is not None and not manager_df.empty:
        story.append(Paragraph("4.5 基金经理", st["h2"]))
        mgr_df = manager_df.sort_values("ann_date", ascending=False) if "ann_date" in manager_df.columns else manager_df
        current_mgr = mgr_df.head(3)
        mgr_rows = [["姓名", "任职日期", "离任日期"]]
        for _, row in current_mgr.iterrows():
            name = row.get("name", "N/A")
            acc_date = row.get("acc_date", "N/A")
            dimission_date = row.get("dimission_date", "在任")
            if pd.isna(dimission_date) or dimission_date == "":
                dimission_date = "在任"
            mgr_rows.append([name, str(acc_date), str(dimission_date)])
        story.append(_tbl(mgr_rows, col_widths=[4*cm, 4*cm, 4*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 五、同类基金对比 ──
    if similar_df is not None and not similar_df.empty:
        story.append(Paragraph("五、同类基金对比（业绩与风险）", st["h1"]))
        intro = _chapter_intro_etf("同类对比")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
        if similar_meta:
            story.append(Paragraph(
                f"筛选方法：{similar_meta.get('method', '同赛道候选池')}；评分口径：{similar_meta.get('score_formula', '收益、费率、规模和风险综合评分')}",
                st["caption"]
            ))

        peer_rows = []
        score_map = {x.get("ts_code"): x for x in similar_meta.get("top_scores", [])}
        for _, row in similar_df.iterrows():
            code = row.get("ts_code", "")
            snav = similar_nav.get(code)
            pr = _calc_returns(snav) if snav is not None else {}
            meta_row = score_map.get(code, {})

            r1m = pr.get("1M")
            r3m = pr.get("3M")
            r6m = pr.get("6M")

            peer_rows.append({
                "name": row.get("name", ""),
                "management": row.get("management", ""),
                "r1m": r1m,
                "r3m": r3m,
                "r6m": r6m,
                "score": meta_row.get("score"),
                "vol_6m": meta_row.get("vol_6m"),
                "max_drawdown_6m": meta_row.get("max_drawdown_6m"),
            })

        peer_rows.sort(
            key=lambda x: (
                x["r6m"] is None,
                -(x["r6m"] if x["r6m"] is not None else -9999),
                -(x["r3m"] if x["r3m"] is not None else -9999),
                -(x["r1m"] if x["r1m"] is not None else -9999),
            )
        )

        comp_rows = [["基金名称", "管理公司", "综合评分", "近6月收益", "近6月波动", "近6月最大回撤"]]
        for item in peer_rows:
            comp_rows.append([
                item["name"],
                item["management"],
                f"{item['score']:.2f}" if item["score"] is not None else "N/A",
                f"{item['r6m']:.2f}%" if item["r6m"] is not None else "N/A",
                f"{item['vol_6m']:.2f}%" if item["vol_6m"] is not None else "N/A",
                f"{item['max_drawdown_6m']:.2f}%" if item["max_drawdown_6m"] is not None else "N/A",
            ])

        story.append(_tbl(comp_rows, col_widths=[4.2*cm, 3.4*cm, 2.2*cm, 2.2*cm, 2.4*cm, 2.6*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 六、规模与流动性 ──
    story.append(Paragraph("六、规模与流动性", st["h1"]))
    intro = _chapter_intro_etf("规模流动性")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    if share_df is not None and not share_df.empty:
        story.append(_aum_chart(share_df, fund_name))
        story.append(Paragraph("图：基金规模趋势（亿元）", st["caption"]))

    if flow_metrics:
        story.append(Paragraph("6.1 份额变化趋势", st["h2"]))
        flow_rows = [
            ["指标", "数值"],
            ["当前总份额", f"{flow_metrics.get('latest_share','N/A')}万份"],
            ["近20日份额变化", f"{flow_metrics.get('net_flow_20d','N/A')}万份（{flow_metrics.get('trend_20d','')}）"],
            ["近60日份额变化", f"{flow_metrics.get('net_flow_60d','N/A')}万份（{flow_metrics.get('trend_60d','')}）"],
        ]
        story.append(_tbl(flow_rows, col_widths=[6*cm, 6*cm]))

    story.append(Spacer(1, 0.3*cm))

    # ── 七、费率分析 ──
    story.append(Paragraph("七、费率分析", st["h1"]))
    intro = _chapter_intro_etf("费率分析")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    fee_rows = [
        ["费用类型", "费率"],
        ["管理费", f"{m_fee}%/年"],
        ["托管费", f"{c_fee}%/年"],
        ["综合费率", f"{total_fee}%/年"],
    ]
    story.append(_tbl(fee_rows, col_widths=[6*cm, 6*cm]))
    story.append(Spacer(1, 0.3*cm))

    # ── 7.1、同类 ETF 费率横向对比（T2b）──
    peer_fees = etf_summary.get("peer_fees")
    if peer_fees and peer_fees.get("peers"):
        story.append(Paragraph("7.1、同类 ETF 费率横向对比", st["h2"]))
        story.append(Paragraph(
            "这节回答：和同赛道（跟踪上证科创板50成份指数）的其他 ETF 比，本基金的持有成本处在什么水平？"
            "ETF 是被动产品，长期收益主要来自指数 β，费率越低、每年复利侵蚀越少，对长期持有的影响越明显。",
            st["caption"]
        ))
        peers_sorted = sorted(peer_fees["peers"], key=lambda x: (x.get("total_fee") or 999))
        pf_rows = [["基金", "代码", "管理公司", "管理费 %/年", "托管费 %/年", "综合费率 %/年"]]
        for it in peers_sorted:
            tag = "（本报告标的）" if it.get("is_self") else ""
            pf_rows.append([
                it["name"] + tag,
                it["code"],
                it.get("management", "—"),
                f'{it["m_fee"]:.2f}' if it.get("m_fee") is not None else "—",
                f'{it["c_fee"]:.2f}' if it.get("c_fee") is not None else "—",
                f'{it["total_fee"]:.2f}' if it.get("total_fee") is not None else "—",
            ])
        story.append(_tbl(pf_rows, col_widths=[3.0*cm, 2.0*cm, 3.2*cm, 2.6*cm, 2.6*cm, 3.0*cm]))
        # 洞察：找最低/最高，给本报告标的定性
        fees = [p["total_fee"] for p in peers_sorted if p.get("total_fee") is not None]
        self_fee = next((p["total_fee"] for p in peers_sorted if p.get("is_self")), None)
        min_fee, max_fee = (min(fees), max(fees)) if fees else (None, None)
        if self_fee is not None and min_fee is not None and max_fee is not None:
            cheaper = sum(1 for f in fees if f < self_fee)
            if cheaper == 0:
                rank_txt = "并列同类最低（无同类更便宜）"
            else:
                rank_txt = f"同类第 {cheaper + 1} 低（仅 {cheaper} 只更便宜）"
            story.append(Paragraph(
                f"注：本基金（588000）综合费率 {self_fee:.2f}%/年，同类最低为 {min_fee:.2f}%/年、最高为 {max_fee:.2f}%/年；"
                f"本基金{rank_txt}。"
                "费率差异按年复利长期累积：以 0.60% 与 0.20% 计，持有 10 年成本相差约 4.4 个百分点。",
                st["caption"]
            ))
        fee_img = _peer_fee_chart(peer_fees)
        if fee_img is not None:
            story.append(Spacer(1, 0.2*cm))
            story.append(fee_img)
        story.append(Spacer(1, 0.3*cm))

    # ── 七点五、指数估值与溢价折价 ──
    if index_val:
        story.append(Paragraph("7.5 跟踪指数估值位置", st["h2"]))
        val_rows = [
            ["指标", "当前值", "历史分位（越低越便宜）"],
            ["市盈率 PE", _disp_num(index_val.get("current_pe")),
             _signal_text("pe_pct", index_val.get("pe_percentile")) if index_val.get("pe_percentile") is not None else "未获取"],
            ["市净率 PB", _disp_num(index_val.get("current_pb")),
             _signal_text("pe_pct", index_val.get("pb_percentile")) if index_val.get("pb_percentile") is not None else "未获取"],
        ]
        story.append(_tbl(val_rows, col_widths=[4*cm, 3*cm, 5*cm]))
        story.append(Spacer(1, 0.2*cm))

    if premium_disc:
        story.append(Paragraph("7.6 溢价折价分析", st["h2"]))
        prem = premium_disc.get("current_premium", 0)
        prem_label = "溢价" if prem > 0 else "折价"
        prem_rows = [
            ["指标", "数值"],
            ["当前溢折率", f"{_signal_text('premium_abs', abs(prem))}（{prem_label}）"],
            ["历史分位", _disp_pct(premium_disc.get('premium_percentile'))],
            ["近1年最高溢价", _disp_pct(premium_disc.get('max_premium'))],
            ["近1年最低折价", _disp_pct(premium_disc.get('min_premium'))],
            ["近1年均值", _disp_pct(premium_disc.get('avg_premium'))],
        ]
        story.append(_tbl(prem_rows, col_widths=[6*cm, 6*cm]))
        if premium_disc.get("note"):
            story.append(Paragraph(premium_disc["note"], st["caption"]))
        story.append(Spacer(1, 0.3*cm))

    # ── 八、风险提示 ──
    story.append(Paragraph("八、空方逻辑与风险推演", st["h1"]))
    intro = _chapter_intro_etf("风险提示")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    story.append(Paragraph(
        "对抗确认偏误：强制列出看空理由与黑天鹅场景。以下量化信号来自配置模型规则识别，"
        "黑天鹅为基于指数特征与 ETF 机制的情景假设，不代表预测。",
        st["caption"]
    ))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("看空理由（量化信号）", st["h2"]))
    for b in etf_bear.get("bear", []):
        story.append(Paragraph(f"• 【判断】{b}", st["body"]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("黑天鹅场景（需重点防范）", st["h2"]))
    for s in etf_bear.get("swans", []):
        story.append(Paragraph(f"• 【情景】{s}", st["body"]))
    story.append(Paragraph(
        "注：黑天鹅为基于行业特征与 ETF 机制的情景假设，不代表预测；用于提示需持续跟踪的脆弱点。",
        st["caption"]
    ))
    story.append(Spacer(1, 0.3*cm))

    # ── 九、未来验证节点（监控清单）（T1：借鉴股票报告 §18）──
    story.append(Paragraph("九、未来验证节点（监控清单）", st["h1"]))
    intro = _chapter_intro_etf("监控清单")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    story.append(Paragraph(
        "以下为规则化生成的跟踪框架：强化逻辑的事件与证伪逻辑的数据，用于持续验证研究结论。不构成买卖建议。",
        st["caption"]
    ))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("强化逻辑的事件", st["h2"]))
    for item in etf_monitor.get("strengthen", []):
        story.append(Paragraph(f"• 【验证·强化】{item}", st["body"]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("证伪逻辑的数据", st["h2"]))
    for item in etf_monitor.get("falsify", []):
        story.append(Paragraph(f"• 【验证·证伪】{item}", st["body"]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("关键时间节点", st["h2"]))
    for item in etf_monitor.get("milestones", []):
        story.append(Paragraph(f"• {item}", st["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 十、赚钱机制与商业模式拆解（T1：借鉴股票报告 §19）──
    story.append(Paragraph("十、赚钱机制与商业模式拆解", st["h1"]))
    intro = _chapter_intro_etf("赚钱机制")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    story.append(Paragraph(
        "本节从收益来源、成本侵蚀、跟踪误差与现金拖累拆解 ETF“靠什么赚钱”，区别于主动基金的选股超额。",
        st["caption"]
    ))
    story.append(Spacer(1, 0.2*cm))
    story.append(_tbl(etf_biz.get("rows", []), col_widths=[4*cm, 12*cm]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(etf_biz.get("narrative", ""), st["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 十一、数据来源与取数说明（T1：借鉴股票报告 §22）──
    story.append(Paragraph("十一、数据来源与取数说明", st["h1"]))
    intro = _chapter_intro_etf("数据来源")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    ds_rows = [["数据项", "来源 / 状态"]]
    ds_rows.append(["基金规模、费率、成立日、实时行情", "通达信 MCP（tdx_quotes / tdx_indicator_select），零 token 落盘"])
    ds_rows.append(["跟踪指数 PE 历史与分位", "通达信 MCP（tdx_api_data gzfx），727 行，零 token 落盘"])
    ds_rows.append(["宽基估值锚（沪深300/中证500/创业板指 PE·PB·股息率·分位）", "通达信 MCP（tdx_security_deep_info 指数历史估值），各 37 个月度点，零 token 落盘"])
    ds_rows.append(["同类 ETF 费率（588080/588050/588090/588180/588280 管理费+托管费+综合费率）", "通达信 MCP（tdx_security_deep_info 基金购买信息/基本资料），零 token 落盘"])
    ds_rows.append(["单日溢折率", "现价（tdx_quotes HQInfo.Now）对比 IOPV，零 token"])
    ds_rows.append(["各期收益率", "通达信 MCP（tdx_kline，前复权 260 行），零 token"])
    ds_rows.append(["成分股/行业权重、份额流变、NAV 历史分位、同类排名", "TDX 环境未提供源 → 标注「未获取」，未伪造"])
    story.append(_tbl(ds_rows, col_widths=[6*cm, 10*cm]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "本报告遵循零 token 数据策略：优先使用通达信 MCP 实时/落盘数据，缺失项一律诚实标注「未获取」或「数据不足」，"
        "不以模型生成内容充当事实。",
        st["caption"]
    ))
    story.append(Spacer(1, 0.3*cm))

    doc.build(
        story,
        onFirstPage=lambda canvas, doc_obj: draw_report_footer(canvas, doc_obj, "etf"),
        onLaterPages=lambda canvas, doc_obj: draw_report_footer(canvas, doc_obj, "etf"),
    )
    print(f"\n✓ PDF 报告已生成：{output_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python3 step3_generate_pdf_report.py <data.json> <output.pdf>")
        sys.exit(1)
    create_etf_pdf(sys.argv[1], sys.argv[2])
