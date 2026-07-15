#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用报告生成器（零 token）—— 股票走 step4，ETF 走 step3。
财务数据从 fin_<code>.json 读取（TDX 采集后提取），日线/指数行情用 AkShare 新浪源。
用法: python3 run_report.py <code> <stock|etf>
"""
import os, sys, json
from datetime import datetime, timedelta
import pandas as pd
import akshare as ak

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)


def _items(df: pd.DataFrame):
    records = df.to_dict("records")
    fields = list(df.columns)
    out = []
    for rec in records:
        out.append([None if (isinstance(rec[f], float) and rec[f] != rec[f]) else rec[f] for f in fields])
    return out


def fetch_daily(code: str, days=130):
    sym = ("sh" if code.startswith(("5", "6", "9")) else "sz") + code
    df = ak.stock_zh_a_daily(symbol=sym, adjust="qfq")
    df = df.rename(columns={"date": "trade_date", "close": "close", "high": "high", "low": "low", "volume": "vol"})
    df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")
    df = df[["trade_date", "close", "high", "low", "vol"]].tail(days)
    for c in ("close", "high", "low", "vol"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


def fetch_index(days=130):
    for fn in (lambda: ak.stock_zh_index_daily(symbol="sh000001"),
               lambda: ak.index_zh_a_hist(symbol="000001", period="daily",
                           start_date=(datetime.now()-timedelta(days=days*2)).strftime("%Y%m%d"),
                           end_date=datetime.now().strftime("%Y%m%d"))):
        try:
            df = fn()
            if df is not None and not df.empty:
                break
        except Exception:
            continue
    col_date = "date" if "date" in df.columns else "日期"
    df = df.rename(columns={col_date: "trade_date", "收盘": "close"})
    df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")
    df = df[["trade_date", "close"]].tail(days)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.reset_index(drop=True)


def fetch_etf_daily(code: str, days=130):
    """ETF 日线：优先东财 fund_etf_hist_em，失败用新浪 stock_zh_a_daily。"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days*2)).strftime("%Y%m%d")
    try:
        df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
        df = df.rename(columns={"日期": "trade_date", "收盘": "close", "最高": "high", "最低": "low", "成交量": "vol"})
    except Exception:
        sym = ("sh" if code.startswith(("5", "6", "9")) else "sz") + code
        df = ak.stock_zh_a_daily(symbol=sym, adjust="qfq")
        df = df.rename(columns={"date": "trade_date", "close": "close", "high": "high", "low": "low", "volume": "vol"})
    df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")
    df = df[["trade_date", "close", "high", "low", "vol"]].tail(days)
    for c in ("close", "high", "low", "vol"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


def build_stock(code, fin):
    name, shares = fin["name"], fin["shares"]
    net_assets, total_assets = fin["net_assets"], fin["total_assets"]
    price, industry, list_date = fin["price"], fin.get("industry", ""), fin.get("list_date", "")
    income = fin["income_annual"]  # [(end_date, total_revenue, n_income_attr_p, oper_cost), ...]
    ttm_np = fin.get("ttm_net_profit") or income[-1][2]
    ts_code = fin.get("ts_code", code + (".SH" if code.startswith(("5","6","9")) else ".SZ"))

    daily = fetch_daily(code)
    index = fetch_index()
    print(f"  daily={len(daily)} index={len(index)} PE点将计算")

    db = daily[["trade_date", "close"]].copy()
    db["pe_ttm"] = (db["close"] * shares / ttm_np).round(2)
    db["pb"] = (db["close"] * shares / net_assets).round(2)
    db["total_mv"] = (db["close"] * shares).round(0)
    db = db[["trade_date", "pe_ttm", "pb", "total_mv", "close"]]

    # fina_indicator（最新年报一期）
    ed, rev, net, cost = income[-1]
    fina_rows = [[ed, round(net/net_assets*100,2), round((rev-cost)/rev*100,2),
                  round((total_assets-net_assets)/total_assets*100,2)]]

    data = {
        "ts_code": ts_code, "fetch_time": datetime.now().isoformat(),
        "basic": {"fields": ["name","industry","list_date","market"], "items": [[name, industry, list_date, "主板"]]},
        "daily": {"fields": ["trade_date","close","high","low","vol"], "items": _items(daily)},
        "daily_basic": {"fields": ["trade_date","pe_ttm","pb","total_mv","close"], "items": _items(db)},
        "index_daily": {"fields": ["trade_date","close"], "items": _items(index)},
        "income": {"fields": ["end_date","total_revenue","n_income_attr_p"],
                   "items": [[r[0], r[1], r[2]] for r in income]},
        "fina_indicator": {"fields": ["end_date","roe","grossprofit_margin","debt_to_assets"], "items": fina_rows},
        "realtime_quote": {"price": price, "source": "tdx_quotes"},
    }
    if "cashflow_annual" in fin:
        data["cashflow"] = {"fields": ["end_date","n_cashflow_act"], "items": [list(r) for r in fin["cashflow_annual"]]}
    if "moneyflow_20d" in fin:
        data["moneyflow"] = {"fields": ["trade_date","net_mf_amount"], "items": [list(r) for r in fin["moneyflow_20d"]]}
    if "industry_peers" in fin:
        data["industry_peers"] = {"industry": industry, "peers": fin["industry_peers"]}

    out_json = os.path.join(PROJECT_DIR, f"temp_{code}_data.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    n_pe = len(data["daily_basic"]["items"])
    pe_vals = [r[1] for r in data["daily_basic"]["items"] if r[1]]
    print(f"  PE点={n_pe} 区间={min(pe_vals):.2f}~{max(pe_vals):.2f} 最新={pe_vals[-1]:.2f}")

    from step4_generate_stock_pdf import create_stock_pdf
    out_pdf = os.path.join(PROJECT_DIR, f"{name}_股票深度分析报告_{datetime.now().strftime('%Y%m%d')}.pdf")
    create_stock_pdf(out_json, out_pdf)
    print(f"  ✓ {out_pdf}")


def build_etf(code, fin):
    name = fin["name"]
    mgmt = fin.get("management", "")
    idx_code = fin.get("index_code", "000688.SH")
    idx_name = fin.get("index_name", "科创50")
    ts_code = fin.get("ts_code", code + ".SH")

    daily = fetch_etf_daily(code)
    print(f"  etf daily={len(daily)}")
    # 跟踪指数日线（科创50=000688 上证，setcode 沪）
    try:
        idx = ak.stock_zh_index_daily(symbol="sh000688")
        idx = idx.rename(columns={"date":"trade_date","close":"close"})
        idx["trade_date"] = idx["trade_date"].astype(str).str.replace("-","")
        idx = idx[["trade_date","close"]].tail(130)
        idx["close"] = pd.to_numeric(idx["close"], errors="coerce")
    except Exception as e:
        print(f"  指数取数失败({e})，用ETF自身作基准")
        idx = daily[["trade_date","close"]].copy()

    data = {
        "ts_code": ts_code, "index_code": idx_code, "fetch_time": datetime.now().isoformat(),
        "basic": {"fields": ["name","management","fund_type","benchmark"],
                  "items": [[name, mgmt, "ETF", idx_name]]},
        "daily": {"fields": ["trade_date","close","high","low","vol"], "items": _items(daily)},
        "index_daily": {"fields": ["trade_date","close"], "items": _items(idx)},
        "realtime_quote": {"price": float(daily["close"].iloc[-1]), "source": "akshare_etf"},
    }
    out_json = os.path.join(PROJECT_DIR, f"temp_{code}_etf_data.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    from step3_generate_pdf_report import create_etf_pdf
    out_pdf = os.path.join(PROJECT_DIR, f"{name}_ETF深度分析报告_{datetime.now().strftime('%Y%m%d')}.pdf")
    create_etf_pdf(out_json, out_pdf)
    print(f"  ✓ {out_pdf}")


def main():
    if len(sys.argv) < 3:
        print("用法: python3 run_report.py <code> <stock|etf>"); sys.exit(1)
    code, kind = sys.argv[1], sys.argv[2]
    fin_path = os.path.join(PROJECT_DIR, f"fin_{code}.json")
    with open(fin_path, encoding="utf-8") as f:
        fin = json.load(f)
    print(f"=== {fin.get('name', code)} ({code}) {kind} ===")
    if kind == "stock":
        build_stock(code, fin)
    else:
        build_etf(code, fin)


if __name__ == "__main__":
    main()
