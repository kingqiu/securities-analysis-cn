#!/usr/bin/env python3
"""
步骤3：基于真实数据生成 ETF 深度分析 PDF 报告（含 Minima AI 买卖建议）
"""

import json
import os
import tempfile
from datetime import datetime

import matplotlib
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
from etf_analyst_model import build_etf_research_view, render_etf_research_brief
from pdf_design import (
    CN_FONT as SHARED_CN_FONT,
    add_cover,
    build_styles,
    callout_box,
    draw_report_footer,
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

    if "free_market_data" in raw:
        d["free_market_data"] = raw["free_market_data"]

    d["stock_names"] = raw.get("stock_names", {})
    return d


def _calc_returns(nav_df):
    if nav_df is None or nav_df.empty:
        return {}
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
    """指数估值分位"""
    if index_dailybasic_df is None or index_dailybasic_df.empty:
        return {}

    df = index_dailybasic_df.sort_values("trade_date").copy()

    for col in ["pe", "pb"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "pe" not in df.columns or "pb" not in df.columns:
        return {}

    latest_pe = df["pe"].iloc[-1] if not df["pe"].dropna().empty else None
    latest_pb = df["pb"].iloc[-1] if not df["pb"].dropna().empty else None

    pe_percentile = None
    pb_percentile = None

    if latest_pe is not None and not df["pe"].dropna().empty:
        pe_percentile = round((df["pe"] < latest_pe).sum() / len(df["pe"].dropna()) * 100, 1)

    if latest_pb is not None and not df["pb"].dropna().empty:
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
        return {}
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

    returns = _calc_returns(nav_df)
    te      = _calc_te(daily_df, index_df)
    ma_pos  = _ma_position(nav_df)
    aum_trend = _aum_trend(share_df)
    flow_metrics = _calc_flow_metrics(share_df)
    te_decomp = _decompose_tracking_diff(daily_df, index_df)
    index_val = _index_valuation_percentile(index_dailybasic_df)
    premium_disc = _calc_premium_discount(nav_df, daily_df)
    concentration = _index_concentration(index_weight_df)

    m_fee = float(basic.get("m_fee") or 0)
    c_fee = float(basic.get("c_fee") or 0)
    total_fee = round(m_fee + c_fee, 4)

    aum_bn = "N/A"
    if share_df is not None and not share_df.empty:
        share_df2 = share_df.copy()
        col = "net_asset" if "net_asset" in share_df2.columns else "fd_share"
        share_df2[col] = pd.to_numeric(share_df2[col], errors="coerce")
        latest_val = share_df2[col].dropna().iloc[-1] if not share_df2[col].dropna().empty else None
        if latest_val:
            # fd_share 单位是万份，net_asset 单位是元
            aum_bn = round(latest_val / 1e4, 1) if col == "net_asset" else round(latest_val / 1e4, 1)

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
        "aum": aum_bn,
        "aum_trend": aum_trend,
        "ma_position": ma_pos,
        "index_pe": index_val.get("current_pe", "N/A") if index_val else "N/A",
        "index_pe_pct": index_val.get("pe_percentile", "N/A") if index_val else "N/A",
        "index_pb": index_val.get("current_pb", "N/A") if index_val else "N/A",
        "index_pb_pct": index_val.get("pb_percentile", "N/A") if index_val else "N/A",
        "premium": premium_disc.get("current_premium", "N/A") if premium_disc else "N/A",
        "premium_pct": premium_disc.get("premium_percentile", "N/A") if premium_disc else "N/A",
        "flow_trend": flow_metrics.get("trend_20d", "未知") if flow_metrics else "未知",
        "net_flow_20d": flow_metrics.get("net_flow_20d", "N/A") if flow_metrics else "N/A",
        "net_flow_60d": flow_metrics.get("net_flow_60d", "N/A") if flow_metrics else "N/A",
        "top10_weight": concentration.get("top10_weight", "N/A"),
        "top20_weight": concentration.get("top20_weight", "N/A"),
        "industry_weight_status": concentration.get("industry_weight_status", "缺少行业映射"),
        "current_price": realtime_quote.get("price", "N/A"),
        "change_pct": realtime_quote.get("change_pct", "N/A"),
        "turnover_rate": realtime_quote.get("turnover_rate", "N/A"),
        "amount": realtime_quote.get("amount", "N/A"),
    }
    etf_view = build_etf_research_view(etf_summary)
    etf_brief = render_etf_research_brief(etf_view)

    # AI 建议：作为配置模型之后的解释补充
    advice_text = get_investment_advice("etf", etf_summary)

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
            ["配置评级", str(etf_view.get("allocation_rating", "N/A")), f"配置分 {etf_view.get('allocation_score', 'N/A')}"],
            ["交易评级", str(etf_view.get("trading_rating", "N/A")), f"交易分 {etf_view.get('trading_score', 'N/A')}"],
            ["综合费率", f"{total_fee}%/年", f"规模 {aum_bn}亿元"],
        ],
        notes=[
            ["核心结论", f"综合费率{total_fee}%/年、规模{aum_bn}亿元；跟踪误差{etf_summary.get('tracking_error')}%，配置价值取决于指数估值与流动性。"],
            ["关注变量", "指数估值、跟踪误差、溢价折价、规模流动性、费率和份额变化。"],
            ["主要风险", "指数系统性下跌、跟踪偏差扩大、流动性下降及高溢价买入风险。"],
        ],
    )

    # ── 一、投资摘要 ──
    story.append(Paragraph("一、投资摘要", st["h1"]))
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
        ["溢价/折价", f"{etf_summary.get('premium')}%", f"分位 {etf_summary.get('premium_pct')}%"],
        ["近60日份额", f"{etf_summary.get('net_flow_60d')}万份", "资金申赎趋势"],
    ], kind="etf"))
    story.append(Spacer(1, 0.3*cm))

    # ── 二、配置与交易计划 ──
    story.append(Paragraph("二、ETF配置与交易计划", st["h1"]))
    story.append(callout_box("以下结论由 ETF 配置模型先生成，重点关注指数估值、跟踪质量、规模流动性、费率和溢价折价；仅供研究参考。", kind="etf"))
    story.append(Spacer(1, 0.2*cm))
    plan_rows = [
        ["事项", "模型结论"],
        ["配置评级", f"{etf_view.get('allocation_rating')}（配置分{etf_view.get('allocation_score')}）"],
        ["交易评级", f"{etf_view.get('trading_rating')}（交易分{etf_view.get('trading_score')}）"],
        ["场内实时状态", f"价格{etf_view.get('current_price', 'N/A')}；涨跌{etf_view.get('change_pct', 'N/A')}%；换手{etf_view.get('turnover_rate', 'N/A')}%"],
        ["定投计划", etf_view.get("dca_plan", "")],
        ["加仓条件", etf_view.get("add_condition", "")],
        ["止盈/再平衡", etf_view.get("rebalance_condition", "")],
    ]
    story.append(_tbl(plan_rows, col_widths=[3.5*cm, 12.5*cm]))
    story.append(Spacer(1, 0.2*cm))

    pro_rows = [
        ["专业维度", "当前读数", "解读"],
        ["跟踪误差", f"{etf_summary.get('tracking_error')}% / 日均偏差{etf_summary.get('tracking_bias')}%", "越低说明跟踪指数越稳定，持续偏差需复核现金拖累、费用和复制误差"],
        ["溢价/折价", f"{etf_summary.get('premium')}%（分位{etf_summary.get('premium_pct')}%）", "高溢价不追买，折价需结合流动性和申赎机制判断"],
        ["份额变化", f"20日{etf_summary.get('net_flow_20d')}万份；60日{etf_summary.get('net_flow_60d')}万份", "份额扩张代表资金配置热度改善，持续赎回需警惕流动性下降"],
        ["成分集中度", f"Top10 {etf_summary.get('top10_weight')}%；Top20 {etf_summary.get('top20_weight')}%", "集中度越高，龙头股或单一行业波动对ETF影响越大"],
        ["行业权重", etf_summary.get("industry_weight_status"), "后续可接入成分股行业映射后输出行业暴露矩阵"],
        ["策略适配", f"定投{etf_view.get('strategy_fit', {}).get('定投')}；波段{etf_view.get('strategy_fit', {}).get('波段')}；资产配置{etf_view.get('strategy_fit', {}).get('资产配置')}", "不同投资目的对应不同买入纪律和仓位上限"],
    ]
    story.append(Paragraph("ETF专业诊断", st["h2"]))
    story.append(_tbl(pro_rows, col_widths=[3*cm, 5*cm, 8*cm]))
    story.append(Spacer(1, 0.2*cm))

    story.extend(md_to_story(etf_brief, st["body"], table_builder=_tbl))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("AI 解读", st["h2"]))
    story.extend(md_to_story(advice_text, st["body"], table_builder=_tbl))
    story.append(Spacer(1, 0.3*cm))

    # ── 三、业绩分析 ──
    story.append(Paragraph("三、业绩分析", st["h1"]))
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
                f"指数成分集中度：前十大权重合计{concentration.get('top10_weight','N/A')}%，前二十大权重合计{concentration.get('top20_weight','N/A')}%。{concentration.get('industry_weight_status','')}",
                st["caption"]
            ))
    else:
        story.append(Paragraph("持仓数据暂不可用", st["body"]))
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
    fee_rows = [
        ["费用类型", "费率"],
        ["管理费", f"{m_fee}%/年"],
        ["托管费", f"{c_fee}%/年"],
        ["综合费率", f"{total_fee}%/年"],
    ]
    story.append(_tbl(fee_rows, col_widths=[6*cm, 6*cm]))
    story.append(Spacer(1, 0.3*cm))

    # ── 七点五、指数估值与溢价折价 ──
    if index_val:
        story.append(Paragraph("7.5 跟踪指数估值位置", st["h2"]))
        val_rows = [
            ["指标", "当前值", "历史分位（越低越便宜）"],
            ["市盈率 PE", str(index_val.get("current_pe", "N/A")),
             f"{index_val.get('pe_percentile','N/A')}%" if index_val.get('pe_percentile') is not None else "N/A"],
            ["市净率 PB", str(index_val.get("current_pb", "N/A")),
             f"{index_val.get('pb_percentile','N/A')}%" if index_val.get('pb_percentile') is not None else "N/A"],
        ]
        story.append(_tbl(val_rows, col_widths=[4*cm, 3*cm, 5*cm]))
        story.append(Spacer(1, 0.2*cm))

    if premium_disc:
        story.append(Paragraph("7.6 溢价折价分析", st["h2"]))
        prem = premium_disc.get("current_premium", 0)
        prem_label = "溢价" if prem > 0 else "折价"
        prem_rows = [
            ["指标", "数值"],
            ["当前溢折率", f"{prem:.2f}%（{prem_label}）"],
            ["历史分位", f"{premium_disc.get('premium_percentile','N/A')}%"],
            ["近1年最高溢价", f"{premium_disc.get('max_premium','N/A')}%"],
            ["近1年最低折价", f"{premium_disc.get('min_premium','N/A')}%"],
            ["近1年均值", f"{premium_disc.get('avg_premium','N/A')}%"],
        ]
        story.append(_tbl(prem_rows, col_widths=[6*cm, 6*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 八、风险提示 ──
    story.append(Paragraph("八、风险提示", st["h1"]))
    risks = [
        "本报告基于历史数据，不代表未来表现，市场有风险，投资需谨慎。",
        "ETF 被动跟踪指数，指数下跌时基金净值同步下跌，无法规避系统性风险。",
        "基金规模过小（低于2亿元）存在清盘风险，请关注规模变化。",
        "本报告由 AI 辅助生成，仅供参考，不构成任何投资建议或承诺。",
    ]
    for r in risks:
        story.append(Paragraph(f"• {r}", st["body"]))

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
