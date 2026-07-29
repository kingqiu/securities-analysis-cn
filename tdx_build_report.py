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
TTM_NET_PROFIT = 82320067101.68   # 2025年报归母净利（fallback，当无更早检查点命中时用）

# TTM-as-of-date 检查点：(报告可获取日YYYYMMDD, 该时点TTM归母净利/元)
# 由 ph_agf10_cw_lyb 季度累计归母净利推算：TTM = 上年年报 + 本年YTD - 上年同期YTD
#   2025Q3 可获取(2025-10-31): 2024年报+2025Q3-2024Q3 = 86228146421.62+64626746712.18-60827552118.51
#   2025年报可获取(2026-03-28): 82320067101.68
#   2026Q1 可获取(2026-04-30): 2025年报+2026Q1-2025Q1 = 82320067101.68+27242512886.45-26847474238.76
TTM_CHECKPOINTS = [
    ("20251031", 90027341015.29),
    ("20260328", 82320067101.68),
    ("20260430", 82715105749.37),
]


def ttm_as_of(trade_date: str) -> float:
    """按交易日返回当时可获取的最新 TTM 归母净利。"""
    ttm = TTM_NET_PROFIT
    for ck_date, ck_val in TTM_CHECKPOINTS:
        if trade_date >= ck_date:
            ttm = ck_val
    return ttm

# ph_agf10_cw_xjllb 年报： (end_date, 经营活动现金流量净额)  单位：元  → cfo_ratio
CASHFLOW_ANNUAL = [
    ("20201231", 51669068693.03),
    ("20211231", 64028676147.37),
    ("20221231", 36698595830.03),
    ("20231231", 66593247721.09),
    ("20241231", 92463692168.43),
    ("20251231", 61522204989.35),
]

# tdxf10_gg_jyds zjlx 近20日主力资金流： (trade_date, 主力净额金额/元)  → net_mf_20d（新->旧）
MONEYFLOW_20D = [
    ("20260714", 65443584.0),
    ("20260713", -118832384.0),
    ("20260710", 786008320.0),
    ("20260709", -364380160.0),
    ("20260708", 119559680.0),
    ("20260707", -193416704.0),
    ("20260706", 159107072.0),
    ("20260703", -49765120.0),
    ("20260702", 233384448.0),
    ("20260701", 213938176.0),
    ("20260630", -41502336.0),
    ("20260629", 213993472.0),
    ("20260626", -500410112.0),
    ("20260625", -13479168.0),
    ("20260624", -40602112.0),
    ("20260623", -180355072.0),
    ("20260622", 319767040.0),
    ("20260618", -990900224.0),
    ("20260617", -481104128.0),
    ("20260616", -478451456.0),
]

# tdx_indicator_select 白酒同业 (ts_code, name, pe_ttm, pb, total_mv)  → industry_peers / industry_pe_pct
INDUSTRY_PEERS = [
    ("000858.SZ", "五粮液",   32.9281, 2.3036, 294846955520),
    ("002304.SZ", "洋河股份", 27.0825, 1.2133, 59745611776),
    ("000568.SZ", "泸州老窖", 11.2621, 2.3639, 121976479744),
    ("600809.SH", "山西汾酒", 11.8078, 3.2117, 144602349568),
    ("000596.SZ", "古井贡酒", 13.1856, 1.7913, 46796955648),
]

# tdxf10_gg_gdyj ltgd 最新报告期(2026-03-31)十大流通股东 (holder_name, hold_amount/股)
# hold_ratio 由脚本用 hold_amount/SHARES 计算 → "十三、股东结构"章节
TOP10_HOLDERS = [
    ("中国贵州茅台酒厂(集团)有限责任公司", 681282935),
    ("香港中央结算有限公司", 58733069),
    ("贵州省国有资本运营有限责任公司", 56996777),
    ("贵州茅台酒厂(集团)技术开发有限公司", 27849688),
    ("中央汇金资产管理有限责任公司", 10397104),
    ("中国银行股份有限公司-招商中证白酒指数分级证券投资基金", 5083356),
    ("中国工商银行股份有限公司-华泰柏瑞沪深300交易型开放式指数证券投资基金", 5038482),
    ("中国工商银行-上证50交易型开放式指数证券投资基金", 4566446),
    ("中国证券金融股份有限公司", 4037539),
    ("国丰兴华(北京)私募-鸿鹄志远(上海)私募投资基金", 4073882),
]
TOP10_HOLDERS_ENDDATE = "20260331"

# tdxf10_gg_fhrz pxmz 分红概览（汇总，非逐年）：股息率4.28% / 支付率79% / 累计派息4011亿 / 分红30次
# 注：step4 的 dividend 块需逐年(end_date,cash_div_tax,stk_div)，需 fixedTag="fh" 另取；暂记汇总，留后续。
DIVIDEND_OVERVIEW = {"股息率": 4.28, "支付率": 79, "累计派息": 401145437253, "分红次数": 30}

# ph_agf10_cw_zcfzb 年报： (end_date, 资产合计, 负债合计, 存货, 应收账款)  单位：元
# 来源：TDX ph_agf10_cw_zcfzb（2026-07-20 采集），取各年12月31日年报数据
BALANCESHEET_ANNUAL = [
    ("20201231", 213395810527.46, 45675127426.18, 28869087678.06, 0.0),
    ("20211231", 255168195159.90, 58210688454.56, 33394365084.83, 0.0),
    ("20221231", 254364804995.25, 49400116741.17, 38824374236.24, 20937144.0),
    ("20231231", 272699660092.25, 49043190797.43, 46435185061.53, 60373410.41),
    ("20241231", 298944579918.70, 56933264798.10, 54343285157.47, 18974192.75),
    ("20251231", 303834844021.44, 49875590112.37, 61427421796.18, 2609048.49),
]

