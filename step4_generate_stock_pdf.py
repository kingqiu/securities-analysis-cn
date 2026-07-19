#!/usr/bin/env python3
"""
步骤4：基于真实数据生成股票深度分析 PDF 报告（含 Minima AI 研究解读）
"""

import json
import os
import re
import tempfile
from datetime import datetime, timedelta

os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".matplotlib-cache"))

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


# ── 可读性增强：信号灯 + 术语释义 ─────────────────────────────────────

SIGNAL_THRESHOLDS = {
    "roe":       [(15, "●", "#1e8449", "优秀(>15%)"), (8, "●", "#BA7517", "一般(8-15%)"), (0, "●", "#c0392b", "偏弱(<8%)")],
    "pe_pct":    [(30, "●", "#1e8449", "偏低(<30%)"), (70, "●", "#BA7517", "适中(30-70%)"), (100, "●", "#c0392b", "偏高(>70%)")],
    "pe_pct_3y": [(30, "●", "#1e8449", "偏低(<30%)"), (70, "●", "#BA7517", "适中(30-70%)"), (100, "●", "#c0392b", "偏高(>70%)")],
    "debt":      [(40, "●", "#1e8449", "健康(<40%)"), (70, "●", "#BA7517", "一般(40-70%)"), (100, "●", "#c0392b", "偏高(>70%)")],
    "cfo_ratio": [(1.0, "●", "#1e8449", "扎实(≥1.0，利润含金量高)"), (0.5, "●", "#BA7517", "一般(0.5-1.0)"), (0, "●", "#c0392b", "偏弱(<0.5，利润质量存疑)")],
    "gross_margin": [(50, "●", "#1e8449", "高毛利(≥50%)"), (35, "●", "#BA7517", "中等(35-50%)"), (0, "●", "#c0392b", "低毛利(<35%)")],
    "net_margin":   [(15, "●", "#1e8449", "较高(≥15%)"), (8, "●", "#BA7517", "中等(8-15%)"), (0, "●", "#c0392b", "偏低(<8%)")],
    "rev_growth":   [(15, "●", "#1e8449", "强劲(>15%)"), (0, "●", "#BA7517", "微增/持平(0-15%)"), (-100, "●", "#c0392b", "负增长(<0%)")],
    "profit_growth": [(15, "●", "#1e8449", "强劲(>15%)"), (0, "●", "#BA7517", "微增/持平(0-15%)"), (-100, "●", "#c0392b", "负增长(<0%)")],
    "current_ratio": [(2.0, "●", "#1e8449", "健康(≥2)"), (1.0, "●", "#BA7517", "一般(1-2)"), (0, "●", "#c0392b", "偏低(<1)")],
    "pledge":       [(5, "●", "#1e8449", "低风险(<5%)"), (10, "●", "#BA7517", "关注(5-10%)"), (100, "●", "#c0392b", "偏高(>10%)")],
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
    for boundary, emoji, color, label in thresholds:
        if v >= boundary:
            return (emoji, color, label)
    # 未匹配（负值兜底）
    return ("●", "#c0392b", "偏弱")


def _signal_text(metric, value, suffix=""):
    """生成带信号灯的 HTML 片段：值 + emoji + 参考区间。用于 Paragraph。"""
    emoji, color, label = _signal(metric, value)
    try:
        v = float(value) if value is not None and str(value) != "N/A" else None
        val_str = f"{v:.1f}{suffix}" if v is not None else str(value)
    except (TypeError, ValueError):
        val_str = str(value)
    if not emoji:
        return val_str
    return f'<font color="{color}">{emoji}</font> {val_str} <font color="{color}">{label}</font>'


GLOSSARY = {
    "PE(TTM)": "市盈率（股价÷最近12个月每股收益），衡量估值高低",
    "PB": "市净率（股价÷每股净资产），<1可能低估但也可能资产质量差",
    "ROE": "净资产收益率（净利润÷净资产），每1元股东权益赚多少利润",
    "CFO/净利比": "经营现金流÷净利润，>1表示利润含金量高（赚到的钱真的到手了）",
    "权益乘数": "总资产÷净资产，即杠杆倍数。2倍表示1元自有资金撬动2元总资产",
    "CAGR": "复合年均增长率，假设每年匀速增长的情况下的平均增速",
    "TTM": "滚动12个月（Trailing Twelve Months），取最近4个季度合计",
    "毛利率": "（营业收入-营业成本）÷营业收入，衡量产品赚钱能力",
    "净利率": "归母净利润÷营业收入，衡量最终能留下多少利润",
    "总资产周转率": "营业收入÷总资产，衡量资产使用效率",
    "资产负债率": "总负债÷总资产，衡量公司借了多少钱",
    "流动比率": "流动资产÷流动负债，≥2表示短期偿债能力强",
    "速动比率": "（流动资产-存货）÷流动负债，≥1表示短期偿债能力强",
    "PE分位": "当前PE在历史数据中的相对位置，30%表示比70%的历史时间都便宜",
    "隐含增速": "反向DCF推算：当前股价隐含了市场对未来增长速度的预期",
    "黑天鹅": "极低概率但冲击巨大的事件，如突发政策、行业崩塌",
}


def _gloss(term):
    """返回术语释义字符串，无释义则原样返回。"""
    return GLOSSARY.get(term, term)


def _tldr(val, fin, cf_quality, business_engine, bear_case, industry_cycle, stock_name):
    """可读性改进1：一页纸摘要 TL;DR —— 5-6条带信号灯的大白话结论。
    返回 list[str]，每条为带 HTML font color 的信号灯 + 参考区间 + 大白话。"""
    items = []
    # 1. 估值
    pe_ttm = val.get("pe_ttm")
    pe_pct = val.get("pe_pct_3y") or val.get("pe_percentile")
    e, c, l = _signal("pe_pct", pe_pct)
    items.append(
        f"1. <b>估值：</b>PE(TTM) {_gloss('PE(TTM)')} 当前 {pe_ttm or 'N/A'}，近3年分位 {pe_pct or 'N/A'}% "
        f'<font color="{c}">{e} {l}</font>'
    )
    # 2. 盈利能力
    roe = fin.get("roe")
    e, c, l = _signal("roe", roe)
    items.append(
        f'2. <b>盈利能力：</b>ROE {_gloss("ROE")} 当前 {roe or "N/A"}% '
        f'<font color="{c}">{e} {l}</font>'
    )
    # 3. 现金流质量
    cfo_ratio = cf_quality.get("latest_ratio") if cf_quality else None
    e, c, l = _signal("cfo_ratio", cfo_ratio)
    items.append(
        f'3. <b>现金流：</b>CFO/净利润 {_gloss("CFO/净利比")} 当前 {cfo_ratio or "N/A"} '
        f'<font color="{c}">{e} {l}</font>'
    )
    # 4. 商业模式
    if business_engine:
        gm = business_engine.get("gross_margin")
        e, c, l = _signal("gross_margin", gm)
        items.append(
            f'4. <b>赚钱方式：</b>毛利率 {_gloss("毛利率")} {gm or "N/A"}% '
            f'<font color="{c}">{e} {l}</font>'
            f" → {business_engine.get('driver', 'N/A')}"
        )
    # 5. 行业周期
    if industry_cycle:
        items.append(
            f'5. <b>行业周期：</b>{industry_cycle.get("stage", "数据不足，暂无判断")}'
        )
    # 6. 空方风险
    if bear_case:
        bear_count = len(bear_case.get("bear", []))
        if bear_count >= 3:
            items.append(f'6. <b>看空信号：</b>检出 <font color="#c0392b">{bear_count}条</font> 量化看空理由，需重点关注。')
        elif bear_count >= 1:
            items.append(f'6. <b>看空信号：</b>检出 <font color="#BA7517">{bear_count}条</font> 看空因素，值得跟踪。')
        else:
            items.append(f'6. <b>看空信号：</b>未检出显著量化空方信号，但仍需关注系统性风险。')
    # 综合一句话
    pe_pct_v = pe_pct
    roe_v = roe
    cfo_v = cfo_ratio
    summary_parts = []
    if pe_pct_v is not None:
        summary_parts.append("估值" + ("不算贵" if pe_pct_v < 40 else "偏贵" if pe_pct_v > 70 else "适中"))
    if roe_v is not None:
        summary_parts.append("盈利" + ("偏弱" if roe_v < 8 else "较强" if roe_v > 15 else "一般"))
    if cfo_v is not None:
        summary_parts.append("利润含金量" + ("扎实" if cfo_v >= 1 else "一般" if cfo_v >= 0.5 else "存疑"))
    if summary_parts:
        items.append(f'<b>一句话：</b>{stock_name}当前{", ".join(summary_parts)}，需跟踪业绩与行业变化。')
    return items


def _plain_summary(val, fin, cf_quality, bear_case, stock_name):
    """可读性改进5：封面 notes 大白话化 —— 根据各指标信号灯拼接一条大白话综合判断。"""
    pe_pct = val.get("pe_pct_3y") or val.get("pe_percentile")
    roe = fin.get("roe")
    cfo = cf_quality.get("latest_ratio") if cf_quality else None
    rev_g = fin.get("rev_growth")
    profit_g = fin.get("profit_growth")
    bear_count = len(bear_case.get("bear", [])) if bear_case else 0

    parts = []
    if pe_pct is not None:
        if pe_pct < 30:
            parts.append("估值偏低，安全边际较好")
        elif pe_pct < 70:
            parts.append("估值适中")
        else:
            parts.append("估值偏高，需警惕预期透支")
    if roe is not None:
        if roe > 15:
            parts.append("盈利能力较强")
        elif roe > 8:
            parts.append("盈利能力中等")
        else:
            parts.append("盈利能力偏弱")
    if cfo is not None:
        if cfo >= 1:
            parts.append("利润含金量扎实")
        elif cfo >= 0.5:
            parts.append("利润含金量一般")
        else:
            parts.append("利润含金量存疑")
    if rev_g is not None or profit_g is not None:
        if (rev_g or 0) > 0 and (profit_g or 0) > 0:
            parts.append("收入与利润仍在增长")
        elif (profit_g or 0) <= 0:
            parts.append("利润增长承压")

    summary = "、".join(parts) if parts else "核心指标需进一步跟踪验证"
    if bear_count >= 3:
        summary += "。有多个看空信号需重点关注"
    elif bear_count >= 1:
        summary += "。存在部分看空因素值得跟踪"

    return f"{stock_name}当前{summary}。"


def _chapter_intro(chapter_key):
    """可读性改进4：章节白话导语 —— 每个章节开头一句"这节回答什么问题"。"""
    INTROS = {
        "公司概况": "这节回答：这家公司是做什么的？在行业里处于什么位置？",
        "情景区间": "这节回答：基于当前估值和业绩，股价大概在什么区间？用于观察估值与风险状态，不构成买卖建议。",
        "股价估值": "这节回答：这家公司现在贵不贵？和历史相比处于什么水平？",
        "业绩分析": "这节回答：这家公司赚钱能力怎么样？收入和利润在增长还是下滑？",
        "财务健康": "这节回答：公司财务状况是否健康？有没有负债过高、现金流差等隐患？",
        "现金流": "这节回答：赚到的利润真的变成现金了吗？利润含金量如何？",
        "杜邦": "这节回答：ROE靠什么驱动？是产品利润率高、还是资产效率好、还是借了杠杆？",
        "资产负债": "这节回答：公司偿债能力怎么样？会不会还不上短期债务？",
        "同行对比": "这节回答：和同行业其他公司比，这家公司估值是偏高还是偏低？盈利能力处于什么水平？",
        "三情景": "这节回答：如果未来一年乐观/中性/悲观，股价大概在什么范围？",
        "资金面": "这节回答：近期聪明钱在买还是卖？市场热度怎么样？",
        "分红": "这节回答：这家公司给股东分红吗？分红慷慨还是吝啬？",
        "业绩预告": "这节回答：公司自己预测下期业绩大概怎样？是增长还是下滑？",
        "股东结构": "这节回答：谁在持有这家公司？大股东稳定还是频繁变动？",
        "赚钱机制": "这节回答：这家公司到底靠什么赚钱？是产品溢价、还是规模效率、还是高周转走量？",
        "行业周期": "这节回答：行业现在处于什么阶段？是扩张期还是出清期？对公司意味着什么？",
        "空方逻辑": "这节回答：有哪些看空的理由？可能出什么黑天鹅？（对抗确认偏误，强制列出）",
        "反向DCF": "这节回答：不预测股价，而是反推：当前市值定价了多少未来增长？预期是否透支？",
        "监控清单": "这节回答：未来需要跟踪哪些关键事件和数据？什么信号会强化或证伪当前判断？",
        "数据来源": "这节回答：这份报告的数据从哪来的？取数时间是什么？可信度如何？",
    }
    return INTROS.get(chapter_key, "")


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

    # 杜邦分解（由 run_report 计算后写入）
    if "dupont" in raw and isinstance(raw["dupont"], dict):
        d["dupont"] = raw["dupont"]

    if "realtime_quote" in raw and isinstance(raw["realtime_quote"], dict):
        d["realtime_quote"] = raw["realtime_quote"]

    # 公司画像（总资产/净资产，用于赚钱机制拆解）
    if "profile" in raw and raw["profile"].get("items"):
        d["profile"] = pd.DataFrame(raw["profile"]["items"], columns=raw["profile"]["fields"])

    # 数据来源清单（P1-11）
    if "data_sources" in raw and raw["data_sources"]:
        d["data_sources"] = raw["data_sources"]

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
    # P0-4：分档分位——近1年(250交易日)、近3年(750交易日)
    cur_pe = latest["pe_ttm"]
    pe_1y = df["pe_ttm"].tail(250).dropna()
    pe_pct_1y = round((pe_1y < cur_pe).mean() * 100, 1) if len(pe_1y) > 10 else None
    pe_3y = df["pe_ttm"].tail(750).dropna()
    pe_pct_3y = round((pe_3y < cur_pe).mean() * 100, 1) if len(pe_3y) > 10 else None
    return {
        "pe_ttm": round(latest["pe_ttm"], 2) if pd.notna(latest["pe_ttm"]) else None,
        "pb":     round(latest["pb"], 2)     if pd.notna(latest["pb"])     else None,
        "mv_bn":  round(latest["total_mv"] / 1e8, 1) if pd.notna(latest.get("total_mv")) else None,
        "pe_percentile": pe_pct,
        "pe_pct_1y": pe_pct_1y,
        "pe_pct_3y": pe_pct_3y,
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


def _reverse_dcf(val, income_df, years=5, r=0.09, g=0.03):
    """反向 DCF：反推当前市值隐含的未来净利增速，判断透支程度。
    val: _latest_valuation 结果（含 mv_bn 市值亿元）
    income_df: 含 end_date/total_revenue/n_income_attr_p
    返回 dict: implied_growth, hist_cagr, verdict, assumptions
    """
    mv_bn = val.get("mv_bn")  # 市值（亿元）
    if not mv_bn or income_df is None or income_df.empty:
        return {}
    df = income_df.copy()
    df["end_date"] = df["end_date"].astype(str)
    df = df[df["end_date"].str.endswith("1231")].sort_values("end_date")
    df["n_income_attr_p"] = pd.to_numeric(df["n_income_attr_p"], errors="coerce")
    df = df.dropna(subset=["n_income_attr_p"])
    if len(df) < 2:
        return {}
    np0 = float(df["n_income_attr_p"].iloc[-1])      # 最新年报归母净利（元）
    np0_bn = np0 / 1e8                                # 亿元
    if np0_bn <= 0:
        return {}
    # 历史 CAGR（最多取近5期）
    n_hist = min(len(df), 5)
    np_hist = float(df["n_income_attr_p"].iloc[-n_hist])
    if np_hist and np_hist > 0 and n_hist > 1:
        hist_cagr = (np0 / np_hist) ** (1.0 / (n_hist - 1)) - 1
    else:
        hist_cagr = None
    # 反推隐含增速 x：市值 = np0_bn * Σ(1+x)^t/(1+r)^t + 终值
    def pv(x):
        s = 0.0
        for t in range(1, years + 1):
            s += (1 + x) ** t / (1 + r) ** t
        terminal = (1 + x) ** years * (1 + g) / (r - g) / (1 + r) ** years
        s += terminal
        return np0_bn * s
    lo, hi = -0.10, 0.50
    # 二分法求 x 使 pv(x) ≈ mv_bn
    if pv(lo) > mv_bn or pv(hi) < mv_bn:
        implied = None
    else:
        for _ in range(80):
            mid = (lo + hi) / 2
            if pv(mid) < mv_bn:
                lo = mid
            else:
                hi = mid
        implied = (lo + hi) / 2
    # 判断
    if implied is None:
        verdict = "当前市值超出合理增速区间，可能存在显著透支或数据异常。"
    elif hist_cagr is not None:
        if implied > hist_cagr * 1.5 and implied > 0.20:
            verdict = "隐含预期显著高于历史增速，市场定价偏乐观，需警惕预期落空。"
        elif implied > hist_cagr:
            verdict = "隐含预期略高于历史增速，定价偏积极但尚在可解释区间。"
        elif implied > 0:
            verdict = "隐含预期低于或接近历史增速，定价相对克制。"
        else:
            verdict = "隐含预期为负或接近零，市场定价偏悲观。"
    else:
        verdict = "历史数据不足以计算 CAGR，仅给出隐含增速。"
    return {
        "implied_growth": round(implied * 100, 1) if implied is not None else "N/A",
        "hist_cagr": round(hist_cagr * 100, 1) if hist_cagr is not None else "N/A",
        "np0_bn": round(np0_bn, 2),
        "mv_bn": round(mv_bn, 1),
        "verdict": verdict,
        "assumptions": f"折现率{r*100:.0f}%，永续增长率{g*100:.0f}%，显式预测{years}年",
    }


def _monitor_checklist(fin, val, cf_quality, stock_name):
    """规则化生成未来验证节点监控清单：强化逻辑事件 + 证伪逻辑数据 + 关键节点。"""
    strengthen, falsify = [], []
    roe = fin.get("roe")
    pe_pct = val.get("pe_percentile")
    rev_g = fin.get("rev_growth")
    profit_g = fin.get("profit_growth")
    gross = fin.get("gross_margin")
    cfo_ratio = cf_quality.get("latest_ratio")

    # 强化逻辑事件
    if rev_g is not None:
        strengthen.append(f"下期营收增速维持在 {round(rev_g*0.8,1)}% 以上，成长逻辑延续。")
    if roe is not None:
        strengthen.append(f"ROE 维持在 {roe}% 以上，盈利能力未恶化。")
    if cfo_ratio is not None and cfo_ratio >= 1.0:
        strengthen.append("经营现金流/净利持续 ≥ 1.0，利润含金量验证。")
    if pe_pct is not None and pe_pct < 30:
        strengthen.append("估值分位回落至 30% 以下，安全边际改善。")

    # 证伪逻辑数据
    if roe is not None:
        falsify.append(f"ROE 跌破 {round(roe*0.7,1)}%，盈利能力实质性下滑。")
    if cfo_ratio is not None:
        falsify.append(f"经营现金流/净利持续低于 {round(cfo_ratio*0.6,2)}，利润质量恶化。")
    if rev_g is not None and rev_g > 0:
        falsify.append(f"营收增速转负或连续两季低于 {round(rev_g*0.5,1)}%，成长证伪。")
    if profit_g is not None:
        falsify.append(f"归母净利连续两季负增长，业绩拐点向下。")
    if pe_pct is not None and pe_pct > 70:
        falsify.append("估值分位升至 80% 以上，透支过度。")

    # 关键节点
    milestones = [
        "下一份定期报告（季报/半年报/年报）披露日：验证营收与利润趋势。",
        "下一次业绩预告/快报窗口：确认业绩是否延续或拐头。",
        "行业重大政策/事件窗口：跟踪供需与竞争格局变化。",
    ]
    if not strengthen:
        strengthen = ["业绩与估值指标出现正向改善信号时强化逻辑。"]
    if not falsify:
        falsify = ["核心财务指标出现持续恶化时复核逻辑。"]
    return {
        "strengthen": strengthen[:5],
        "falsify": falsify[:5],
        "milestones": milestones,
    }


def _business_engine(income_df, fina_df, profile, stock_name):
    """P1-8 赚钱机制/商业模式拆解：用毛利率、净利率、资产周转识别盈利模式与赚钱驱动。
    毛利率/净利率/周转为可验证事实；盈利模式归类为规则化判断。"""
    result = {}
    if income_df is None or income_df.empty or profile is None:
        return result
    inc = income_df.copy()
    inc["end_date"] = inc["end_date"].astype(str)
    inc = inc[inc["end_date"].str.endswith("1231")].sort_values("end_date")
    for col in ("total_revenue", "oper_cost", "n_income_attr_p"):
        if col in inc.columns:
            inc[col] = pd.to_numeric(inc.get(col, np.nan), errors="coerce")
    if inc.empty:
        return result
    latest = inc.iloc[-1]
    rev = latest.get("total_revenue")
    cost = latest.get("oper_cost")
    net = latest.get("n_income_attr_p")
    if rev and rev > 0:
        gross = (rev - cost) / rev if (cost is not None and pd.notna(cost)) else None
        net_m = net / rev if (net is not None and pd.notna(net)) else None
        result["revenue_bn"] = round(rev / 1e8, 1)
        result["gross_margin"] = round(gross * 100, 1) if gross is not None else None
        result["net_margin"] = round(net_m * 100, 1) if net_m is not None else None
    # 资产效率（事实）
    try:
        prof = profile.iloc[0]
        ta = float(prof.get("total_assets")) if prof.get("total_assets") is not None else None
        na = float(prof.get("net_assets")) if prof.get("net_assets") is not None else None
    except (AttributeError, KeyError, TypeError, ValueError):
        ta = na = None
    if ta and ta > 0 and rev:
        result["asset_turnover"] = round(rev / ta, 3)
    if na and na > 0 and rev:
        result["equity_turnover"] = round(rev / na, 3)
    # 规则化归类（判断）
    gm = result.get("gross_margin")
    nm = result.get("net_margin")
    if gm is not None and nm is not None:
        if gm >= 60:
            model = "高毛利模式：盈利核心来自产品溢价、品牌、专利或稀缺资源壁垒，对销量波动耐受度较高，但需警惕单品依赖与价格管控（如集采/招标）。"
        elif gm >= 35:
            model = "中等毛利模式：盈利来自规模制造与成本管控，竞争优势取决于产能效率、良率与供应链话语权。"
        else:
            model = "低毛利模式：盈利高度依赖销量与周转，价格或需求下行时利润弹性大、抗风险能力弱。"
        if nm >= 15:
            quality = "净利率处于较高水平，费用管控或产品附加值较好。"
        elif nm >= 8:
            quality = "净利率处于中等水平。"
        else:
            quality = "净利率偏低，需关注费用率与成本端的挤压。"
        if gm >= 50:
            driver = "高毛利驱动：盈利核心靠‘卖得贵’（产品溢价/专利壁垒/品牌），风险在价格管控与单品依赖。"
        elif gm >= 35:
            driver = "中等毛利驱动：盈利靠‘做得精’（制造效率与规模），风险在产能利用率与成本波动。"
        else:
            driver = "低毛利驱动：盈利靠‘走量’（高周转），风险在价格与需求波动。"
        result["model"] = model
        result["quality"] = quality
        result["driver"] = driver
    return result


def _industry_cycle(industry_comp, industry_peers, val, fin, stock_name, industry):
    """P1-7 行业周期与格局判断：基于同业截面估值与增长信号的轻量规则化推断。
    缺行业历史PE序列与产能/Capex数据，仅为方向性参考（判断）。"""
    result = {}
    if not industry_comp:
        return result
    peer_med_pe = industry_comp.get("industry_pe_median")
    target_pe_pct = industry_comp.get("pe_percentile")
    target_pe = val.get("pe_ttm")
    rev_g = fin.get("rev_growth")
    profit_g = fin.get("profit_growth")
    if peer_med_pe:
        if peer_med_pe < 20:
            result["heat"] = "估值整体偏低（行业PE中位数<20）"
        elif peer_med_pe > 40:
            result["heat"] = "估值整体偏高（行业PE中位数>40）"
        else:
            result["heat"] = "估值处于中性区间（行业PE中位数20-40）"
        result["peer_med_pe"] = peer_med_pe
    if target_pe_pct is not None:
        if target_pe_pct < 30:
            result["position"] = "目标公司估值处于行业低位（<30%分位），相对同业折价"
        elif target_pe_pct > 70:
            result["position"] = "目标公司估值处于行业高位（>70%分位），相对同业溢价"
        else:
            result["position"] = "目标公司估值接近行业中枢"
        result["target_pe_pct"] = target_pe_pct
    if rev_g is not None and profit_g is not None:
        if rev_g > 15 and profit_g > 15:
            result["growth_signal"] = "公司增长强劲（营收/净利增速>15%）"
        elif rev_g > 0 and profit_g > 0:
            result["growth_signal"] = "公司稳健增长（营收/净利正增长）"
        elif rev_g <= 0 or profit_g <= 0:
            result["growth_signal"] = "公司增长承压（营收或净利增速转弱）"
    # 周期阶段推断（判断）
    heat_hi = (peer_med_pe or 0) > 40
    heat_lo = (peer_med_pe or 99) < 20
    pos_hi = (target_pe_pct or 0) > 70
    pos_lo = (target_pe_pct or 99) < 30
    strong = (rev_g or 0) > 15 and (profit_g or 0) > 15
    weak = (rev_g or 0) <= 0 or (profit_g or 0) <= 0
    if heat_hi and strong:
        stage = "扩张期：行业估值偏热且龙头增长强劲，需防预期透支。"
    elif heat_lo and weak:
        stage = "出清/低谷期：行业估值低位且增长承压，关注格局改善与拐点信号。"
    elif pos_lo and (rev_g or 0) > 0:
        stage = "价值修复期：目标相对同业折价且仍增长，关注折价是否被错误定价。"
    elif pos_hi:
        stage = "高预期期：目标相对同业溢价，需更强基本面支撑。"
    else:
        stage = "成熟期/分化期：行业估值中性，个股表现取决于自身α与结构差异。"
    result["stage"] = stage
    return result


def _bear_case(val, fin, cf_quality, stock_summary, moneyflow_df, reverse_dcf, web_research, industry):
    """P1-6 空方逻辑与黑天鹅推演：规则化识别量化看空信号 + 检索偏空关键词 + 行业化黑天鹅场景。"""
    bear = []
    facts = []
    pe_pct = val.get("pe_percentile")
    pe_pct_3y = val.get("pe_pct_3y")
    debt = fin.get("debt_ratio")
    rev_g = fin.get("rev_growth")
    profit_g = fin.get("profit_growth")
    cfo = cf_quality.get("latest_ratio") if cf_quality else None
    net_mf = stock_summary.get("net_mf_20d")
    pledge = stock_summary.get("pledge_ratio")
    impl = reverse_dcf.get("implied_growth") if reverse_dcf else None
    hist = reverse_dcf.get("hist_cagr") if reverse_dcf else None

    # 量化看空信号
    if (pe_pct is not None and pe_pct > 70) or (pe_pct_3y is not None and pe_pct_3y > 80):
        bear.append("估值分位偏高（PE历史分位>70% / 近3年>80%），安全边际不足，回撤风险大。")
    if debt is not None and debt > 60:
        bear.append(f"资产负债率偏高（{debt}%），财务杠杆与利息负担压制抗风险能力。")
    if cfo is not None and cfo < 0.8:
        bear.append(f"经营现金流/净利仅 {cfo}，利润含金量偏低，盈利质量需复核。")
    if isinstance(net_mf, (int, float)) and net_mf < 0:
        bear.append("近20日主力资金净流出，短期筹码面偏弱。")
    if isinstance(pledge, (int, float)) and pledge > 10:
        bear.append(f"股权质押率 {pledge}%，存在股价下跌触发平仓的连锁风险。")
    if (rev_g is not None and rev_g < 0) or (profit_g is not None and profit_g < 0):
        bear.append("营收或净利已现负增长，成长逻辑面临证伪。")
    if impl not in (None, "N/A") and hist not in (None, "N/A"):
        try:
            if float(impl) > float(hist) * 1.5 and float(impl) > 0.2:
                bear.append(f"反向DCF显示市场隐含增速 {impl}% 远高于历史CAGR {hist}%，预期透支明显。")
        except (TypeError, ValueError):
            pass

    # 检索偏空关键词
    if web_research and web_research.get("sections"):
        text = " ".join(str(v) for v in web_research["sections"].values())
        keywords = ["减持", "下滑", "亏损", "诉讼", "监管", "问询", "终止", "承压", "降价", "集采", "风险", "回调", "利空", "警示", "暂停"]
        hits = [k for k in keywords if k in text]
        if hits:
            facts.append("互联网检索中出现的偏空关键词：" + "、".join(hits)
                         + "（详见「十四、公司研究与行业动态」原文，需结合公告核实）。")

    if not bear:
        bear = ["未检出显著量化空方信号；但任何公司均存在宏观、行业与政策层面的系统性风险，仍需持续跟踪。"]

    # 行业化黑天鹅场景
    swan_map = {
        "医药": ["集采/招标降价导致核心品种价格与利润大幅下滑",
                 "重磅在研管线临床失败或进度不及预期",
                 "医保控费与专利悬崖冲击存量品种"],
        "医药制造": ["集采/招标降价导致核心品种价格与利润大幅下滑",
                     "重磅在研管线临床失败或进度不及预期",
                     "医保控费与专利悬崖冲击存量品种"],
        "玻璃纤维": ["行业产能过剩下价格战，玻纤价格持续下行",
                     "下游风电/汽车/电子需求走弱",
                     "贸易摩擦与海外关税壁垒"],
        "半导体": ["行业下行周期叠加库存减值",
                   "大客户订单流失或技术路线切换",
                   "设备/材料出口管制升级"],
        "default": ["行业政策与监管骤变",
                    "技术路线被颠覆，核心产品被替代",
                    "大客户/大供应商集中带来的经营中断",
                    "宏观系统性风险与流动性收紧"],
    }
    swans = swan_map.get(industry, swan_map["default"])
    return {"bear": bear, "facts": facts, "swans": swans}


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

    # P0 增强：反向DCF / 监控清单 / 杜邦（杜邦数据由 run_report 提供）
    reverse_dcf = _reverse_dcf(val, income_df)
    monitor = _monitor_checklist(fin, val, cf_quality, stock_name)
    dupont = d.get("dupont")

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

    # P1 增强：赚钱机制 / 行业周期 / 空方逻辑（均为规则化，零 token）
    business_engine = _business_engine(income_df, fina_df, d.get("profile"), stock_name)
    industry_cycle = _industry_cycle(industry_comp, d.get("industry_peers"), val, fin, stock_name, industry)
    bear_case = _bear_case(val, fin, cf_quality, stock_summary, moneyflow_df, reverse_dcf, web_research, industry)
    data_sources = d.get("data_sources", [])

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
            ["核心结论", f"【判断】{_plain_summary(val, fin, cf_quality, bear_case, stock_name)}"],
            ["关注变量", f"【判断】需重点跟踪：估值分位变化、营收与利润增速趋势、现金流是否持续改善、主力资金流向与行业景气信号。"],
            ["主要风险", f"【判断】主要风险来自行业竞争、政策变化、估值中枢下移及市场系统性波动；具体看空理由详见「二十一、空方逻辑与风险推演」。"],
        ],
    )

    add_report_reading_guide(story, kind="stock")

    # ── 可读性改进1：核心要点速览（TL;DR）──
    tldr_items = _tldr(val, fin, cf_quality, business_engine, bear_case, industry_cycle, stock_name)
    if tldr_items:
        story.append(PageBreak())
        story.append(Paragraph("核心要点速览", st["h1"]))
        story.append(Paragraph(
            "以下为报告核心指标的大白话总结，每个指标带信号灯（●绿色=优 / ●黄色=中 / ●红色=劣）和参考区间，帮助快速理解「这个数意味着什么」。详细数据见后续各章节。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.3*cm))
        for item in tldr_items:
            story.append(Paragraph(item, st["body"]))
        story.append(Spacer(1, 0.3*cm))

    # P1-10：事实/判断标注约定
    story.append(Paragraph(
        "标注约定：本报告以【事实】标注可验证的公开数据，【判断】标注基于规则的分析推论，"
        "【情景】标注假设性风险场景。所有结论仅供研究复盘，不构成任何投资建议。",
        st["caption"]
    ))

    # ── 一、公司概况 ──
    story.append(Paragraph("一、公司概况", st["h1"]))
    intro = _chapter_intro("公司概况")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    info_rows = [
        ["股票名称", stock_name, "股票代码", d["ts_code"]],
        ["所属行业", industry, "所在地区", basic.get("area","")],
        ["上市日期", basic.get("list_date",""), "市场", basic.get("market","")],
        ["总市值", f"{val.get('mv_bn','N/A')}亿元", "当前PE(TTM)", str(val.get("pe_ttm","N/A"))],
        ["当前PB", str(val.get("pb","N/A")), "PE历史分位", f"{val.get('pe_percentile','N/A')}%"],
        ["PE近1年分位", f"{val.get('pe_pct_1y','N/A')}%", "PE近3年分位", f"{val.get('pe_pct_3y','N/A')}%"],
        ["当前股价", f"{stock_summary.get('cur_price', 'N/A')}元", "价格来源", stock_summary.get("price_source", "Tushare日线/估值")],
    ]
    story.append(_tbl(info_rows, col_widths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm]))
    story.append(Spacer(1, 0.3*cm))
    # 可读性改进2：指标卡片加信号灯与术语释义
    roe_v = fin.get('roe')
    rev_g_v = fin.get('rev_growth')
    cfo_v = cf_quality.get("latest_ratio") if cf_quality else None
    roe_signal = _signal_text("roe", roe_v, "%")
    rev_signal = _signal_text("rev_growth", rev_g_v, "%")
    cfo_signal = _signal_text("cfo_ratio", cfo_v)
    story.append(metric_cards([
        [f"ROE（{_gloss('ROE')}）", roe_signal, "盈利能力"],
        [f"营收增速（{_gloss('CAGR')}）", rev_signal, "成长性"],
        [f"现金流质量（{_gloss('CFO/净利比')}）", cfo_signal, "利润含金量"],
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
    intro = _chapter_intro("情景区间")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
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
    story.append(Spacer(1, 0.3*cm))

    # ── 三、股价与估值 ──
    story.append(Paragraph("三、股价与估值", st["h1"]))
    intro = _chapter_intro("股价估值")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    if daily_df is not None and not daily_df.empty:
        story.append(_price_chart(daily_df, index_df, stock_name))
        story.append(Paragraph("图：近1年股价走势（灰色虚线为上证综指归一化对比）", st["caption"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 四、业绩分析 ──
    story.append(Paragraph("四、业绩分析", st["h1"]))
    intro = _chapter_intro("业绩分析")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    if income_df is not None and not income_df.empty and "income_df" in fin:
        story.append(_revenue_chart(fin["income_df"], stock_name))
        story.append(Paragraph("图：近5年营业收入与归母净利润（亿元）", st["caption"]))

    # 可读性改进2：业绩表加信号灯 + 术语释义
    fin_rows = [
        ["指标（释义）", "数值（信号灯）"],
        [f"近1年营收增速（{_gloss('CAGR')}）", f"{_signal_text('rev_growth', fin.get('rev_growth'), '%')}"],
        [f"近1年净利润增速（{_gloss('CAGR')}）", f"{_signal_text('profit_growth', fin.get('profit_growth'), '%')}"],
        [f"最新ROE（{_gloss('ROE')}）", f"{_signal_text('roe', fin.get('roe'), '%')}"],
        [f"毛利率（{_gloss('毛利率')}）", f"{_signal_text('gross_margin', fin.get('gross_margin'), '%')}"],
        [f"资产负债率（{_gloss('资产负债率')}）", f"{_signal_text('debt', fin.get('debt_ratio'), '%')}"],
    ]
    story.append(_tbl(fin_rows, col_widths=[6*cm, 6*cm]))
    story.append(Spacer(1, 0.3*cm))

    # ── 五、财务健康度 ──
    story.append(Paragraph("五、财务健康度", st["h1"]))
    intro = _chapter_intro("财务健康")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
    debt = fin.get("debt_ratio", None)
    roe  = fin.get("roe", None)
    health_notes = []
    if roe is not None:
        health_notes.append(f"ROE {_signal_text('roe', roe, '%')}")
    if debt is not None:
        health_notes.append(f"资产负债率 {_signal_text('debt', debt, '%')}")
    for note in health_notes:
        story.append(Paragraph(f"• {note}", st["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── 五点五、现金流质量 ──
    if cf_quality and cf_quality.get("rows"):
        story.append(Paragraph("5.5 现金流质量", st["h2"]))
        intro = _chapter_intro("现金流")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
        story.append(Paragraph(
            f"综合评价：{cf_quality.get('quality_label','N/A')}（CFO/净利润比率越高，利润含金量越高）",
            st["body"]
        ))
        cf_rows = [[f"年份", "经营现金流（亿）", "归母净利润（亿）", f"CFO/净利润（{_gloss('CFO/净利比')}）"]]
        for r in cf_quality["rows"]:
            ratio_signal = _signal_text("cfo_ratio", r["ratio"]) if r["ratio"] is not None else "N/A"
            cf_rows.append([
                r["year"],
                str(r["cfo_bn"]) if r["cfo_bn"] is not None else "N/A",
                str(r["net_bn"]) if r["net_bn"] is not None else "N/A",
                ratio_signal,
            ])
        story.append(_tbl(cf_rows, col_widths=[2.5*cm, 4*cm, 4*cm, 3.5*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 5.6 ROE 杜邦分解（P0-3）──
    if dupont and dupont.get("rows"):
        story.append(Paragraph("5.6 ROE 杜邦分解", st["h2"]))
        intro = _chapter_intro("杜邦")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
        story.append(Paragraph(
            f"ROE = 净利率({_gloss('净利率')}) × 总资产周转率({_gloss('总资产周转率')}) × 权益乘数({_gloss('权益乘数')})。驱动判断：{dupont.get('driver','N/A')}。"
            f"靠净利率的 ROE 含金量高，靠权益乘数（加杠杆）的 ROE 风险在累积。",
            st["body"]
        ))
        dp_rows = [[f"年份", f"净利率(%)({_gloss('净利率')})", f"总资产周转率({_gloss('总资产周转率')})", f"权益乘数({_gloss('权益乘数')})", f"ROE(%)({_gloss('ROE')})"]]
        for r in dupont["rows"]:
            dp_rows.append([str(x) for x in r])
        story.append(_tbl(dp_rows, col_widths=[2.5*cm, 3*cm, 3.5*cm, 3*cm, 2.5*cm]))
        story.append(Spacer(1, 0.3*cm))

    # ── 五点八、资产负债质量 ──
    if bs_quality and bs_quality.get("rows"):
        story.append(Paragraph("5.8 资产负债质量", st["h2"]))
        intro = _chapter_intro("资产负债")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
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
        intro = _chapter_intro("同行对比")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
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
            # P1-9：同行深度对比表（目标行补全净利率/营收增速；peer 行在有数据时自动显示）
            _tgt_nm = business_engine.get("net_margin") if business_engine else None
            peer_rows = [["角色", "名称", "市值(亿)", "PE", "PB", "ROE", "毛利率", "净利率", "营收增速", "净利增速"]]
            peer_rows.append([
                target.get("role", "目标公司"),
                target.get("name", stock_name),
                f"{target.get('mv_bn'):.1f}" if target.get("mv_bn") is not None else "N/A",
                f"{target.get('pe_ttm'):.1f}" if target.get("pe_ttm") is not None else "N/A",
                f"{target.get('pb'):.1f}" if target.get("pb") is not None else "N/A",
                f"{target.get('roe'):.1f}%" if target.get("roe") is not None else "N/A",
                f"{target.get('gross_margin'):.1f}%" if target.get("gross_margin") is not None else "N/A",
                f"{_tgt_nm:.1f}%" if _tgt_nm is not None else "N/A",
                f"{target.get('rev_growth'):.1f}%" if target.get("rev_growth") is not None else "N/A",
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
                    f"{p.get('net_margin'):.1f}%" if p.get("net_margin") is not None else "N/A",
                    f"{p.get('rev_growth'):.1f}%" if p.get("rev_growth") is not None else "N/A",
                    f"{p.get('profit_growth'):.1f}%" if p.get("profit_growth") is not None else "N/A",
                ])
            story.append(_tbl(peer_rows, col_widths=[1.9*cm, 2.5*cm, 1.6*cm, 1.25*cm, 1.25*cm, 1.45*cm, 1.45*cm, 1.45*cm, 1.65*cm, 1.65*cm]))
            story.append(Paragraph(
                "说明：龙头参照用于判断行业定价锚和质量上限；若目标公司估值显著低于龙头，需要进一步判断是低估机会，"
                "还是商业模式、成长性、治理或现金流折价。同行 ROE/毛利率/净利率/增速在其财务数据接入后自动填充（当前同行仅含估值与市值）。",
                st["caption"]
            ))
            # 同行定位结论（规则化判断）
            _pos_parts = []
            _pe_pct = peer_view.get("percentile", {}).get("pe_ttm")
            _roe_pct = peer_view.get("percentile", {}).get("roe")
            if _pe_pct is not None:
                _pos_parts.append(f"PE 处于同行 {_pe_pct}% 分位")
            if _roe_pct is not None:
                _pos_parts.append(f"ROE 处于同行 {_roe_pct}% 分位")
            _med = peer_view.get("industry_median", {})
            if _med.get("pe_ttm") is not None and target.get("pe_ttm") is not None:
                _rel = "低于" if target["pe_ttm"] < _med["pe_ttm"] else ("高于" if target["pe_ttm"] > _med["pe_ttm"] else "接近")
                _pos_parts.append(f"PE {_rel}行业中位数 {_med['pe_ttm']:.1f}")
            if _pos_parts:
                story.append(Paragraph(
                    f"【判断】同行定位：{'；'.join(_pos_parts)}。"
                    f"若估值折价伴随更优的 ROE/增速，则折价可能为机会；若折价源于成长性或治理劣势，则属合理风险补偿。",
                    st["body"]
                ))
            story.append(Spacer(1, 0.3*cm))

    # ── 七、三情景分析 ──
    if scenario and scenario.get("cur_price"):
        story.append(Paragraph("七、三情景分析（未来1年）", st["h1"]))
        intro = _chapter_intro("三情景")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
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
    intro = _chapter_intro("资金面")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
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
    intro = _chapter_intro("股东结构")
    if intro:
        story.append(Paragraph(intro, st["caption"]))
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
            "本次未接入互联网检索（零 token 纯结构化模式），行业与公司动态暂缺。"
            "如需该章节，提供对应股票代码的 TDX wenda 检索结果（tdx_raw/<code>_research.json）即可生成「十四、互联网研究（多维交叉验证）」。",
            st["caption"]
        ))
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

    # ── 十七、隐含预期推演（反向 DCF，P0-2）──
    if reverse_dcf:
        story.append(PageBreak())
        story.append(Paragraph("十七、隐含预期推演（反向 DCF）", st["h1"]))
        intro = _chapter_intro("反向DCF")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
        story.append(Paragraph(
            "本节不预测股价，而是反推：当前市值定价了多少未来增长？隐含预期越高于历史增速，定价越乐观。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.2*cm))
        rdc_rows = [
            ["指标", "数值"],
            ["当前市值", f"{reverse_dcf.get('mv_bn','N/A')} 亿元"],
            ["最新年报归母净利", f"{reverse_dcf.get('np0_bn','N/A')} 亿元"],
            ["历史净利 CAGR", f"{reverse_dcf.get('hist_cagr','N/A')}%"],
            ["市场隐含增速", f"{reverse_dcf.get('implied_growth','N/A')}%"],
            ["核心假设", reverse_dcf.get("assumptions","N/A")],
        ]
        story.append(_tbl(rdc_rows, col_widths=[5*cm, 11*cm]))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(f"【判断】{reverse_dcf.get('verdict','N/A')}", st["body"]))
        story.append(Paragraph(
            "注：隐含增速为简化反向 DCF 推算结果，受折现率/永续增长率假设影响，仅作参考。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.3*cm))

    # ── 十八、未来验证节点（监控清单，P0-5）──
    if monitor:
        story.append(PageBreak())
        story.append(Paragraph("十八、未来验证节点（监控清单）", st["h1"]))
        intro = _chapter_intro("监控清单")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
        story.append(Paragraph(
            "以下为规则化生成的跟踪框架：强化逻辑的事件与证伪逻辑的数据，用于持续验证研究结论。不构成买卖建议。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("强化逻辑的事件", st["h2"]))
        for item in monitor.get("strengthen", []):
            story.append(Paragraph(f"• 【验证·强化】{item}", st["body"]))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("证伪逻辑的数据", st["h2"]))
        for item in monitor.get("falsify", []):
            story.append(Paragraph(f"• 【验证·证伪】{item}", st["body"]))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("关键时间节点", st["h2"]))
        for item in monitor.get("milestones", []):
            story.append(Paragraph(f"• {item}", st["body"]))
        story.append(Spacer(1, 0.3*cm))

    # ── 十九、赚钱机制与商业模式拆解（P1-8）──
    if business_engine:
        story.append(PageBreak())
        story.append(Paragraph("十九、赚钱机制与商业模式拆解", st["h1"]))
        intro = _chapter_intro("赚钱机制")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
        story.append(Paragraph(
            "本节从毛利率、净利率与资产周转拆解公司“靠什么赚钱”，区分产品溢价型与规模效率型。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.2*cm))
        be_rows = [["维度", "数值/判断"]]
        be_rows.append(["年营业收入", f"{business_engine.get('revenue_bn','N/A')} 亿元 【事实】"])
        be_rows.append(["毛利率", f"{business_engine.get('gross_margin','N/A')}% 【事实】"])
        be_rows.append(["净利率", f"{business_engine.get('net_margin','N/A')}% 【事实】"])
        if business_engine.get("asset_turnover") is not None:
            be_rows.append(["总资产周转率", f"{business_engine.get('asset_turnover')} 【事实】"])
        if business_engine.get("equity_turnover") is not None:
            be_rows.append(["每元净资产创收", f"{business_engine.get('equity_turnover')} 元 【事实】"])
        story.append(_tbl(be_rows, col_widths=[4*cm, 12*cm]))
        story.append(Spacer(1, 0.2*cm))
        if business_engine.get("model"):
            story.append(Paragraph(f"【判断】盈利模式：{business_engine.get('model')}", st["body"]))
        if business_engine.get("quality"):
            story.append(Paragraph(f"【判断】盈利质量：{business_engine.get('quality')}", st["body"]))
        if business_engine.get("driver"):
            story.append(Paragraph(f"【判断】赚钱驱动：{business_engine.get('driver')}", st["body"]))
        story.append(Paragraph(
            "注：毛利率/净利率/周转率为可验证财务事实；盈利模式归类为基于上述数据的规则化判断。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.3*cm))

    # ── 二十、行业周期与格局判断（P1-7）──
    if industry_cycle:
        story.append(PageBreak())
        story.append(Paragraph("二十、行业周期与格局判断", st["h1"]))
        intro = _chapter_intro("行业周期")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
        story.append(Paragraph(
            "基于同业截面估值与增长信号的轻量代理判断（缺行业历史PE序列与产能/Capex数据，仅为方向性参考）。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.2*cm))
        ic2_rows = [["信号", "判断"]]
        if industry_cycle.get("heat"):
            ic2_rows.append(["行业估值热度", f"{industry_cycle.get('heat')} 【判断】"])
        if industry_cycle.get("position"):
            ic2_rows.append(["目标相对行业位置", f"{industry_cycle.get('position')} 【判断】"])
        if industry_cycle.get("growth_signal"):
            ic2_rows.append(["公司增长信号", f"{industry_cycle.get('growth_signal')} 【事实·判断混合】"])
        story.append(_tbl(ic2_rows, col_widths=[4*cm, 12*cm]))
        story.append(Spacer(1, 0.2*cm))
        if industry_cycle.get("stage"):
            story.append(Paragraph(f"【判断】周期阶段：{industry_cycle.get('stage')}", st["body"]))
        story.append(Paragraph(
            "说明：本判断使用同业PE中位数、目标在行业中的PE分位与增长数据做规则化推断，"
            "未接入行业产能/资本开支/库存等深层数据，结论仅供参考。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.3*cm))

    # ── 二十一、空方逻辑与风险推演（P1-6）──
    if bear_case:
        story.append(PageBreak())
        story.append(Paragraph("二十一、空方逻辑与风险推演", st["h1"]))
        intro = _chapter_intro("空方逻辑")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
        story.append(Paragraph(
            "对抗确认偏误：强制列出看空理由与黑天鹅场景。以下量化信号为规则化识别，"
            "偏空检索线索来自互联网研究（需以公告核实）。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("看空理由（量化信号）", st["h2"]))
        for b in bear_case.get("bear", []):
            story.append(Paragraph(f"• 【判断】{b}", st["body"]))
        if bear_case.get("facts"):
            story.append(Spacer(1, 0.2*cm))
            story.append(Paragraph("偏空检索线索", st["h2"]))
            for f in bear_case.get("facts", []):
                story.append(Paragraph(f"• {f}", st["body"]))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("黑天鹅场景（需重点防范）", st["h2"]))
        for s in bear_case.get("swans", []):
            story.append(Paragraph(f"• 【情景】{s}", st["body"]))
        story.append(Paragraph(
            "注：黑天鹅为基于行业特征的情景假设，不代表预测；用于提示需持续跟踪的脆弱点。",
            st["caption"]
        ))
        story.append(Spacer(1, 0.3*cm))

    # ── 二十二、数据来源与取数说明（P1-11）──
    if data_sources:
        story.append(PageBreak())
        story.append(Paragraph("二十二、数据来源与取数说明", st["h1"]))
        intro = _chapter_intro("数据来源")
        if intro:
            story.append(Paragraph(intro, st["caption"]))
        story.append(Paragraph(
            "本报告为纯规则化、零 token 编排：所有指标由公开数据计算，未调用任何大模型。来源如下：",
            st["caption"]
        ))
        story.append(Spacer(1, 0.2*cm))
        src_rows = [["数据项", "来源/方法", "取数时间"]]
        for s in data_sources:
            src_rows.append([s.get("item", "N/A"), s.get("source", "N/A"), s.get("time", "N/A")])
        story.append(_tbl(src_rows, col_widths=[4*cm, 9*cm, 3*cm]))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(
            "说明：财务数据以 TDX（通达信）F10 接口采集，行情以 AkShare 新浪源补充；"
            "所有计算在本地完成，不具备实时性，请以交易所与上市公司最新公告为准。",
            st["caption"]
        ))
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
