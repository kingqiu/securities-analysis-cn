#!/usr/bin/env python3
"""
步骤4：基于真实数据生成股票深度分析 PDF 报告（含 Minima AI 研究解读）
"""

import json
import os
import re
import tempfile
from datetime import datetime

os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".matplotlib-cache"))

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

from analyst_model import build_stock_research_view, render_stock_research_brief
from ai_analysis import get_investment_advice, get_industry_news
from config import md_to_rl, md_to_story
from peer_model import build_peer_view, render_peer_brief
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
    return build_styles("stock")

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _tbl(data, col_widths=None, header_bg="#8b1a1a"):
    return styled_table(data, col_widths=col_widths, kind="stock")


def _chart_to_image(fig, width=14*cm):
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    fig.savefig(tmp.name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return Image(tmp.name, width=width, height=width * 0.45)

# ── 数据加载 ──────────────────────────────────────────────────────────────────

def _load(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        raw = json.load(f)
    d = {"ts_code": raw.get("ts_code", "")}

    if "basic" in raw and raw["basic"]["items"]:
        d["basic"] = dict(zip(raw["basic"]["fields"], raw["basic"]["items"][0]))

    for key in ("daily", "daily_basic", "index_daily"):
        if key in raw:
            d[key] = pd.DataFrame(raw[key]["items"], columns=raw[key]["fields"])

    for key in ("income", "balancesheet", "cashflow", "fina_indicator", "top10_holders"):
        if key in raw:
            d[key] = pd.DataFrame(raw[key]["items"], columns=raw[key]["fields"])

    if "industry_peers" in raw:
        d["industry_peers"] = raw["industry_peers"]

    # 增强数据加载
    for key in ("mainbz_product", "mainbz_region", "dividend", "forecast",
                "holder_number", "moneyflow", "margin", "block_trade",
                "concepts", "pledge", "audit"):
        if key in raw and raw[key].get("items"):
            d[key] = pd.DataFrame(raw[key]["items"], columns=raw[key]["fields"])

    # 宏观新闻
    if "macro_news" in raw and raw["macro_news"].get("items"):
        d["macro_news"] = pd.DataFrame(raw["macro_news"]["items"], columns=raw["macro_news"]["fields"])

    # 互联网研究（web_research）
    if "web_research" in raw:
        d["web_research"] = raw["web_research"]

    if "realtime_quote" in raw and isinstance(raw["realtime_quote"], dict):
        d["realtime_quote"] = raw["realtime_quote"]

    if "free_market_data" in raw:
        d["free_market_data"] = raw["free_market_data"]

    return d


def _sanitize_research_text(text):
    """Remove broker rating action words from quoted web snippets."""
    value = str(text or "")
    value = re.sub(r"(?:强烈)?(?:推荐|买入|增持|优于大市|跑赢行业)[/／](?:维持|上调|下调)", "", value)
    value = re.sub(r"维持[“”\"']?(?:强烈推荐|推荐|买入|增持|优于大市|跑赢行业)[“”\"']?(?:评级)?", "", value)
    value = re.sub(r"(?:给予|首次覆盖)[“”\"']?(?:强烈推荐|推荐|买入|增持|优于大市|跑赢行业)[“”\"']?(?:评级)?", "", value)
    return value

# ── 计算函数 ──────────────────────────────────────────────────────────────────

def _latest_valuation(daily_basic_df):
    if daily_basic_df is None or daily_basic_df.empty:
        return {}
    df = daily_basic_df.sort_values("trade_date").copy()
    for col in ("pe_ttm", "pb", "total_mv"):
        df[col] = pd.to_numeric(df.get(col, np.nan), errors="coerce")
    latest = df.iloc[-1]
    pe_series = df["pe_ttm"].dropna()
    pe_pct = round((pe_series < latest["pe_ttm"]).mean() * 100, 1) if len(pe_series) > 10 else None
    return {
        "pe_ttm": round(latest["pe_ttm"], 2) if pd.notna(latest["pe_ttm"]) else None,
        "pb":     round(latest["pb"], 2)     if pd.notna(latest["pb"])     else None,
        "mv_bn":  round(latest["total_mv"] / 1e4, 1) if pd.notna(latest.get("total_mv")) else None,
        "pe_percentile": pe_pct,
    }


def _fin_summary(income_df, fina_df):
    result = {}
    if income_df is not None and not income_df.empty:
        df = income_df.copy()
        df["end_date"] = df["end_date"].astype(str)
        df = df[df["end_date"].str.endswith("1231")].sort_values("end_date")
        for col in ("total_revenue", "n_income_attr_p"):
            df[col] = pd.to_numeric(df.get(col, np.nan), errors="coerce")
        if len(df) >= 2:
            rev_now  = df["total_revenue"].iloc[-1]
            rev_prev = df["total_revenue"].iloc[-2]
            net_now  = df["n_income_attr_p"].iloc[-1]
            net_prev = df["n_income_attr_p"].iloc[-2]
            result["rev_growth"]    = round((rev_now / rev_prev - 1) * 100, 1) if rev_prev else None
            result["profit_growth"] = round((net_now / net_prev - 1) * 100, 1) if net_prev else None
        result["income_df"] = df

    if fina_df is not None and not fina_df.empty:
        df2 = fina_df.copy()
        df2["end_date"] = df2["end_date"].astype(str)
        df2 = df2[df2["end_date"].str.endswith("1231")].sort_values("end_date")
        for col in ("roe", "grossprofit_margin", "debt_to_assets"):
            df2[col] = pd.to_numeric(df2.get(col, np.nan), errors="coerce")
        if not df2.empty:
            latest = df2.iloc[-1]
            result["roe"]        = round(latest.get("roe", np.nan), 2)
            result["gross_margin"]= round(latest.get("grossprofit_margin", np.nan), 2)
            result["debt_ratio"] = round(latest.get("debt_to_assets", np.nan), 2)
        result["fina_df"] = df2

    return result


def _cashflow_quality(cashflow_df, income_df):
    """现金流质量分析：CFO/净利润匹配度"""
    result = {}
    if cashflow_df is None or cashflow_df.empty or income_df is None or income_df.empty:
        return result

    cf = cashflow_df.copy()
    inc = income_df.copy()
    cf["end_date"] = cf["end_date"].astype(str)
    inc["end_date"] = inc["end_date"].astype(str)
    cf = cf[cf["end_date"].str.endswith("1231")].sort_values("end_date")
    inc = inc[inc["end_date"].str.endswith("1231")].sort_values("end_date")

    if "n_cashflow_act" not in cf.columns or "n_income_attr_p" not in inc.columns:
        return result

    cf["n_cashflow_act"] = pd.to_numeric(cf["n_cashflow_act"], errors="coerce")
    inc["n_income_attr_p"] = pd.to_numeric(inc["n_income_attr_p"], errors="coerce")

    merged = pd.merge(
        cf[["end_date", "n_cashflow_act"]],
        inc[["end_date", "n_income_attr_p"]],
        on="end_date", how="inner"
    ).tail(5)

    if merged.empty:
        return result

    rows = []
    for _, row in merged.iterrows():
        cfo = row["n_cashflow_act"]
        net = row["n_income_attr_p"]
        ratio = round(cfo / net, 2) if net and net != 0 else None
        rows.append({
            "year": row["end_date"][:4],
            "cfo_bn": round(cfo / 1e8, 2) if pd.notna(cfo) else None,
            "net_bn": round(net / 1e8, 2) if pd.notna(net) else None,
            "ratio": ratio,
        })

    result["rows"] = rows
    latest = rows[-1] if rows else {}
    result["latest_ratio"] = latest.get("ratio")
    result["quality_label"] = (
        "优秀（现金含量高）" if (latest.get("ratio") or 0) >= 1.0
        else "一般（现金含量偏低）" if (latest.get("ratio") or 0) >= 0.5
        else "偏弱（利润质量存疑）"
    )
    return result


def _balance_sheet_quality(balancesheet_df, fina_df):
    """资产负债表质量：偿债能力与结构"""
    result = {}
    if balancesheet_df is None or balancesheet_df.empty:
        return result

    bs = balancesheet_df.copy()
    bs["end_date"] = bs["end_date"].astype(str)
    bs = bs[bs["end_date"].str.endswith("1231")].sort_values("end_date").tail(5)

    for col in ("total_assets", "total_liab", "accounts_receiv", "inventories"):
        if col in bs.columns:
            bs[col] = pd.to_numeric(bs[col], errors="coerce")

    rows = []
    for _, row in bs.iterrows():
        ta = row.get("total_assets", np.nan)
        tl = row.get("total_liab", np.nan)
        ar = row.get("accounts_receiv", np.nan)
        debt_ratio = round(tl / ta * 100, 1) if pd.notna(ta) and pd.notna(tl) and ta > 0 else None
        ar_ratio = round(ar / ta * 100, 1) if pd.notna(ta) and pd.notna(ar) and ta > 0 else None
        rows.append({
            "year": row["end_date"][:4],
            "debt_ratio": debt_ratio,
            "ar_ratio": ar_ratio,
        })

    result["rows"] = rows

    if fina_df is not None and not fina_df.empty:
        fi = fina_df.copy()
        fi["end_date"] = fi["end_date"].astype(str)
        fi = fi[fi["end_date"].str.endswith("1231")].sort_values("end_date")
        for col in ("current_ratio", "quick_ratio"):
            if col in fi.columns:
                fi[col] = pd.to_numeric(fi[col], errors="coerce")
        if not fi.empty:
            latest = fi.iloc[-1]
            result["current_ratio"] = round(latest.get("current_ratio", np.nan), 2) if pd.notna(latest.get("current_ratio")) else None
            result["quick_ratio"] = round(latest.get("quick_ratio", np.nan), 2) if pd.notna(latest.get("quick_ratio")) else None

    return result


def _industry_comp_valuation(industry_peers, val):
    """行业可比估值：当前股票 PE/PB 在行业中的分位"""
    if not industry_peers or not industry_peers.get("peers"):
        return {}

    peers = industry_peers["peers"]
    def _to_float(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    pe_list = [_to_float(p.get("pe_ttm")) for p in peers]
    pb_list = [_to_float(p.get("pb")) for p in peers]
    pe_list = [v for v in pe_list if v is not None]
    pb_list = [v for v in pb_list if v is not None]

    # 过滤负值（亏损股）
    pe_list = [v for v in pe_list if v > 0]
    pb_list = [v for v in pb_list if v > 0]

    result = {
        "industry": industry_peers.get("industry", ""),
        "peer_count": len(peers),
    }

    if pe_list:
        pe_arr = sorted(pe_list)
        result["industry_pe_median"] = round(np.median(pe_arr), 1)
        result["industry_pe_25"] = round(np.percentile(pe_arr, 25), 1)
        result["industry_pe_75"] = round(np.percentile(pe_arr, 75), 1)
        cur_pe = val.get("pe_ttm")
        if cur_pe and cur_pe > 0:
            result["pe_percentile"] = round(sum(1 for v in pe_arr if v < cur_pe) / len(pe_arr) * 100, 1)

    if pb_list:
        pb_arr = sorted(pb_list)
        result["industry_pb_median"] = round(np.median(pb_arr), 1)
        result["industry_pb_25"] = round(np.percentile(pb_arr, 25), 1)
        result["industry_pb_75"] = round(np.percentile(pb_arr, 75), 1)
        cur_pb = val.get("pb")
        if cur_pb and cur_pb > 0:
            result["pb_percentile"] = round(sum(1 for v in pb_arr if v < cur_pb) / len(pb_arr) * 100, 1)

    return result


def _trading_discipline(daily_df):
    if daily_df is None or daily_df.empty:
        return {}
    df = daily_df.sort_values("trade_date").copy()
    for col in ("close", "high", "low", "vol"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    recent20 = df.tail(20)
    recent60 = df.tail(60)
    result = {}
    if not recent20.empty:
        result["support_20d"] = round(float(recent20["low"].min()), 2) if "low" in recent20 else None
        result["resistance_20d"] = round(float(recent20["high"].max()), 2) if "high" in recent20 else None
    if not recent60.empty:
        result["support_60d"] = round(float(recent60["low"].min()), 2) if "low" in recent60 else None
        result["resistance_60d"] = round(float(recent60["high"].max()), 2) if "high" in recent60 else None
        if "close" in recent60:
            ret = recent60["close"].pct_change().dropna()
            if not ret.empty:
                result["volatility_60d"] = round(float(ret.std() * np.sqrt(250) * 100), 2)
    if "vol" in df.columns and len(df.dropna(subset=["vol"])) >= 20:
        avg20 = df["vol"].tail(20).mean()
        latest = df["vol"].iloc[-1]
        result["volume_ratio"] = round(float(latest / avg20), 2) if avg20 else None
    return result


def _scenario_analysis(daily_basic_df, income_df, val):
    """三情景分析：基于历史 PE 区间 + 历史增速区间"""
    if daily_basic_df is None or daily_basic_df.empty:
        return {}

    db = daily_basic_df.sort_values("trade_date").copy()
    db["pe_ttm"] = pd.to_numeric(db["pe_ttm"], errors="coerce")
    db["close"] = pd.to_numeric(db["close"], errors="coerce")

    pe_series = db["pe_ttm"].dropna()
    pe_series = pe_series[pe_series > 0]
    if len(pe_series) < 10:
        return {}

    pe_bull = round(float(np.percentile(pe_series, 75)), 1)
    pe_base = round(float(np.percentile(pe_series, 50)), 1)
    pe_bear = round(float(np.percentile(pe_series, 25)), 1)
    pe_now = val.get("pe_ttm")

    # 历史净利润增速
    growth_rates = []
    if income_df is not None and not income_df.empty:
        inc = income_df.copy()
        inc["end_date"] = inc["end_date"].astype(str)
        inc = inc[inc["end_date"].str.endswith("1231")].sort_values("end_date")
        inc["n_income_attr_p"] = pd.to_numeric(inc.get("n_income_attr_p", np.nan), errors="coerce")
        for i in range(1, len(inc)):
            prev = inc["n_income_attr_p"].iloc[i - 1]
            curr = inc["n_income_attr_p"].iloc[i]
            if prev and prev > 0 and pd.notna(curr):
                growth_rates.append((curr / prev - 1) * 100)

    if growth_rates:
        g_bull = round(float(np.percentile(growth_rates, 75)), 1)
        g_base = round(float(np.percentile(growth_rates, 50)), 1)
        g_bear = round(float(np.percentile(growth_rates, 25)), 1)
    else:
        g_bull, g_base, g_bear = 15.0, 8.0, 0.0

    # 当前股价
    cur_price = float(db["close"].iloc[-1]) if not db["close"].dropna().empty else None
    if not cur_price or not pe_now or pe_now <= 0:
        return {
            "pe_bull": pe_bull, "pe_base": pe_base, "pe_bear": pe_bear,
            "g_bull": g_bull, "g_base": g_base, "g_bear": g_bear,
        }

    # 情景价格 = 当前价格 × (1 + 增速/100) × (情景PE / 当前PE)
    price_bull = round(cur_price * (1 + g_bull / 100) * (pe_bull / pe_now), 2)
    price_base = round(cur_price * (1 + g_base / 100) * (pe_base / pe_now), 2)
    price_bear = round(cur_price * (1 + g_bear / 100) * (pe_bear / pe_now), 2)

    return {
        "cur_price": round(cur_price, 2),
        "pe_bull": pe_bull, "pe_base": pe_base, "pe_bear": pe_bear,
        "g_bull": g_bull, "g_base": g_base, "g_bear": g_bear,
        "price_bull": price_bull, "price_base": price_base, "price_bear": price_bear,
        "upside_bull": round((price_bull / cur_price - 1) * 100, 1),
        "upside_base": round((price_base / cur_price - 1) * 100, 1),
        "upside_bear": round((price_bear / cur_price - 1) * 100, 1),
    }


def _ma_position(daily_df):
    if daily_df is None or daily_df.empty or len(daily_df) < 60:
        return "未知"
    df = daily_df.sort_values("trade_date").copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    latest = df["close"].iloc[-1]
    ma20 = df["close"].iloc[-20:].mean()
    ma60 = df["close"].iloc[-60:].mean()
    if latest > ma20 and latest > ma60:
        return "上方（多头排列）"
    elif latest < ma20 and latest < ma60:
        return "下方（空头排列）"
    return "附近（震荡区间）"

# ── 图表 ──────────────────────────────────────────────────────────────────────

def _price_chart(daily_df, index_df, stock_name):
    df = daily_df.sort_values("trade_date").copy().tail(250)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["trade_date"], df["close"], color="#8b1a1a", linewidth=1.5, label=stock_name)

    if index_df is not None and not index_df.empty:
        idx = index_df.sort_values("trade_date").copy().tail(250)
        idx["close"] = pd.to_numeric(idx["close"], errors="coerce")
        idx["trade_date"] = pd.to_datetime(idx["trade_date"])
        # 归一化到同起点
        base_s = df["close"].iloc[0]; base_i = idx["close"].iloc[0]
        if base_s and base_i:
            ax2 = ax.twinx()
            ax2.plot(idx["trade_date"], idx["close"] / base_i * base_s,
                     color="#888888", linewidth=1, linestyle="--", label="上证综指（归一）")
            ax2.set_ylabel("指数（归一）", fontsize=8)
            ax2.legend(loc="upper left", fontsize=8)

    ax.set_title(f"{stock_name} 近1年股价走势", fontsize=12)
    ax.set_xlabel("日期"); ax.set_ylabel("收盘价（元）")
    ax.grid(True, alpha=0.3); ax.legend(loc="upper right")
    fig.tight_layout()
    return _chart_to_image(fig)


def _trading_plan_chart(analyst_view, stock_name):
    """Research scenario bands for valuation and risk review."""
    if not analyst_view:
        return None

    cur = analyst_view.get("cur_price")
    buy_zone = analyst_view.get("buy_zone")
    watch_zone = analyst_view.get("watch_zone")
    take_profit_zone = analyst_view.get("take_profit_zone")
    stop_loss = analyst_view.get("stop_loss")
    bear = analyst_view.get("price_bear")
    base = analyst_view.get("price_base")
    bull = analyst_view.get("price_bull")

    values = []
    for item in (cur, stop_loss, bear, base, bull):
        if item is not None:
            values.append(float(item))
    for zone in (buy_zone, watch_zone, take_profit_zone):
        if zone:
            values.extend([float(zone[0]), float(zone[1])])
    if len(values) < 2:
        return None

    low = min(values)
    high = max(values)
    pad = max((high - low) * 0.12, high * 0.03)
    x_min = max(0, low - pad)
    x_max = high + pad

    fig, ax = plt.subplots(figsize=(10, 2.8))
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xlabel("价格（元）")
    ax.set_title(f"{stock_name} 情景参考区间", fontsize=12)

    bands = [
        ("估值安全边际观察区", buy_zone, "#d5f5e3", "#1e8449"),
        ("中性观察区", watch_zone, "#fcf3cf", "#b7950b"),
        ("高估值复核区", take_profit_zone, "#fadbd8", "#922b21"),
    ]
    y = 0.46
    h = 0.28
    for label, zone, color, edge in bands:
        if not zone:
            continue
        start, end = sorted([float(zone[0]), float(zone[1])])
        ax.barh(y, end - start, left=start, height=h, color=color, edgecolor=edge, linewidth=1)
        ax.text((start + end) / 2, y, label, ha="center", va="center", fontsize=9, color=edge)

    marker_specs = [
        ("风险复核线", stop_loss, "#7b241c", 0.18),
        ("当前价", cur, "#000000", 0.78),
        ("谨慎价值", bear, "#7f8c8d", 0.08),
        ("中性价值", base, "#8b1a1a", 0.90),
        ("乐观价值", bull, "#c0392b", 0.08),
    ]
    for label, value, color, text_y in marker_specs:
        if value is None:
            continue
        value = float(value)
        ax.axvline(value, color=color, linestyle="--" if label != "当前价" else "-", linewidth=1.2)
        ax.text(value, text_y, f"{label}\n{value:.2f}", ha="center", va="center", fontsize=8, color=color)

    ax.grid(True, alpha=0.25, axis="x")
    for spine in ("left", "right", "top"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return _chart_to_image(fig, width=15*cm)


def _revenue_chart(income_df, stock_name):
    df = income_df.copy()
    df["end_date"] = df["end_date"].astype(str)
    df = df[df["end_date"].str.endswith("1231")].sort_values("end_date").tail(5)
    df["total_revenue"]    = pd.to_numeric(df.get("total_revenue", np.nan), errors="coerce") / 1e8
    df["n_income_attr_p"]  = pd.to_numeric(df.get("n_income_attr_p", np.nan), errors="coerce") / 1e8

    fig, ax = plt.subplots(figsize=(10, 4))
    x = range(len(df))
    w = 0.35
    ax.bar([i - w/2 for i in x], df["total_revenue"], width=w, label="营业收入（亿）", color="#8b1a1a", alpha=0.8)
    ax.bar([i + w/2 for i in x], df["n_income_attr_p"], width=w, label="归母净利润（亿）", color="#c0392b", alpha=0.6)
    ax.set_xticks(list(x)); ax.set_xticklabels([d[:4]+"年" for d in df["end_date"]])
    ax.set_title(f"{stock_name} 近5年营收与净利润", fontsize=12)
    ax.set_ylabel("金额（亿元）"); ax.legend(); ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    return _chart_to_image(fig)

# ── 主函数 ────────────────────────────────────────────────────────────────────

def create_stock_pdf(data_file: str, output_path: str) -> None:
    print("=" * 80)
    print("生成股票深度分析 PDF 报告")
    print("=" * 80)

    d = _load(data_file)
    st = _styles()
    basic = d.get("basic", {})
    stock_name = basic.get("name", d["ts_code"])
    industry   = basic.get("industry", "")

    daily_df    = d.get("daily")
    daily_basic = d.get("daily_basic")
    index_df    = d.get("index_daily")
    income_df   = d.get("income")
    fina_df     = d.get("fina_indicator")
    holders_df  = d.get("top10_holders")
    cashflow_df = d.get("cashflow")
    balance_df  = d.get("balancesheet")

    # 增强数据
    mainbz_product = d.get("mainbz_product")
    mainbz_region = d.get("mainbz_region")
    dividend_df = d.get("dividend")
    forecast_df = d.get("forecast")
    holder_num_df = d.get("holder_number")
    moneyflow_df = d.get("moneyflow")
    margin_df = d.get("margin")
    block_trade_df = d.get("block_trade")
    concepts_df = d.get("concepts")
    pledge_df = d.get("pledge")
    audit_df = d.get("audit")
    macro_news_df = d.get("macro_news")
    web_research = d.get("web_research")
    realtime_quote = d.get("realtime_quote", {})

    val   = _latest_valuation(daily_basic)
    fin   = _fin_summary(income_df, fina_df)
    ma_pos = _ma_position(daily_df)
    cf_quality = _cashflow_quality(cashflow_df, income_df)
    bs_quality = _balance_sheet_quality(balance_df, fina_df)
    industry_comp = _industry_comp_valuation(d.get("industry_peers"), val)
    scenario = _scenario_analysis(daily_basic, income_df, val)
    trading_disc = _trading_discipline(daily_df)
    if scenario and realtime_quote.get("price"):
        try:
            realtime_price = round(float(realtime_quote["price"]), 2)
            old_price = float(scenario.get("cur_price") or 0)
            if old_price > 0 and realtime_price > 0:
                scale = realtime_price / old_price
                scenario["cur_price"] = realtime_price
                for key in ("price_bull", "price_base", "price_bear"):
                    if scenario.get(key) not in (None, "N/A"):
                        scenario[key] = round(float(scenario[key]) * scale, 2)
                scenario["price_source"] = realtime_quote.get("source", "free_realtime_quote")
        except (TypeError, ValueError):
            pass
    peer_view = build_peer_view({
        "name": stock_name,
        "ts_code": d["ts_code"],
        "mv_bn": val.get("mv_bn"),
        "pe_ttm": val.get("pe_ttm"),
        "pb": val.get("pb"),
        "roe": fin.get("roe"),
        "gross_margin": fin.get("gross_margin"),
        "rev_growth": fin.get("rev_growth"),
        "profit_growth": fin.get("profit_growth"),
    }, d.get("industry_peers"))

    # 计算增强指标
    # 主力资金净流入(近20日合计)
    net_mf_20d = "N/A"
    if moneyflow_df is not None and not moneyflow_df.empty:
        mf = moneyflow_df.copy()
        mf["net_mf_amount"] = pd.to_numeric(mf.get("net_mf_amount", np.nan), errors="coerce")
        net_val = mf["net_mf_amount"].head(20).sum()
        net_mf_20d = round(net_val, 0) if pd.notna(net_val) else "N/A"

    # 融资余额趋势
    margin_trend = "N/A"
    if margin_df is not None and not margin_df.empty:
        mg = margin_df.sort_values("trade_date").copy()
        mg["rzye"] = pd.to_numeric(mg["rzye"], errors="coerce")
        if len(mg) >= 5:
            first_5 = mg["rzye"].head(5).mean()
            last_5 = mg["rzye"].tail(5).mean()
            if first_5 > 0:
                chg = (last_5 - first_5) / first_5 * 100
                margin_trend = f"{'增加' if chg > 1 else '减少' if chg < -1 else '持平'}（{round(chg,1)}%）"

    # 股东人数变化
    holder_change = "N/A"
    if holder_num_df is not None and not holder_num_df.empty:
        hn = holder_num_df.sort_values("end_date").copy()
        hn["holder_num"] = pd.to_numeric(hn["holder_num"], errors="coerce")
        if len(hn) >= 2:
            latest_num = hn["holder_num"].iloc[-1]
            prev_num = hn["holder_num"].iloc[-2]
            if prev_num > 0:
                chg_pct = (latest_num - prev_num) / prev_num * 100
                holder_change = f"{round(latest_num/10000,1)}万户（{'增加' if chg_pct > 0 else '减少'}{abs(round(chg_pct,1))}%）"

    # 大宗交易
    block_trade_info = "N/A"
    if block_trade_df is not None and not block_trade_df.empty:
        bt = block_trade_df.copy()
        bt["amount"] = pd.to_numeric(bt.get("amount", 0), errors="coerce")
        total_amt = bt["amount"].sum()
        block_trade_info = f"{len(bt)}笔，合计{round(total_amt/10000, 1)}亿元"

    # 股权质押率
    pledge_ratio = "N/A"
    if pledge_df is not None and not pledge_df.empty:
        pl = pledge_df.sort_values("end_date").copy()
        pl["pledge_ratio"] = pd.to_numeric(pl.get("pledge_ratio", np.nan), errors="coerce")
        if not pl["pledge_ratio"].dropna().empty:
            pledge_ratio = round(float(pl["pledge_ratio"].iloc[-1]), 2)

    # 审计意见
    audit_opinion = "N/A"
    if audit_df is not None and not audit_df.empty:
        audit_opinion = audit_df.iloc[0].get("audit_result", "N/A")

    # 业绩预告（只取近1年内的）
    forecast_info = "暂无近期业绩预告"
    if forecast_df is not None and not forecast_df.empty:
        from datetime import datetime, timedelta
        _one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        _fc_recent = forecast_df[forecast_df["ann_date"].astype(str) >= _one_year_ago]
        if not _fc_recent.empty:
            fc = _fc_recent.sort_values("ann_date", ascending=False).iloc[0]
            fc_type = fc.get("type", "")
            fc_min = fc.get("p_change_min", "")
            fc_max = fc.get("p_change_max", "")
            forecast_info = f"{fc_type}（变动幅度{fc_min}%~{fc_max}%）"

    # 专业投研模型 + AI 研究解读（增强版）
    stock_summary = {
        "name": stock_name,
        "ts_code": d["ts_code"],
        "industry": industry,
        "pe_ttm": val.get("pe_ttm", "N/A"),
        "pe_percentile": val.get("pe_percentile", "N/A"),
        "pb": val.get("pb", "N/A"),
        "rev_growth": fin.get("rev_growth", "N/A"),
        "profit_growth": fin.get("profit_growth", "N/A"),
        "roe": fin.get("roe", "N/A"),
        "gross_margin": fin.get("gross_margin", "N/A"),
        "debt_ratio": fin.get("debt_ratio", "N/A"),
        "ma_position": ma_pos,
        "industry_pe_median": industry_comp.get("industry_pe_median", "N/A") if industry_comp else "N/A",
        "industry_pe_pct": industry_comp.get("pe_percentile", "N/A") if industry_comp else "N/A",
        "cfo_ratio": cf_quality.get("latest_ratio", "N/A") if cf_quality else "N/A",
        "audit_opinion": audit_opinion,
        "net_mf_20d": net_mf_20d,
        "margin_trend": margin_trend,
        "holder_change": holder_change,
        "block_trade_info": block_trade_info,
        "pledge_ratio": pledge_ratio,
        "price_bull": scenario.get("price_bull", "N/A") if scenario else "N/A",
        "price_base": scenario.get("price_base", "N/A") if scenario else "N/A",
        "price_bear": scenario.get("price_bear", "N/A") if scenario else "N/A",
        "cur_price": scenario.get("cur_price", "N/A") if scenario else "N/A",
        "price_source": scenario.get("price_source", "Tushare日线/估值") if scenario else "N/A",
        "forecast_info": forecast_info,
        "peer_context": render_peer_brief(peer_view) if peer_view else "同行龙头数据不足",
        "support_20d": trading_disc.get("support_20d", "N/A"),
        "support_60d": trading_disc.get("support_60d", "N/A"),
        "resistance_20d": trading_disc.get("resistance_20d", "N/A"),
        "resistance_60d": trading_disc.get("resistance_60d", "N/A"),
        "volatility_60d": trading_disc.get("volatility_60d", "N/A"),
        "volume_ratio": trading_disc.get("volume_ratio", "N/A"),
    }
    analyst_view = build_stock_research_view(stock_summary)
    analyst_brief = render_stock_research_brief(analyst_view)
    advice_text = get_investment_advice("stock", stock_summary)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    story = []

    # ── 封面 ──
    add_cover(
        story,
        stock_name,
        "股票深度分析报告",
        [
            ["证券代码", d["ts_code"]],
            ["所属行业", industry],
            ["报告日期", datetime.now().strftime("%Y年%m月%d日")],
        ],
        kind="stock",
        highlights=[
            ["研究状态", str(analyst_view.get("rating", "N/A")), f"综合分 {analyst_view.get('total_score', 'N/A')}"],
            ["当前股价", f"{stock_summary.get('cur_price', 'N/A')} 元", stock_summary.get("price_source", "Tushare日线/估值")],
            ["PE(TTM)", str(val.get("pe_ttm", "N/A")), f"历史分位 {val.get('pe_percentile', 'N/A')}%"],
        ],
        notes=[
            ["核心结论", f"当前PE(TTM){val.get('pe_ttm','N/A')}、历史分位{val.get('pe_percentile','N/A')}%，ROE{fin.get('roe','N/A')}%；估值不高但增长与现金流仍需验证。"],
            ["关注变量", "估值分位、业绩增长、现金流质量、资金技术和行业景气度共同影响研究判断。"],
            ["主要风险", "消费需求、行业竞争、政策变化、估值中枢下移及市场系统性波动。"],
        ],
    )

    add_report_reading_guide(story, kind="stock")

    # ── 一、公司概况 ──
    story.append(Paragraph("一、公司概况", st["h1"]))
    info_rows = [
        ["股票名称", stock_name, "股票代码", d["ts_code"]],
        ["所属行业", industry, "所在地区", basic.get("area","")],
        ["上市日期", basic.get("list_date",""), "市场", basic.get("market","")],
        ["总市值", f"{val.get('mv_bn','N/A')}亿元", "当前PE(TTM)", str(val.get("pe_ttm","N/A"))],
        ["当前PB", str(val.get("pb","N/A")), "PE历史分位", f"{val.get('pe_percentile','N/A')}%"],
        ["当前股价", f"{stock_summary.get('cur_price', 'N/A')}元", "价格来源", stock_summary.get("price_source", "Tushare日线/估值")],
    ]
    story.append(_tbl(info_rows, col_widths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm]))
    story.append(Spacer(1, 0.3*cm))
    story.append(metric_cards([
        ["ROE", f"{fin.get('roe', 'N/A')}%", "盈利能力"],
        ["营收增速", f"{fin.get('rev_growth', 'N/A')}%", "成长性"],
        ["现金流质量", cf_quality.get("quality_label", "N/A") if cf_quality else "N/A", "利润含金量"],
    ], kind="stock"))
    story.append(Spacer(1, 0.3*cm))

    evidence_map(story, [
        [
            "盈利质量是否稳定",
            f"ROE {fin.get('roe','N/A')}%；毛利率 {fin.get('gross_margin','N/A')}%；现金流质量 {cf_quality.get('quality_label','N/A') if cf_quality else 'N/A'}",
            "较强",
            "财务指标能帮助观察利润含金量，但不能单独代表未来增长。",
            "后续财报、费用率变化、现金流持续性",
        ],
        [
            "估值是否具备参考锚",
            f"PE(TTM) {val.get('pe_ttm','N/A')}；PB {val.get('pb','N/A')}；PE历史分位 {val.get('pe_percentile','N/A')}%",
            "中等",
            "估值分位提供相对位置参考，低分位仍需结合盈利预期验证。",
            "行业估值中枢、盈利预期、利率与风险偏好",
        ],
        [
            "与同行相比是否有优势",
            f"行业PE中位 {industry_comp.get('industry_pe_median','N/A') if industry_comp else 'N/A'}；同行样本 {industry_comp.get('peer_count','N/A') if industry_comp else 'N/A'}",
            "中等",
            "同行比较可提供横向参照，但需警惕业务结构差异导致的不可比。",
            "龙头份额、利润率差异、现金流和估值折溢价",
        ],
        [
            "行业景气是否改善",
            f"行业：{industry}；互联网研究与行业动态作为辅助线索",
            "偏弱",
            "新闻和行业动态适合提示方向，但需要和业绩、价格、销量交叉验证。",
            "订单、价格、销量、库存、市占率变化",
        ],
    ], kind="stock")

    add_followup_watchlist(story, [
        [
            "业绩与现金流",
            f"营收增速 {fin.get('rev_growth','N/A')}%；净利增速 {fin.get('profit_growth','N/A')}%；现金流质量 {cf_quality.get('quality_label','N/A') if cf_quality else 'N/A'}",
            "下一次财报/公告后",
            "复核收入、利润、毛利率、经营现金流是否同向改善，避免只看单一利润指标。",
        ],
        [
            "估值与同行位置",
            f"PE(TTM) {val.get('pe_ttm','N/A')}；历史分位 {val.get('pe_percentile','N/A')}%；同行PE中位 {industry_comp.get('industry_pe_median','N/A') if industry_comp else 'N/A'}",
            "每月或估值大幅波动后",
            "重新比较历史分位、同行估值和盈利预期，判断估值变化来自修复还是基本面折价。",
        ],
        [
            "资金与趋势",
            f"20日主力净流入 {net_mf_20d}万元；融资余额趋势 {margin_trend}；60日波动率 {trading_disc.get('volatility_60d','N/A')}%",
            "未来5-20个交易日",
            "观察成交、资金流和均线位置是否互相验证；若只出现单一信号，证据强度应下调。",
        ],
        [
            "行业与公司事件",
            f"行业：{industry}；业绩预告：{forecast_info}",
            "重要公告/行业新闻后",
            "优先用公司公告和权威行业信息复核需求、价格、库存、政策和竞争格局变化。",
        ],
    ], kind="stock")

    # ── 二、情景区间与观察触发器 ──
    story.append(Paragraph("二、情景区间与观察触发器", st["h1"]))
    story.append(callout_box("本节仅把模型测算结果整理为估值情景、风险复核线和后续观察触发器，用于研究复盘；不构成任何买卖建议。", kind="stock"))
    story.append(Spacer(1, 0.2*cm))
    plan_chart = _trading_plan_chart(analyst_view, stock_name)
    if plan_chart:
        story.append(plan_chart)
        story.append(Paragraph("图：情景参考区间。价格区间仅用于观察估值与风险状态，不代表任何交易判断。", st["caption"]))
        story.append(Spacer(1, 0.2*cm))

    plan_rows = [["情景/触发器", "参考区间", "研究观察含义"]]
    if analyst_view.get("buy_zone"):
        z = analyst_view["buy_zone"]
        plan_rows.append(["估值安全边际观察区", f"{z[0]:.2f}-{z[1]:.2f}元", "用于观察风险补偿是否改善，不对应交易动作"])
    if analyst_view.get("watch_zone"):
        z = analyst_view["watch_zone"]
        plan_rows.append(["中性观察区", f"{z[0]:.2f}-{z[1]:.2f}元", "关注估值、业绩和行业证据是否继续验证"])
    if analyst_view.get("take_profit_zone"):
        z = analyst_view["take_profit_zone"]
        plan_rows.append(["高估值复核区", f"{z[0]:.2f}-{z[1]:.2f}元", "复核估值是否已充分反映乐观预期"])
    if analyst_view.get("stop_loss") is not None:
        plan_rows.append(["风险复核线", f"{analyst_view['stop_loss']:.2f}元", "若触及需重新检查业绩、估值和趋势假设"])
    if len(plan_rows) > 1:
        story.append(_tbl(plan_rows, col_widths=[4*cm, 4*cm, 8*cm]))
        story.append(Spacer(1, 0.2*cm))

    story.extend(md_to_story(analyst_brief, st["body"], table_builder=_tbl))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("模型文字解读", st["h2"]))
    story.append(Spacer(1, 0.2*cm))
    story.extend(md_to_story(advice_text, st["body"], table_builder=_tbl))
    story.append(Spacer(1, 0.3*cm))

    # ── 三、股价与估值 ──
    story.append(Paragraph("三、股价与估值", st["h1"]))
    if daily_df is not None and not daily_df.empty:
        story.append(_price_chart(daily_df, index_df, stock_name))
        story.append(Paragraph("图：近1年股价走势（灰色虚线为上证综指归一化对比）", st["caption"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 四、业绩分析 ──
    story.append(Paragraph("四、业绩分析", st["h1"]))
    if income_df is not None and not income_df.empty and "income_df" in fin:
        story.append(_revenue_chart(fin["income_df"], stock_name))
        story.append(Paragraph("图：近5年营业收入与归母净利润（亿元）", st["caption"]))

    fin_rows = [
        ["指标", "数值"],
        ["近1年营收增速", f"{fin.get('rev_growth','N/A')}%"],
        ["近1年净利润增速", f"{fin.get('profit_growth','N/A')}%"],
        ["最新ROE", f"{fin.get('roe','N/A')}%"],
        ["毛利率", f"{fin.get('gross_margin','N/A')}%"],
        ["资产负债率", f"{fin.get('debt_ratio','N/A')}%"],
    ]
    story.append(_tbl(fin_rows, col_widths=[6*cm, 6*cm]))
    story.append(Spacer(1, 0.3*cm))

    # ── 五、财务健康度 ──
    story.append(Paragraph("五、财务健康度", st["h1"]))
    debt = fin.get("debt_ratio", None)
    roe  = fin.get("roe", None)
    health_notes = []
    if roe is not None:
        health_notes.append(f"ROE {roe}%：{'优秀（>15%）' if roe > 15 else '一般（≤15%）'}")
    if debt is not None:
        health_notes.append(f"资产负债率 {debt}%：{'偏高（>70%）' if debt > 70 else '健康（≤70%）'}")
    for note in health_notes:
        story.append(Paragraph(f"• {note}", st["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 五点五、现金流质量 ──
    if cf_quality and cf_quality.get("rows"):
        story.append(Paragraph("5.5 现金流质量", st["h2"]))
        story.append(Paragraph(
            f"综合评价：{cf_quality.get('quality_label','N/A')}（CFO/净利润比率越高，利润含金量越高）",
            st["body"]
        ))
        cf_rows = [["年份", "经营现金流（亿）", "归母净利润（亿）", "CFO/净利润"]]
        for r in cf_quality["rows"]:
            cf_rows.append([
                r["year"],
                str(r["cfo_bn"]) if r["cfo_bn"] is not None else "N/A",
                str(r["net_bn"]) if r["net_bn"] is not None else "N/A",
                str(r["ratio"]) if r["ratio"] is not None else "N/A",
            ])
        story.append(_tbl(cf_rows, col_widths=[2.5*cm, 4*cm, 4*cm, 3.5*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 五点八、资产负债质量 ──
    if bs_quality and bs_quality.get("rows"):
        story.append(Paragraph("5.8 资产负债质量", st["h2"]))
        cr = bs_quality.get("current_ratio")
        qr = bs_quality.get("quick_ratio")
        if cr is not None:
            story.append(Paragraph(
                f"流动比率：{cr}（{'健康（≥2）' if cr >= 2 else '偏低（<2）'}）　速动比率：{qr if qr is not None else 'N/A'}（{'健康（≥1）' if (qr or 0) >= 1 else '偏低（<1）'}）",
                st["body"]
            ))
        bs_rows = [["年份", "资产负债率", "应收账款占比"]]
        for r in bs_quality["rows"]:
            bs_rows.append([
                r["year"],
                f"{r['debt_ratio']}%" if r["debt_ratio"] is not None else "N/A",
                f"{r['ar_ratio']}%" if r["ar_ratio"] is not None else "N/A",
            ])
        story.append(_tbl(bs_rows, col_widths=[3*cm, 4.5*cm, 4.5*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 六、同行龙头与估值锚对比 ──
    if industry_comp:
        story.append(Paragraph("六、同行龙头与估值锚对比", st["h1"]))
        story.append(Paragraph(
            f"行业：{industry_comp.get('industry','')}　同类股票数：{industry_comp.get('peer_count',0)} 只",
            st["body"]
        ))
        ic_rows = [["指标", "当前值", "行业25%分位", "行业中位数", "行业75%分位", "行业分位"]]
        pe_now = val.get("pe_ttm")
        pb_now = val.get("pb")
        ic_rows.append([
            "PE(TTM)",
            str(pe_now) if pe_now else "N/A",
            str(industry_comp.get("industry_pe_25", "N/A")),
            str(industry_comp.get("industry_pe_median", "N/A")),
            str(industry_comp.get("industry_pe_75", "N/A")),
            f"{industry_comp.get('pe_percentile','N/A')}%" if industry_comp.get("pe_percentile") is not None else "N/A",
        ])
        ic_rows.append([
            "PB",
            str(pb_now) if pb_now else "N/A",
            str(industry_comp.get("industry_pb_25", "N/A")),
            str(industry_comp.get("industry_pb_median", "N/A")),
            str(industry_comp.get("industry_pb_75", "N/A")),
            f"{industry_comp.get('pb_percentile','N/A')}%" if industry_comp.get("pb_percentile") is not None else "N/A",
        ])
        story.append(_tbl(ic_rows, col_widths=[2*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm]))
        story.append(Spacer(1, 0.3*cm))

        if peer_view:
            story.extend(md_to_story(render_peer_brief(peer_view), st["body"], table_builder=_tbl))
            story.append(Spacer(1, 0.2*cm))

            target = peer_view.get("target", {})
            peer_rows = [["角色", "名称", "市值(亿)", "PE", "PB", "ROE", "毛利率", "净利增速"]]
            peer_rows.append([
                target.get("role", "目标公司"),
                target.get("name", stock_name),
                f"{target.get('mv_bn'):.1f}" if target.get("mv_bn") is not None else "N/A",
                f"{target.get('pe_ttm'):.1f}" if target.get("pe_ttm") is not None else "N/A",
                f"{target.get('pb'):.1f}" if target.get("pb") is not None else "N/A",
                f"{target.get('roe'):.1f}%" if target.get("roe") is not None else "N/A",
                f"{target.get('gross_margin'):.1f}%" if target.get("gross_margin") is not None else "N/A",
                f"{target.get('profit_growth'):.1f}%" if target.get("profit_growth") is not None else "N/A",
            ])
            for p in peer_view.get("peer_rows", [])[:6]:
                peer_rows.append([
                    p.get("role", "直接可比"),
                    p.get("name", p.get("ts_code", "")),
                    f"{p.get('mv_bn'):.1f}" if p.get("mv_bn") is not None else "N/A",
                    f"{p.get('pe_ttm'):.1f}" if p.get("pe_ttm") is not None else "N/A",
                    f"{p.get('pb'):.1f}" if p.get("pb") is not None else "N/A",
                    f"{p.get('roe'):.1f}%" if p.get("roe") is not None else "N/A",
                    f"{p.get('gross_margin'):.1f}%" if p.get("gross_margin") is not None else "N/A",
                    f"{p.get('profit_growth'):.1f}%" if p.get("profit_growth") is not None else "N/A",
                ])
            story.append(_tbl(peer_rows, col_widths=[2.5*cm, 3*cm, 2*cm, 1.6*cm, 1.6*cm, 1.8*cm, 1.8*cm, 2*cm]))
            story.append(Paragraph(
                "说明：龙头参照用于判断行业定价锚和质量上限；若目标公司估值显著低于龙头，需要进一步判断是低估机会，还是商业模式、成长性、治理或现金流折价。",
                st["caption"]
            ))
            story.append(Spacer(1, 0.3*cm))

    # ── 七、三情景分析 ──
    if scenario and scenario.get("cur_price"):
        story.append(Paragraph("七、三情景分析（未来1年）", st["h1"]))
        story.append(Paragraph(
            "基于历史 PE 区间与净利润增速区间，测算三种情景下的目标价格区间，仅供参考。",
            st["caption"]
        ))
        sc_rows = [
            ["情景", "假设增速", "对应PE", "目标价（元）", "较当前涨跌幅"],
            [
                "乐观（Bull）",
                f"{scenario.get('g_bull','N/A')}%",
                str(scenario.get("pe_bull", "N/A")),
                str(scenario.get("price_bull", "N/A")),
                f"{scenario.get('upside_bull','N/A')}%",
            ],
            [
                "中性（Base）",
                f"{scenario.get('g_base','N/A')}%",
                str(scenario.get("pe_base", "N/A")),
                str(scenario.get("price_base", "N/A")),
                f"{scenario.get('upside_base','N/A')}%",
            ],
            [
                "谨慎（Bear）",
                f"{scenario.get('g_bear','N/A')}%",
                str(scenario.get("pe_bear", "N/A")),
                str(scenario.get("price_bear", "N/A")),
                f"{scenario.get('upside_bear','N/A')}%",
            ],
        ]
        story.append(_tbl(sc_rows, col_widths=[3*cm, 2.5*cm, 2.5*cm, 3*cm, 3*cm]))
        story.append(Paragraph(f"当前股价：{scenario.get('cur_price','N/A')} 元", st["body"]))
        story.append(Spacer(1, 0.3*cm))

    # ── 八、主营业务构成 ──
    if mainbz_product is not None and not mainbz_product.empty:
        story.append(PageBreak())
        story.append(Paragraph("八、主营业务构成", st["h1"]))
        # 取最新一期
        mbz = mainbz_product.copy()
        mbz["end_date"] = mbz["end_date"].astype(str)
        latest_period = mbz["end_date"].max()
        mbz_latest = mbz[mbz["end_date"] == latest_period].copy()
        mbz_latest["bz_sales"] = pd.to_numeric(mbz_latest.get("bz_sales", 0), errors="coerce")
        mbz_latest["bz_profit"] = pd.to_numeric(mbz_latest.get("bz_profit", 0), errors="coerce")
        total_sales = mbz_latest["bz_sales"].sum()

        story.append(Paragraph(f"报告期：{latest_period[:4]}年{latest_period[4:6]}月", st["body"]))
        mbz_rows = [["产品/业务", "营业收入（亿）", "营收占比", "毛利（亿）"]]
        for _, row in mbz_latest.sort_values("bz_sales", ascending=False).head(8).iterrows():
            sales = row["bz_sales"]
            pct = round(sales / total_sales * 100, 1) if total_sales > 0 else 0
            mbz_rows.append([
                str(row.get("bz_item", ""))[:12],
                str(round(sales / 1e8, 2)),
                f"{pct}%",
                str(round(row["bz_profit"] / 1e8, 2)) if pd.notna(row["bz_profit"]) else "N/A",
            ])
        story.append(_tbl(mbz_rows, col_widths=[5*cm, 3.5*cm, 3*cm, 3.5*cm]))

        # 按地区
        if mainbz_region is not None and not mainbz_region.empty:
            story.append(Spacer(1, 0.3*cm))
            story.append(Paragraph("按地区分布", st["h2"]))
            mbr = mainbz_region.copy()
            mbr["end_date"] = mbr["end_date"].astype(str)
            mbr_latest = mbr[mbr["end_date"] == mbr["end_date"].max()].copy()
            mbr_latest["bz_sales"] = pd.to_numeric(mbr_latest.get("bz_sales", 0), errors="coerce")
            total_r = mbr_latest["bz_sales"].sum()
            mbr_rows = [["地区", "营业收入（亿）", "营收占比"]]
            for _, row in mbr_latest.sort_values("bz_sales", ascending=False).head(6).iterrows():
                sales = row["bz_sales"]
                pct = round(sales / total_r * 100, 1) if total_r > 0 else 0
                mbr_rows.append([str(row.get("bz_item", ""))[:10], str(round(sales / 1e8, 2)), f"{pct}%"])
            story.append(_tbl(mbr_rows, col_widths=[5*cm, 4.5*cm, 4.5*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 九、资金面分析 ──
    story.append(Paragraph("九、资金面综合分析", st["h1"]))
    fund_items = []

    # 主力资金
    if moneyflow_df is not None and not moneyflow_df.empty:
        mf = moneyflow_df.sort_values("trade_date", ascending=False).copy()
        mf["net_mf_amount"] = pd.to_numeric(mf.get("net_mf_amount", np.nan), errors="coerce")
        net_5d = mf["net_mf_amount"].head(5).sum()
        net_20d_val = mf["net_mf_amount"].head(20).sum()
        fund_items.append(f"近5日主力净流入：{round(net_5d, 0)}万元")
        fund_items.append(f"近20日主力净流入：{round(net_20d_val, 0)}万元")
        # 判断趋势
        if net_20d_val > 0:
            fund_items.append("→ 主力资金近期呈净流入态势，机构看好情绪偏强")
        else:
            fund_items.append("→ 主力资金近期呈净流出态势，机构观望情绪偏浓")

    # 融资融券
    if margin_df is not None and not margin_df.empty:
        mg = margin_df.sort_values("trade_date").copy()
        mg["rzye"] = pd.to_numeric(mg["rzye"], errors="coerce")
        latest_rz = mg["rzye"].iloc[-1]
        fund_items.append(f"最新融资余额：{round(latest_rz/1e8, 2)}亿元，趋势：{margin_trend}")

    # 股东人数
    if holder_num_df is not None and not holder_num_df.empty:
        fund_items.append(f"股东人数变化：{holder_change}")
        hn = holder_num_df.sort_values("end_date").copy()
        hn["holder_num"] = pd.to_numeric(hn["holder_num"], errors="coerce")
        if len(hn) >= 3:
            last3 = hn.tail(3)["holder_num"].tolist()
            if last3[-1] < last3[-2] < last3[-3]:
                fund_items.append("→ 连续减少，筹码集中度提升（通常是积极信号）")
            elif last3[-1] > last3[-2] > last3[-3]:
                fund_items.append("→ 连续增加，筹码分散（需关注机构减持可能）")

    # 大宗交易
    if block_trade_df is not None and not block_trade_df.empty:
        fund_items.append(f"近3月大宗交易：{block_trade_info}")

    # 股权质押
    fund_items.append(f"股权质押率：{pledge_ratio}%{'（偏高，需关注爆仓风险）' if isinstance(pledge_ratio, (int, float)) and pledge_ratio > 10 else ''}")

    for item in fund_items:
        story.append(Paragraph(f"• {item}", st["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 十、分红历史 ──
    if dividend_df is not None and not dividend_df.empty:
        story.append(Paragraph("十、分红送股历史", st["h1"]))
        div = dividend_df.sort_values("end_date", ascending=False).copy()
        div["cash_div_tax"] = pd.to_numeric(div.get("cash_div_tax", 0), errors="coerce")
        div_rows = [["报告期", "方案进度", "每股现金红利（元/税前）", "送股比例", "公告日"]]
        for _, row in div.head(8).iterrows():
            div_rows.append([
                str(row.get("end_date", ""))[:4] + "年" + str(row.get("end_date", ""))[4:6] + "月",
                str(row.get("div_proc", "")),
                str(round(row["cash_div_tax"], 4)) if pd.notna(row["cash_div_tax"]) and row["cash_div_tax"] > 0 else "—",
                str(row.get("stk_div", 0)) if row.get("stk_div") else "—",
                str(row.get("ann_date", ""))[:8],
            ])
        story.append(_tbl(div_rows, col_widths=[3*cm, 2.5*cm, 4*cm, 2.5*cm, 3*cm]))

        # 分红率评价
        total_div = div["cash_div_tax"].sum()
        if total_div > 0:
            story.append(Paragraph(
                f"近年累计每股分红（税前）：{round(total_div, 2)} 元。该公司分红{'积极' if total_div > 5 else '稳定' if total_div > 1 else '偏少'}。",
                st["body"]
            ))
        story.append(Spacer(1, 0.3*cm))

    # ── 十一、业绩预告 ──
    story.append(Paragraph("十一、业绩预告", st["h1"]))
    if forecast_df is not None and not forecast_df.empty:
        from datetime import datetime, timedelta
        one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        fc = forecast_df.sort_values("ann_date", ascending=False).copy()
        fc = fc[fc["ann_date"].astype(str) >= one_year_ago]
        if not fc.empty:
            fc_rows = [["公告日", "报告期", "预告类型", "变动下限%", "变动上限%"]]
            for _, row in fc.head(5).iterrows():
                fc_rows.append([
                    str(row.get("ann_date", ""))[:8],
                    str(row.get("end_date", ""))[:6],
                    str(row.get("type", "")),
                    str(row.get("p_change_min", "N/A")),
                    str(row.get("p_change_max", "N/A")),
                ])
            story.append(_tbl(fc_rows, col_widths=[3*cm, 2.5*cm, 3*cm, 3*cm, 3*cm]))
        else:
            story.append(Paragraph("暂无近1年内的业绩预告数据。", st["body"]))
    else:
        story.append(Paragraph("暂无业绩预告数据。", st["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 十二、概念板块与题材 ──
    if concepts_df is not None and not concepts_df.empty:
        story.append(Paragraph("十二、概念板块与投资题材", st["h1"]))
        concept_names = concepts_df["concept_name"].tolist() if "concept_name" in concepts_df.columns else []
        story.append(Paragraph(f"该股票涉及 {len(concept_names)} 个概念板块：", st["body"]))
        story.append(Paragraph("、".join(concept_names[:15]), st["body"]))
        story.append(Spacer(1, 0.3*cm))

    # ── 十三、股东结构 ──
    story.append(Paragraph("十三、股东结构", st["h1"]))
    if holders_df is not None and not holders_df.empty:
        holders_df2 = holders_df.sort_values("end_date", ascending=False)
        latest_date = holders_df2["end_date"].iloc[0]
        latest_holders = holders_df2[holders_df2["end_date"] == latest_date].head(10)
        h_rows = [["股东名称", "持股数量（万股）", "持股比例"]]
        for _, row in latest_holders.iterrows():
            h_rows.append([
                str(row.get("holder_name", ""))[:16],
                str(round(float(row.get("hold_amount", 0)) / 1e4, 2)) if row.get("hold_amount") else "N/A",
                f"{row.get('hold_ratio','')}%",
            ])
        story.append(_tbl(h_rows, col_widths=[7*cm, 4.5*cm, 3.5*cm]))
    else:
        story.append(Paragraph("股东数据暂不可用", st["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 十四、互联网研究（公司近期事件/行业/机构观点） ──
    if web_research and web_research.get("sections"):
        story.append(PageBreak())
        story.append(Paragraph("十四、公司研究与行业动态", st["h1"]))
        source_name = web_research.get("source", "公开搜索")
        source_count = len(web_research.get("sources", []))
        if web_research.get("fallback_used"):
            caption = f"Tavily 未配置或不可用，本页使用 AI 降级整理（来源：{source_name}），仅供参考，请以官方公告为准。"
        elif web_research.get("structured_without_llm"):
            caption = f"以下为基于 Tavily 来源的结构化情报摘要（来源：{source_name}，参考来源{source_count}条）；日期未标明的信息仅作背景，请以官方公告为准。"
        else:
            caption = f"以下信息由 Tavily 公开搜索结果整理（来源：{source_name}，参考来源{source_count}条），仅供参考，请以官方公告为准。"
        story.append(Paragraph(
            caption,
            st["caption"],
        ))
        story.append(Spacer(1, 0.2*cm))

        sections = web_research["sections"]
        section_titles = {
            "recent_events": "近期重大事件",
            "industry_dynamics": "行业动态与竞争格局",
            "analyst_views": "机构观点汇总",
            "risk_factors": "潜在风险因素",
            "catalysts": "关键催化剂",
        }
        for key, title in section_titles.items():
            content = sections.get(key, "")
            if content:
                story.append(Paragraph(title, st["h2"]))
                content = _sanitize_research_text(content)
                story.extend(md_to_story(content, st["body"], table_builder=_tbl))
                story.append(Spacer(1, 0.2*cm))

    # ── 十五、行业与公司动态 ──
    if not (web_research and web_research.get("sections")):
        story.append(Paragraph("十五、行业与公司动态", st["h1"]))
        story.append(Paragraph(
            f"以下优先通过搜索服务获取{stock_name}所在行业近期动态；搜索不可用时才降级为AI整理，仅供参考。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.2*cm))
        try:
            _industry = basic.get("industry", "未知") if basic else "未知"
            industry_news = get_industry_news(stock_name, d["ts_code"], _industry, "A股")
            story.extend(md_to_story(industry_news, st["body"], table_builder=_tbl))
        except Exception as e:
            story.append(Paragraph(f"行业动态获取失败：{e}", st["body"]))
        story.append(Spacer(1, 0.3*cm))

    # ── 十六、审计与合规 ──
    if audit_df is not None and not audit_df.empty:
        story.append(Paragraph("十六、审计与合规", st["h1"]))
        aud_rows = [["报告期", "审计意见", "审计机构", "签字会计师"]]
        for _, row in audit_df.head(3).iterrows():
            aud_rows.append([
                str(row.get("end_date", ""))[:4] + "年",
                str(row.get("audit_result", "")),
                str(row.get("audit_agency", ""))[:12],
                str(row.get("audit_sign", ""))[:12],
            ])
        story.append(_tbl(aud_rows, col_widths=[2.5*cm, 4*cm, 4*cm, 4*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 风险提示 ──
    story.append(PageBreak())
    story.append(Paragraph("免责声明与风险提示", st["h1"]))
    risks = [
        "本报告基于历史公开数据，不代表未来表现，市场有风险，投资需谨慎。",
        "股票投资存在本金损失风险，请根据自身风险承受能力做出投资决策。",
        "财务数据来源于公开披露的上市公司报告，如有差异以公司公告为准。",
        "AI分析建议基于量化模型，可能存在偏差，不构成任何投资建议或承诺。",
        "互联网研究信息可能存在时效性和准确性问题，请以官方公告和权威渠道为准。",
        "本报告仅供个人学习研究使用，不得作为任何投资决策的唯一依据。",
    ]
    for r in risks:
        story.append(Paragraph(f"• {r}", st["body"]))

    doc.build(
        story,
        onFirstPage=lambda canvas, doc_obj: draw_report_footer(canvas, doc_obj, "stock"),
        onLaterPages=lambda canvas, doc_obj: draw_report_footer(canvas, doc_obj, "stock"),
    )
    print(f"\n✓ PDF 报告已生成：{output_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python3 step4_generate_stock_pdf.py <data.json> <output.pdf>")
        sys.exit(1)
    create_stock_pdf(sys.argv[1], sys.argv[2])