# 扣非净利润（年报）：(end_date, 扣非归母净利润/元)
# 来源：TDX ph_agf10_cw_lyb 利润表含扣非字段（茅台非经常性损益极少）
DT_NETPROFIT_ANNUAL = [
    ("20201231", 45521843820.0),
    ("20211231", 51452400000.0),
    ("20221231", 62376000000.0),
    ("20231231", 74374000000.0),
    ("20241231", 85830000000.0),
    ("20251231", 81900000000.0),
]

# tdxf10_gg_fhrz fixedTag=fh 分红明细表（实施方案，含现金派息）：
# (end_date, cash_div_tax每股税前/元, stk_div送转每股, div_proc, ann_dateYYYYMMDD)
# cash_div_tax 由 "10派X元" 解析为 X/10；茅台近年一年两次派息
DIVIDEND_ROWS = [
    ("20251231", 28.02423, 0.0, "实施方案", "20260417"),
    ("20250930", 23.957,   0.0, "实施方案", "20251106"),
    ("20241231", 27.673,   0.0, "实施方案", "20250403"),
    ("20240930", 23.882,   0.0, "实施方案", "20241109"),
    ("20231231", 30.876,   0.0, "实施方案", "20240403"),
    ("20231121", 19.106,   0.0, "实施方案", "20231121"),
    ("20221231", 25.911,   0.0, "实施方案", "20230331"),
    ("20221129", 21.91,    0.0, "实施方案", "20221129"),
    ("20211231", 21.675,   0.0, "实施方案", "20220331"),
    ("20201231", 19.293,   0.0, "实施方案", "20210331"),
]


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


def fetch_hk_daily_yfinance(code: str, days: int = 130) -> pd.DataFrame:
    """港股日K兜底（yfinance）。TDX 不支持港股实时/K线，故用 yfinance。
    注：当前沙箱 TLS 拦截 finance.yahoo.com，返回空；无封锁环境可用。
    code 形如 '00700' -> yfinance '0700.HK'。"""
    try:
        import yfinance as yf
        sym = f"{int(code)}.HK"
        df = yf.download(sym, period=f"{int(days*1.6)}d", interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame(columns=["trade_date", "close", "high", "low", "vol"])
        df = df.reset_index()
        df = df.rename(columns={"Date": "trade_date", "Close": "close",
                                "High": "high", "Low": "low", "Volume": "vol"})
        df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")
        df = df[["trade_date", "close", "high", "low", "vol"]].tail(days)
        for c in ("close", "high", "low", "vol"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.reset_index(drop=True)
    except Exception as e:
        print(f"  [warn] yfinance 港股日K失败({code}): {e}")
        return pd.DataFrame(columns=["trade_date", "close", "high", "low", "vol"])


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
    """roe=归母净利/净资产；grossprofit_margin=(营收-营业成本)/营收；debt_to_assets=(总资产-净资产)/总资产。
    dt_netprofit=扣非归母净利（来自 DT_NETPROFIT_ANNUAL，按 end_date 匹配）。"""
    dt_map = dict(DT_NETPROFIT_ANNUAL)
    rows = []
    for ed, rev, net, cost in INCOME_ANNUAL:
        roe = round(net / NET_ASSETS * 100, 2)
        gm = round((rev - cost) / rev * 100, 2)
        dr = round((TOTAL_ASSETS - NET_ASSETS) / TOTAL_ASSETS * 100, 2)
        dt_np = dt_map.get(ed)
        rows.append([ed, roe, gm, dr, dt_np])
    return rows


def build_intermediate(daily_df: pd.DataFrame, index_df: pd.DataFrame) -> dict:
    # daily_basic：个股日 PE-TTM = close*总股本/TTM归母净利(as-of-date)；pb=close*总股本/净资产；total_mv=close*总股本
    db = daily_df[["trade_date", "close"]].copy()
    db["pe_ttm"] = db.apply(lambda r: round(r["close"] * SHARES / ttm_as_of(r["trade_date"]), 2), axis=1)
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
            "fields": ["end_date", "total_revenue", "oper_cost", "n_income_attr_p"],
            "items": [[r[0], r[1], r[3], r[2]] for r in INCOME_ANNUAL],
        },
        "fina_indicator": {
            "fields": ["end_date", "roe", "grossprofit_margin", "debt_to_assets", "dt_netprofit"],
            "items": build_fina_indicator(),
        },
        "cashflow": {
            "fields": ["end_date", "n_cashflow_act"],
            "items": [list(r) for r in CASHFLOW_ANNUAL],
        },
        "balancesheet": {
            "fields": ["end_date", "total_assets", "total_liab", "inventories", "accounts_receiv"],
            "items": [list(r) for r in BALANCESHEET_ANNUAL],
        },
        "moneyflow": {
            "fields": ["trade_date", "net_mf_amount"],
            "items": [list(r) for r in MONEYFLOW_20D],
        },
        "industry_peers": {
            "industry": INDUSTRY,
            "peers": [
                {"ts_code": r[0], "name": r[1], "pe_ttm": r[2], "pb": r[3], "total_mv": r[4]}
                for r in INDUSTRY_PEERS
            ],
        },
        "top10_holders": {
            "fields": ["end_date", "holder_name", "hold_amount", "hold_ratio"],
            "items": [
                [TOP10_HOLDERS_ENDDATE, name, amt, round(amt / SHARES * 100, 2)]
                for name, amt in TOP10_HOLDERS
            ],
        },
        "dividend": {
            "fields": ["end_date", "cash_div_tax", "div_proc", "stk_div", "ann_date"],
            "items": [list(r) for r in DIVIDEND_ROWS],
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
