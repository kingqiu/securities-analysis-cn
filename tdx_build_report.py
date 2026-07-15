#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TDX 数据编排层 (PoC) —— 贵州茅台 A股研究复盘报告

零 token 产出 PDF：
  - 财务数据来自通达信 MCP（tdx_quotes hasCwInfo + ph_agf10_cw_lyb，2026-07-15 采集），
    以 Python 字面量嵌入（生产可改为读取 tdx_raw/*.json 落盘文件）。
  - 日线/指数行情由 AkShare 拉取（免 token；生产可改 TDX tdx_kline 落盘文件，已验证可用）。
  - 组装成 step4_generate_stock_pdf 期望的「中间 JSON 列名契约」，
    复用 analyst_model + PDF 引擎，绕过 Tushare 取数层与 identify_code_type。

契约（step4._load）：每个块 = {"fields":[...], "items":[[...],...]}，
pd.DataFrame(items, columns=fields) 还原。列名必须为英文精确名。
"""
import os
import sys
import json
from datetime import datetime, timedelta

import pandas as pd
import akshare as ak

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

# ============================================================
# TDX 采集的财务数据 (2026-07-15, code=600519 贵州茅台)
# 来源：tdx_quotes(hasCwInfo=1) + tdx_api_data ph_agf10_cw_lyb
# ============================================================
NAME = "贵州茅台"
TSCODE = "600519.SH"
SHARES = 1250081560            # tdx_quotes ZGB=125008.156 万股 → 股
NET_ASSETS = 270894040000      # tdx_quotes JZC=27089404 万元 → 元（净资产）
TOTAL_ASSETS = 319918840000    # tdx_quotes ZZC=31991884 万元 → 元（总资产）
PRICE_NOW = 1244.97            # tdx_quotes Now（实时价，用于情景价重缩放）
LIST_DATE = "20010827"         # tdx_quotes Start
INDUSTRY = "白酒"              # TDX BelongHY=82102 → 白酒

# ph_agf10_cw_lyb 年报： (end_date, 营业总收入, 归属母公司净利润, 营业成本)  单位：元
INCOME_ANNUAL = [
    ("20201231", 97993240501.21,  46697285429.81, 8154001476.28),
    ("20211231", 109464278563.89, 52460144378.16, 8983377809.96),
    ("20221231", 127553959355.97, 62717467870.12, 10093468616.63),
    ("20231231", 150560330316.45, 74734071550.75, 11867273851.78),
    ("20241231", 174144069958.25, 86228146421.62, 13789482367.98),
    ("20251231", 172054171890.91, 82320067101.68, 14892277570.91),
]
TTM_NET_PROFIT = 82320067101.68   # 2025年报归母净利（近 120 个交易日均在 2026 年，TTM 近似）


# ============================================================
# 行情拉取（AkShare，免 token）
# ============================================================
def fetch_daily(code: str, days: int = 130) -> pd.DataFrame:
    """用新浪源（ak.stock_zh_a_daily）拉日线，避开东财 push2 域名封锁。symbol 需带 sh/sz 前缀。"""
    sym = ("sh" if code.startswith(("5", "6", "9")) else "sz") + code
    df = ak.stock_zh_a_daily(symbol=sym, adjust="qfq")
    df = df.rename(columns={"date": "trade_date", "close": "close",
                            "high": "high", "low": "low", "volume": "vol"})
    df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")
    df = df[["trade_date", "close", "high", "low", "vol"]].tail(days)
    for c in ("close", "high", "low", "vol"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


def fetch_index(days: int = 130) -> pd.DataFrame:
    """上证综指(000001) 日线，新浪源，作为基准。"""
    df = None
    for fn in (
        lambda: ak.stock_zh_index_daily(symbol="sh000001"),   # 新浪源
        lambda: ak.index_zh_a_hist(symbol="000001", period="daily",
                                   start_date=(datetime.now()-timedelta(days=days*2)).strftime("%Y%m%d"),
                                   end_date=datetime.now().strftime("%Y%m%d")),  # 东财兜底
    ):
        try:
            df = fn()
            if df is not None and not df.empty:
                break
        except Exception as e:
            print(f"  index 候选失败: {e}")
    if df is None or df.empty:
        return pd.DataFrame(columns=["trade_date", "close"])
    col_date = "date" if "date" in df.columns else ("日期" if "日期" in df.columns else df.columns[0])
    df = df.rename(columns={col_date: "trade_date", "收盘": "close", "close": "close"})
    df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")
    df = df[["trade_date", "close"]].tail(days)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.reset_index(drop=True)


# ============================================================
# 中间 JSON 组装（满足 step4 列名契约）
# ============================================================
def _items(df: pd.DataFrame):
    """DataFrame -> [[...],...] 且 numpy 标量转 Python 原生、NaN->None。"""
    records = df.to_dict("records")
    fields = list(df.columns)
    out = []
    for rec in records:
        row = []
        for f in fields:
            v = rec[f]
            if isinstance(v, float) and v != v:   # NaN
                v = None
            row.append(v)
        out.append(row)
    return out


def build_fina_indicator():
    """roe=归母净利/净资产；grossprofit_margin=(营收-营业成本)/营收；debt_to_assets=(总资产-净资产)/总资产。"""
    rows = []
    for ed, rev, net, cost in INCOME_ANNUAL:
        roe = round(net / NET_ASSETS * 100, 2)
        gm = round((rev - cost) / rev * 100, 2)
        dr = round((TOTAL_ASSETS - NET_ASSETS) / TOTAL_ASSETS * 100, 2)
        rows.append([ed, roe, gm, dr])
    return rows


def build_intermediate(daily_df: pd.DataFrame, index_df: pd.DataFrame) -> dict:
    # daily_basic：个股日 PE-TTM = close*总股本/TTM归母净利；pb=close*总股本/净资产；total_mv=close*总股本
    db = daily_df[["trade_date", "close"]].copy()
    db["pe_ttm"] = (db["close"] * SHARES / TTM_NET_PROFIT).round(2)
    db["pb"] = (db["close"] * SHARES / NET_ASSETS).round(2)
    db["total_mv"] = (db["close"] * SHARES).round(0)
    db = db[["trade_date", "pe_ttm", "pb", "total_mv", "close"]]

    if index_df.empty:
        index_df = daily_df[["trade_date", "close"]].copy()  # 兜底：用个股自身作基准，避免图表空

    return {
        "ts_code": TSCODE,
        "fetch_time": datetime.now().isoformat(),
        "basic": {
            "fields": ["name", "industry", "list_date", "market"],
            "items": [[NAME, INDUSTRY, LIST_DATE, "主板"]],
        },
        "daily": {
            "fields": ["trade_date", "close", "high", "low", "vol"],
            "items": _items(daily_df),
        },
        "daily_basic": {
            "fields": ["trade_date", "pe_ttm", "pb", "total_mv", "close"],
            "items": _items(db),
        },
        "index_daily": {
            "fields": ["trade_date", "close"],
            "items": _items(index_df),
        },
        "income": {
            "fields": ["end_date", "total_revenue", "n_income_attr_p"],
            "items": [[r[0], r[1], r[2]] for r in INCOME_ANNUAL],
        },
        "fina_indicator": {
            "fields": ["end_date", "roe", "grossprofit_margin", "debt_to_assets"],
            "items": build_fina_indicator(),
        },
        "realtime_quote": {"price": PRICE_NOW, "source": "tdx_quotes"},
        "_data_source": "TDX MCP (financials) + AkShare (daily bars); zero token",
    }


def main():
    print("=" * 70)
    print("TDX 编排层 PoC —— 贵州茅台 A股报告（零 token）")
    print("=" * 70)

    print("\n[1/3] 拉取日线（AkShare）...")
    daily = fetch_daily("600519", 130)
    print(f"  daily 行数: {len(daily)}  日期范围: {daily['trade_date'].iloc[0]} ~ {daily['trade_date'].iloc[-1]}")

    print("\n[2/3] 拉取指数（上证综指，AkShare）...")
    index = fetch_index(130)
    print(f"  index 行数: {len(index)}")

    print("\n[3/3] 组装中间 JSON（TDX 财务 + 计算个股日 PE）...")
    data = build_intermediate(daily, index)
    n_pe = len(data["daily_basic"]["items"])
    pe_vals = [r[1] for r in data["daily_basic"]["items"] if r[1]]
    print(f"  daily_basic PE 点数: {n_pe}（≥10 即可触发情景区间）")
    if pe_vals:
        print(f"  PE 区间: {min(pe_vals):.2f} ~ {max(pe_vals):.2f}  最新: {pe_vals[-1]:.2f}")

    out_json = os.path.join(PROJECT_DIR, "temp_600519_SH_data.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  中间 JSON -> {os.path.basename(out_json)}")

    print("\n[4/4] 调用 step4 引擎生成 PDF...")
    from step4_generate_stock_pdf import create_stock_pdf
    out_pdf = os.path.join(
        PROJECT_DIR, f"{NAME}_股票深度分析报告_{datetime.now().strftime('%Y%m%d')}.pdf"
    )
    create_stock_pdf(out_json, out_pdf)
    print(f"\n✓ PDF 生成: {os.path.basename(out_pdf)}")
    print(f"  路径: {out_pdf}")


if __name__ == "__main__":
    main()
