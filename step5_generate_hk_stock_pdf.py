#!/usr/bin/env python3
"""
步骤5：基于真实数据生成港股深度分析 PDF 报告（含 Minima AI 买卖建议）
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

from ai_analysis import get_investment_advice, get_industry_news
from config import md_to_rl, md_to_story

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

# ── 样式 ──────────────────────────────────────────────────────────────────────

def _styles():
    def s(name, **kw):
        return ParagraphStyle(name, fontName=CN_FONT, **kw)
    return {
        "title":   s("T",  fontSize=22, leading=28, alignment=TA_CENTER, spaceAfter=6),
        "subtitle":s("ST", fontSize=13, leading=18, alignment=TA_CENTER, spaceAfter=4, textColor=colors.HexColor("#555555")),
        "h1":      s("H1", fontSize=14, leading=20, spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#1a3c6e")),
        "h2":      s("H2", fontSize=12, leading=16, spaceBefore=8,  spaceAfter=4, textColor=colors.HexColor("#2c5f9e")),
        "body":    s("B",  fontSize=10, leading=15, spaceAfter=4, alignment=TA_JUSTIFY),
        "caption": s("C",  fontSize=8,  leading=12, textColor=colors.grey, alignment=TA_CENTER),
    }

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _tbl(data, col_widths=None, header_bg="#1a3c6e"):
    style = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor(header_bg)),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, -1), CN_FONT),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4fa")]),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(style)
    return t


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

    # 基本信息（港股 hk_basic 返回的是单层 dict）
    if "basic" in raw:
        if isinstance(raw["basic"], dict) and "fields" not in raw["basic"]:
            d["basic"] = raw["basic"]
        elif isinstance(raw["basic"], dict) and "fields" in raw["basic"] and raw["basic"].get("items"):
            d["basic"] = dict(zip(raw["basic"]["fields"], raw["basic"]["items"][0]))
        else:
            d["basic"] = raw["basic"]

    # 日线行情
    if "daily" in raw and raw["daily"].get("items"):
        d["daily"] = pd.DataFrame(raw["daily"]["items"], columns=raw["daily"]["fields"])

    # 财务指标
    if "fina_indicator" in raw and raw["fina_indicator"].get("items"):
        d["fina_indicator"] = pd.DataFrame(raw["fina_indicator"]["items"], columns=raw["fina_indicator"]["fields"])

    # 利润表
    if "income" in raw and raw["income"].get("items"):
        d["income"] = pd.DataFrame(raw["income"]["items"], columns=raw["income"]["fields"])

    # 现金流量表
    if "cashflow" in raw and raw["cashflow"].get("items"):
        d["cashflow"] = pd.DataFrame(raw["cashflow"]["items"], columns=raw["cashflow"]["fields"])

    # 南向资金持仓
    if "hold" in raw and raw["hold"].get("items"):
        d["hold"] = pd.DataFrame(raw["hold"]["items"], columns=raw["hold"]["fields"])

    # 增强数据
    if "balancesheet" in raw and raw["balancesheet"].get("items"):
        d["balancesheet"] = pd.DataFrame(raw["balancesheet"]["items"], columns=raw["balancesheet"]["fields"])

    if "concepts" in raw and raw["concepts"].get("items"):
        d["concepts"] = pd.DataFrame(raw["concepts"]["items"], columns=raw["concepts"]["fields"])

    if "macro_news" in raw and raw["macro_news"].get("items"):
        d["macro_news"] = pd.DataFrame(raw["macro_news"]["items"], columns=raw["macro_news"]["fields"])

    if "web_research" in raw:
        d["web_research"] = raw["web_research"]

    return d

# ── 计算函数 ──────────────────────────────────────────────────────────────────

def _latest_valuation(fina_df, daily_df):
    """从财务指标和日线行情中提取最新估值"""
    result = {}
    if fina_df is not None and not fina_df.empty:
        df = fina_df.copy()
        if "end_date" in df.columns:
            df = df.sort_values("end_date")
        latest = df.iloc[-1]
        for col in ("pe_ttm", "pb", "roe_avg", "debt_to_assets", "grossprofit_margin"):
            val = latest.get(col)
            if val is not None:
                try:
                    result[col] = round(float(val), 2)
                except (TypeError, ValueError):
                    pass

    if daily_df is not None and not daily_df.empty:
        df = daily_df.sort_values("trade_date").copy()
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        if not df["close"].dropna().empty:
            result["cur_price"] = round(float(df["close"].iloc[-1]), 3)
            # 计算PE历史分位（如果有pe_ttm列）
            if "pe_ttm" in fina_df.columns if fina_df is not None else False:
                pe_series = pd.to_numeric(fina_df["pe_ttm"], errors="coerce").dropna()
                pe_series = pe_series[pe_series > 0]
                if len(pe_series) > 5 and result.get("pe_ttm"):
                    result["pe_percentile"] = round(
                        (pe_series < result["pe_ttm"]).mean() * 100, 1
                    )

    return result


def _fin_summary(income_df, fina_df):
    """利润表 & 财务指标摘要"""
    result = {}
    if income_df is not None and not income_df.empty:
        df = income_df.copy()
        if "end_date" in df.columns:
            df["end_date"] = df["end_date"].astype(str)
            df = df.sort_values("end_date")

        # 尝试提取营收和净利润字段（港股字段可能不同）
        rev_col = None
        for c in ("total_revenue", "revenue", "total_revenue_2"):
            if c in df.columns:
                rev_col = c
                break
        profit_col = None
        for c in ("n_income_attr_p", "net_income", "n_income"):
            if c in df.columns:
                profit_col = c
                break

        if rev_col:
            df[rev_col] = pd.to_numeric(df[rev_col], errors="coerce")
        if profit_col:
            df[profit_col] = pd.to_numeric(df[profit_col], errors="coerce")

        if rev_col and len(df) >= 2:
            rev_now = df[rev_col].iloc[-1]
            rev_prev = df[rev_col].iloc[-2]
            if rev_prev and rev_prev != 0 and pd.notna(rev_now):
                result["rev_growth"] = round((rev_now / rev_prev - 1) * 100, 1)

        if profit_col and len(df) >= 2:
            net_now = df[profit_col].iloc[-1]
            net_prev = df[profit_col].iloc[-2]
            if net_prev and net_prev != 0 and pd.notna(net_now):
                result["profit_growth"] = round((net_now / net_prev - 1) * 100, 1)

        result["income_df"] = df
        result["rev_col"] = rev_col
        result["profit_col"] = profit_col

    if fina_df is not None and not fina_df.empty:
        df2 = fina_df.copy()
        if "end_date" in df2.columns:
            df2 = df2.sort_values("end_date")
        latest = df2.iloc[-1]
        for col, key in [("roe_avg", "roe"), ("grossprofit_margin", "gross_margin"), ("debt_to_assets", "debt_ratio")]:
            val = latest.get(col)
            if val is not None:
                try:
                    result[key] = round(float(val), 2)
                except (TypeError, ValueError):
                    pass

    return result


def _cashflow_quality(cashflow_df, income_df):
    """现金流质量分析"""
    result = {}
    if cashflow_df is None or cashflow_df.empty:
        return result

    cf = cashflow_df.copy()
    if "end_date" in cf.columns:
        cf["end_date"] = cf["end_date"].astype(str)
        cf = cf.sort_values("end_date")

    # 港股现金流字段
    cfo_col = None
    for c in ("n_cashflow_act", "net_operate_cf", "c_fr_oper_act"):
        if c in cf.columns:
            cfo_col = c
            break

    if not cfo_col:
        return result

    cf[cfo_col] = pd.to_numeric(cf[cfo_col], errors="coerce")

    # 营收用于计算 OCF/Sales
    rev_col = None
    if income_df is not None and not income_df.empty:
        for c in ("total_revenue", "revenue", "total_revenue_2"):
            if c in income_df.columns:
                rev_col = c
                break

    rows = []
    for _, row in cf.tail(5).iterrows():
        cfo = row[cfo_col]
        rows.append({
            "period": str(row.get("end_date", ""))[:10],
            "cfo": round(float(cfo) / 1e6, 2) if pd.notna(cfo) else None,
        })

    result["rows"] = rows

    # OCF/Sales 比率
    if rev_col and income_df is not None:
        inc = income_df.copy()
        if "end_date" in inc.columns:
            inc["end_date"] = inc["end_date"].astype(str)
            inc = inc.sort_values("end_date")
        inc[rev_col] = pd.to_numeric(inc[rev_col], errors="coerce")
        if not cf.empty and not inc.empty:
            latest_cfo = cf[cfo_col].iloc[-1]
            latest_rev = inc[rev_col].iloc[-1]
            if pd.notna(latest_cfo) and pd.notna(latest_rev) and latest_rev != 0:
                result["ocf_sales"] = round(float(latest_cfo) / float(latest_rev), 3)

    return result


def _southbound_analysis(hold_df):
    """南向资金持仓分析"""
    result = {}
    if hold_df is None or hold_df.empty:
        return result

    df = hold_df.copy()
    if "trade_date" in df.columns:
        df = df.sort_values("trade_date")

    # 尝试提取持仓比例字段
    ratio_col = None
    for c in ("ratio", "vol_ratio", "hold_ratio"):
        if c in df.columns:
            ratio_col = c
            break

    vol_col = None
    for c in ("vol", "hold_vol", "amount"):
        if c in df.columns:
            vol_col = c
            break

    if ratio_col:
        df[ratio_col] = pd.to_numeric(df[ratio_col], errors="coerce")
        latest_ratio = df[ratio_col].iloc[-1] if not df[ratio_col].dropna().empty else None
        result["latest_ratio"] = round(float(latest_ratio), 2) if pd.notna(latest_ratio) else None

        # 趋势：对比30天前
        if len(df) >= 30:
            prev_ratio = df[ratio_col].iloc[-30]
            if pd.notna(prev_ratio) and pd.notna(latest_ratio):
                diff = latest_ratio - prev_ratio
                if diff > 0.5:
                    result["trend"] = "增持"
                elif diff < -0.5:
                    result["trend"] = "减持"
                else:
                    result["trend"] = "持平"
            else:
                result["trend"] = "未知"
        else:
            result["trend"] = "数据不足"

    if vol_col:
        df[vol_col] = pd.to_numeric(df[vol_col], errors="coerce")

    # 近期数据用于表格展示
    recent = df.tail(10)
    table_rows = []
    for _, row in recent.iterrows():
        table_rows.append({
            "date": str(row.get("trade_date", ""))[:10],
            "ratio": round(float(row[ratio_col]), 2) if ratio_col and pd.notna(row.get(ratio_col)) else None,
            "vol": round(float(row[vol_col]) / 1e4, 2) if vol_col and pd.notna(row.get(vol_col)) else None,
        })
    result["table_rows"] = table_rows

    return result


def _ma_position(daily_df):
    """均线位置判断"""
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

def _price_chart(daily_df, stock_name):
    """港股股价走势图"""
    df = daily_df.sort_values("trade_date").copy().tail(250)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["trade_date"], df["close"], color="#1a3c6e", linewidth=1.5, label=stock_name)

    # 添加均线
    if len(df) >= 20:
        ma20 = df["close"].rolling(20).mean()
        ax.plot(df["trade_date"], ma20, color="#e67e22", linewidth=0.8, linestyle="--", label="MA20")
    if len(df) >= 60:
        ma60 = df["close"].rolling(60).mean()
        ax.plot(df["trade_date"], ma60, color="#888888", linewidth=0.8, linestyle=":", label="MA60")

    ax.set_title(f"{stock_name} 近1年股价走势（港元）", fontsize=12)
    ax.set_xlabel("日期")
    ax.set_ylabel("收盘价（HKD）")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    fig.tight_layout()
    return _chart_to_image(fig)


def _southbound_chart(hold_df, stock_name):
    """南向资金持仓比例走势图"""
    if hold_df is None or hold_df.empty:
        return None

    df = hold_df.copy()
    if "trade_date" not in df.columns:
        return None

    df = df.sort_values("trade_date")
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    ratio_col = None
    for c in ("ratio", "vol_ratio", "hold_ratio"):
        if c in df.columns:
            ratio_col = c
            break

    if not ratio_col:
        return None

    df[ratio_col] = pd.to_numeric(df[ratio_col], errors="coerce")

    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.fill_between(df["trade_date"], df[ratio_col], alpha=0.3, color="#1a3c6e")
    ax.plot(df["trade_date"], df[ratio_col], color="#1a3c6e", linewidth=1.2)
    ax.set_title(f"{stock_name} 南向资金持仓比例走势", fontsize=12)
    ax.set_xlabel("日期")
    ax.set_ylabel("持仓比例（%）")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _chart_to_image(fig)


def _revenue_chart(income_df, stock_name, rev_col, profit_col):
    """营收与净利润柱状图"""
    if income_df is None or income_df.empty:
        return None

    df = income_df.copy()
    if "end_date" in df.columns:
        df["end_date"] = df["end_date"].astype(str)
        df = df.sort_values("end_date").tail(5)

    if not rev_col and not profit_col:
        return None

    fig, ax = plt.subplots(figsize=(10, 4))
    x = range(len(df))
    w = 0.35

    if rev_col and rev_col in df.columns:
        df[rev_col] = pd.to_numeric(df[rev_col], errors="coerce") / 1e6  # 百万港元
        ax.bar([i - w/2 for i in x], df[rev_col], width=w, label="营业收入（百万）", color="#1a3c6e", alpha=0.8)

    if profit_col and profit_col in df.columns:
        df[profit_col] = pd.to_numeric(df[profit_col], errors="coerce") / 1e6
        ax.bar([i + w/2 for i in x], df[profit_col], width=w, label="净利润（百万）", color="#2c5f9e", alpha=0.6)

    labels = [d[:4] if len(d) >= 4 else d for d in df["end_date"]] if "end_date" in df.columns else list(x)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_title(f"{stock_name} 营收与净利润趋势", fontsize=12)
    ax.set_ylabel("金额（百万港元）")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    return _chart_to_image(fig)

# ── 主函数 ────────────────────────────────────────────────────────────────────

def create_hk_stock_pdf(data_file: str, output_path: str) -> None:
    print("=" * 80)
    print("生成港股深度分析 PDF 报告")
    print("=" * 80)

    d = _load(data_file)
    st = _styles()
    basic = d.get("basic", {})
    stock_name = basic.get("name", d["ts_code"])

    daily_df = d.get("daily")
    fina_df = d.get("fina_indicator")
    income_df = d.get("income")
    cashflow_df = d.get("cashflow")
    hold_df = d.get("hold")
    balance_df = d.get("balancesheet")
    concepts_df = d.get("concepts")
    macro_news_df = d.get("macro_news")
    web_research = d.get("web_research")

    val = _latest_valuation(fina_df, daily_df)
    fin = _fin_summary(income_df, fina_df)
    ma_pos = _ma_position(daily_df)
    cf_quality = _cashflow_quality(cashflow_df, income_df)
    sb_analysis = _southbound_analysis(hold_df)

    # AI 买卖建议
    advice_text = get_investment_advice("hk_stock", {
        "name": stock_name,
        "ts_code": d["ts_code"],
        "pe_ttm": val.get("pe_ttm", "N/A"),
        "pb_ttm": val.get("pb", "N/A"),
        "roe_avg": val.get("roe_avg", "N/A"),
        "debt_ratio": fin.get("debt_ratio", "N/A"),
        "rev_growth": fin.get("rev_growth", "N/A"),
        "profit_growth": fin.get("profit_growth", "N/A"),
        "gross_margin": fin.get("gross_margin", "N/A"),
        "ocf_sales": cf_quality.get("ocf_sales", "N/A"),
        "southbound_ratio": sb_analysis.get("latest_ratio", "N/A"),
        "southbound_trend": sb_analysis.get("trend", "未知"),
        "ma_position": ma_pos,
    })

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    story = []

    # ── 封面 ──
    story += [
        Spacer(1, 3*cm),
        Paragraph(stock_name, st["title"]),
        Paragraph("港股深度分析报告", st["subtitle"]),
        Spacer(1, 0.5*cm),
        Paragraph(f"股票代码：{d['ts_code']}　　市场：香港联交所", st["body"]),
        Paragraph(f"报告日期：{datetime.now().strftime('%Y年%m月%d日')}　　数据来源：小德法 Tushare API", st["body"]),
        PageBreak(),
    ]

    # ── 一、公司概况 ──
    story.append(Paragraph("一、公司概况", st["h1"]))
    info_rows = [
        ["股票名称", stock_name, "股票代码", d["ts_code"]],
        ["全称", basic.get("fullname", basic.get("name", "")), "上市日期", basic.get("list_date", "N/A")],
        ["当前PE(TTM)", str(val.get("pe_ttm", "N/A")), "当前PB", str(val.get("pb", "N/A"))],
        ["最新ROE", f"{val.get('roe_avg', 'N/A')}%", "当前股价", f"{val.get('cur_price', 'N/A')} HKD"],
    ]
    story.append(_tbl(info_rows, col_widths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm]))
    story.append(Spacer(1, 0.3*cm))

    # ── 二、投资建议（AI） ──
    story.append(Paragraph("二、投资建议（AI分析）", st["h1"]))
    story.append(Paragraph(
        "以下建议由 MiniMax-M2.7 模型基于量化数据自动生成，仅供参考，不构成投资依据。",
        st["caption"]
    ))
    story.append(Spacer(1, 0.2*cm))
    story.extend(md_to_story(advice_text, st["body"], table_builder=_tbl))
    story.append(Spacer(1, 0.3*cm))

    # ── 三、股价与均线 ──
    story.append(Paragraph("三、股价走势", st["h1"]))
    if daily_df is not None and not daily_df.empty:
        story.append(_price_chart(daily_df, stock_name))
        story.append(Paragraph("图：近1年股价走势（含MA20/MA60均线）", st["caption"]))
        story.append(Paragraph(f"当前均线位置：{ma_pos}", st["body"]))
    else:
        story.append(Paragraph("日线数据暂不可用", st["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 四、业绩分析 ──
    story.append(Paragraph("四、业绩分析", st["h1"]))
    rev_col = fin.get("rev_col")
    profit_col = fin.get("profit_col")
    if income_df is not None and not income_df.empty:
        chart = _revenue_chart(fin.get("income_df", income_df), stock_name, rev_col, profit_col)
        if chart:
            story.append(chart)
            story.append(Paragraph("图：营业收入与净利润趋势（百万港元）", st["caption"]))

    fin_rows = [
        ["指标", "数值"],
        ["近1年营收增速", f"{fin.get('rev_growth', 'N/A')}%"],
        ["近1年净利润增速", f"{fin.get('profit_growth', 'N/A')}%"],
        ["最新ROE（平均）", f"{fin.get('roe', 'N/A')}%"],
        ["毛利率", f"{fin.get('gross_margin', 'N/A')}%"],
        ["资产负债率", f"{fin.get('debt_ratio', 'N/A')}%"],
    ]
    story.append(_tbl(fin_rows, col_widths=[6*cm, 6*cm]))
    story.append(Spacer(1, 0.3*cm))

    # ── 五、财务健康度 ──
    story.append(Paragraph("五、财务健康度", st["h1"]))
    roe_val = fin.get("roe")
    debt_val = fin.get("debt_ratio")
    gm_val = fin.get("gross_margin")
    health_notes = []
    if roe_val is not None:
        health_notes.append(f"ROE(平均) {roe_val}%：{'优秀（>15%）' if roe_val > 15 else '良好（10-15%）' if roe_val > 10 else '一般（<10%）'}")
    if debt_val is not None:
        health_notes.append(f"资产负债率 {debt_val}%：{'偏高（>70%）' if debt_val > 70 else '健康（≤70%）'}")
    if gm_val is not None:
        health_notes.append(f"毛利率 {gm_val}%：{'优秀（>40%）' if gm_val > 40 else '良好（20-40%）' if gm_val > 20 else '一般（<20%）'}")
    for note in health_notes:
        story.append(Paragraph(f"• {note}", st["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 六、现金流质量 ──
    if cf_quality:
        story.append(Paragraph("六、现金流质量", st["h1"]))
        ocf_sales = cf_quality.get("ocf_sales")
        if ocf_sales is not None:
            label = "健康（>0.15）" if ocf_sales > 0.15 else "偏弱（≤0.15）"
            story.append(Paragraph(f"经营现金流/营收比率：{ocf_sales}（{label}）", st["body"]))

        if cf_quality.get("rows"):
            cf_rows = [["报告期", "经营现金流（百万）"]]
            for r in cf_quality["rows"]:
                cf_rows.append([
                    r["period"],
                    str(r["cfo"]) if r["cfo"] is not None else "N/A",
                ])
            story.append(_tbl(cf_rows, col_widths=[5*cm, 5*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 七、南向资金持仓分析 ──
    story.append(Paragraph("七、南向资金持仓分析", st["h1"]))
    if sb_analysis and sb_analysis.get("latest_ratio") is not None:
        story.append(Paragraph(
            f"最新南向资金持仓比例：{sb_analysis['latest_ratio']}%　　近期趋势：{sb_analysis.get('trend', '未知')}",
            st["body"]
        ))

        # 南向资金走势图
        sb_chart = _southbound_chart(hold_df, stock_name)
        if sb_chart:
            story.append(sb_chart)
            story.append(Paragraph("图：南向资金持仓比例走势", st["caption"]))

        # 近期持仓数据表
        if sb_analysis.get("table_rows"):
            sb_rows = [["日期", "持仓比例（%）", "持仓量（万股）"]]
            for r in sb_analysis["table_rows"][-5:]:  # 只展示最近5条
                sb_rows.append([
                    r["date"],
                    str(r["ratio"]) if r["ratio"] is not None else "N/A",
                    str(r["vol"]) if r["vol"] is not None else "N/A",
                ])
            story.append(_tbl(sb_rows, col_widths=[4*cm, 4*cm, 4*cm]))
    else:
        story.append(Paragraph("该股票可能不在港股通范围内，南向资金数据不可用。", st["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 八、财务指标趋势 ──
    if fina_df is not None and not fina_df.empty:
        story.append(PageBreak())
        story.append(Paragraph("八、核心财务指标趋势", st["h1"]))
        fi = fina_df.copy()
        if "end_date" in fi.columns:
            fi["end_date"] = fi["end_date"].astype(str)
            fi = fi.sort_values("end_date")

        # 提取关键指标趋势表
        trend_rows = [["报告期", "PE(TTM)", "PB(TTM)", "ROE(%)", "营收增速(%)", "净利润增速(%)"]]
        for _, row in fi.tail(6).iterrows():
            trend_rows.append([
                str(row.get("end_date", ""))[:6],
                str(round(float(row.get("pe_ttm", 0)), 1)) if row.get("pe_ttm") else "N/A",
                str(round(float(row.get("pb_ttm", 0)), 2)) if row.get("pb_ttm") else "N/A",
                str(round(float(row.get("roe_avg", 0)), 2)) if row.get("roe_avg") else "N/A",
                str(round(float(row.get("operate_income_yoy", 0)), 1)) if row.get("operate_income_yoy") else "N/A",
                str(round(float(row.get("holder_profit_yoy", 0)), 1)) if row.get("holder_profit_yoy") else "N/A",
            ])
        story.append(_tbl(trend_rows, col_widths=[2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm]))

        # 分红信息（从 fina_indicator 中提取）
        dps_col = "dps_hkd" if "dps_hkd" in fi.columns else None
        if dps_col:
            story.append(Spacer(1, 0.3*cm))
            story.append(Paragraph("分红历史（每股派息 HKD）", st["h2"]))
            div_rows = [["报告期", "每股派息(HKD)", "股息率(%)"]]
            for _, row in fi.tail(5).iterrows():
                dps = row.get(dps_col)
                div_rate = row.get("dividend_rate")
                div_rows.append([
                    str(row.get("end_date", ""))[:6],
                    str(round(float(dps), 4)) if dps else "—",
                    str(round(float(div_rate) * 100, 2)) if div_rate else "N/A",
                ])
            story.append(_tbl(div_rows, col_widths=[4*cm, 4*cm, 4*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 九、互联网研究（公司近期事件/行业/机构观点） ──
    if web_research and web_research.get("sections"):
        story.append(PageBreak())
        story.append(Paragraph("九、公司研究与行业动态", st["h1"]))
        source_name = web_research.get("source", "公开搜索")
        source_count = len(web_research.get("sources", []))
        if web_research.get("fallback_used"):
            caption = f"Tavily 未配置或不可用，本页使用 AI 降级整理（来源：{source_name}），仅供参考，请以官方公告为准。"
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
                story.extend(md_to_story(content, st["body"], table_builder=_tbl))
                story.append(Spacer(1, 0.2*cm))

    # ── 十、行业与公司动态 ──
    if not (web_research and web_research.get("sections")):
        story.append(Paragraph("十、行业与公司动态", st["h1"]))
        story.append(Paragraph(
            f"以下优先通过搜索服务获取{stock_name}所在行业近期动态；搜索不可用时才降级为AI整理，仅供参考。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.2*cm))
        try:
            _industry = basic.get("industry", basic.get("name", "未知"))
            industry_news = get_industry_news(stock_name, d["ts_code"], _industry, "港股")
            story.extend(md_to_story(industry_news, st["body"], table_builder=_tbl))
        except Exception as e:
            story.append(Paragraph(f"行业动态获取失败：{e}", st["body"]))
        story.append(Spacer(1, 0.3*cm))

    # ── 风险提示 ──
    story.append(PageBreak())
    story.append(Paragraph("免责声明与风险提示", st["h1"]))
    risks = [
        "汇率风险：港股以港元计价，人民币/港元汇率波动可能影响实际收益。",
        "流动性风险：部分港股交易量较低，大额交易可能面临滑点。",
        "市场风险：港股受国际资金流动影响较大，波动率可能高于A股。",
        "信息不对称：港股信息披露规则与A股不同，需关注公司公告。",
        "本报告基于历史公开数据，不代表未来表现，市场有风险，投资需谨慎。",
        "AI分析建议基于量化模型，可能存在偏差，不构成任何投资建议或承诺。",
        "互联网研究信息可能存在时效性和准确性问题，请以官方公告和权威渠道为准。",
    ]
    for r in risks:
        story.append(Paragraph(f"• {r}", st["body"]))

    doc.build(story)
    print(f"\n✓ 港股 PDF 报告已生成：{output_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python3 step5_generate_hk_stock_pdf.py <data.json> <output.pdf>")
        sys.exit(1)
    create_hk_stock_pdf(sys.argv[1], sys.argv[2])
