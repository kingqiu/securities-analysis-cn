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


def fetch_daily(code: str):
    """A股日线全量（新浪源），由调用方按需 tail。"""
    sym = ("sh" if code.startswith(("5", "6", "9")) else "sz") + code
    df = ak.stock_zh_a_daily(symbol=sym, adjust="qfq")
    df = df.rename(columns={"date": "trade_date", "close": "close", "high": "high", "low": "low", "volume": "vol"})
    df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")
    df = df[["trade_date", "close", "high", "low", "vol"]]
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
    """ETF 日线：优先读 TDX 落盘文件 tdx_raw/<code>_daily.json（最稳），
    否则新浪 stock_zh_a_daily，再否则东财 fund_etf_hist_em。返回含 amount。"""
    tdx_file = os.path.join(PROJECT_DIR, "tdx_raw", f"{code}_daily.json")
    if os.path.exists(tdx_file):
        with open(tdx_file, encoding="utf-8") as f:
            raw = json.load(f)
        df = pd.DataFrame(raw["items"], columns=raw["fields"])
        print(f"  ETF日线来自 TDX 落盘文件({len(df)}行)", flush=True)
        return df.tail(days).reset_index(drop=True)
    sym = ("sh" if code.startswith(("5", "6", "9")) else "sz") + code
    df = None
    try:
        df = ak.stock_zh_a_daily(symbol=sym, adjust="qfq")
        df = df.rename(columns={"date": "trade_date", "close": "close", "high": "high", "low": "low", "volume": "vol", "amount": "amount"})
    except Exception as e:
        print(f"  sina ETF 日线失败({e})，尝试东财", flush=True)
    if df is None or df.empty:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days*2)).strftime("%Y%m%d")
        df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
        df = df.rename(columns={"日期": "trade_date", "收盘": "close", "最高": "high", "最低": "low", "成交量": "vol", "成交额": "amount"})
    df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")
    keep = ["trade_date", "close", "high", "low", "vol"] + (["amount"] if "amount" in df.columns else [])
    df = df[keep].tail(days)
    for c in keep[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


def build_stock(code, fin):
    name, shares = fin["name"], fin["shares"]
    net_assets, total_assets = fin["net_assets"], fin["total_assets"]
    price, industry, list_date = fin["price"], fin.get("industry", ""), fin.get("list_date", "")
    income = fin["income_annual"]  # [(end_date, total_revenue, n_income_attr_p, oper_cost), ...]
    ttm_np = fin.get("ttm_net_profit") or income[-1][2]
    ts_code = fin.get("ts_code", code + (".SH" if code.startswith(("5","6","9")) else ".SZ"))

    daily_full = fetch_daily(code)
    daily = daily_full.tail(130).reset_index(drop=True)
    index = fetch_index()
    print(f"  daily={len(daily)} (full={len(daily_full)}) index={len(index)} PE点将计算")

    # P0-4：daily_basic 取近3年(750交易日)用于多档分位
    db_src = daily_full.tail(750).reset_index(drop=True)
    db = db_src[["trade_date", "close"]].copy()
    db["pe_ttm"] = (db["close"] * shares / ttm_np).round(2)
    db["pb"] = (db["close"] * shares / net_assets).round(2)
    db["total_mv"] = (db["close"] * shares).round(0)
    db = db[["trade_date", "pe_ttm", "pb", "total_mv", "close"]]

    # fina_indicator（最新年报一期）
    ed, rev, net, cost = income[-1]
    fina_rows = [[ed, round(net/net_assets*100,2), round((rev-cost)/rev*100,2),
                  round((total_assets-net_assets)/total_assets*100,2)]]

    # P0-3：杜邦分解（最新年报一期）
    _nm = net / rev if rev else 0               # 净利率
    _at = rev / total_assets if total_assets else 0  # 总资产周转率
    _em = total_assets / net_assets if net_assets else 0  # 权益乘数
    _roe_d = _nm * _at * _em
    if _em >= _nm and _em >= _at:
        _driver = "权益乘数（杠杆）驱动，ROE 含金量偏低，需警惕负债风险"
    elif _nm >= _at and _nm >= _em:
        _driver = "净利率驱动，ROE 含金量高，盈利能力强"
    else:
        _driver = "周转率驱动，运营效率较高"
    dupont = {
        "rows": [[ed[:4], round(_nm*100,2), round(_at,3), round(_em,3), round(_roe_d*100,2)]],
        "driver": _driver,
    }

    data = {
        "ts_code": ts_code, "fetch_time": datetime.now().isoformat(),
        "basic": {"fields": ["name","industry","list_date","market"], "items": [[name, industry, list_date, "主板"]]},
        "daily": {"fields": list(daily.columns), "items": _items(daily)},
        "daily_basic": {"fields": ["trade_date","pe_ttm","pb","total_mv","close"], "items": _items(db)},
        "index_daily": {"fields": ["trade_date","close"], "items": _items(index)},
        "income": {"fields": ["end_date","total_revenue","oper_cost","n_income_attr_p"],
                   "items": [[r[0], r[1], r[3], r[2]] for r in income]},
        "fina_indicator": {"fields": ["end_date","roe","grossprofit_margin","debt_to_assets"], "items": fina_rows},
        "realtime_quote": {"price": price, "source": "tdx_quotes"},
        "dupont": dupont,
    }

    # 公司画像（用于赚钱机制拆解）
    data["profile"] = {
        "fields": ["shares","total_assets","net_assets"],
        "items": [[shares, total_assets, net_assets]],
    }

    # P1-11：数据来源清单
    fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    research_file = os.path.join(PROJECT_DIR, "tdx_raw", f"{code}_research.json")
    sources = [
        {"item": "行情/市值/PE·PB", "source": "AkShare 新浪日线 + TDX quotes", "time": fetch_time},
        {"item": "利润表(营收/成本/净利)", "source": "TDX ph_agf10_cw_lyb", "time": fetch_time},
        {"item": "现金流量表", "source": "TDX ph_agf10_cw_xjllb", "time": fetch_time},
        {"item": "资金流向(主力净流入)", "source": "TDX tdxf10_gg_jyds", "time": fetch_time},
        {"item": "十大流通股东", "source": "TDX tdxf10_gg_gdyj", "time": fetch_time},
        {"item": "分红送股", "source": "TDX tdxf10_gg_fhrz", "time": fetch_time},
        {"item": "同行估值与市值", "source": "TDX tdx_indicator_select", "time": fetch_time},
        {"item": "杜邦/估值/分位计算", "source": "本地规则化计算（零 token）", "time": fetch_time},
    ]
    if os.path.exists(research_file):
        sources.append({"item": "互联网研究(研报/新闻/公告/宏观)", "source": "TDX wenda 检索", "time": fetch_time})
    data["data_sources"] = sources
    if "cashflow_annual" in fin:
        data["cashflow"] = {"fields": ["end_date","n_cashflow_act"], "items": [list(r) for r in fin["cashflow_annual"]]}
    if "moneyflow_20d" in fin:
        data["moneyflow"] = {"fields": ["trade_date","net_mf_amount"], "items": [list(r) for r in fin["moneyflow_20d"]]}
    if "industry_peers" in fin:
        # 统一字段名：peer_model 使用 mv_bn(亿元)；fin 中为 total_mv(元)，此处换算
        peers = []
        for p in fin["industry_peers"]:
            np_ = dict(p)
            if "total_mv" in np_ and "mv_bn" not in np_:
                np_["mv_bn"] = round(np_["total_mv"] / 1e8, 1)
            peers.append(np_)
        data["industry_peers"] = {"industry": industry, "peers": peers}
    if "top10_holders" in fin:
        t10_end = fin.get("top10_end_date", "")
        data["top10_holders"] = {
            "fields": ["end_date","holder_name","hold_amount","hold_ratio"],
            "items": [[t10_end, name, amt, round(amt / shares * 100, 2)] for name, amt in fin["top10_holders"]],
        }
    if "dividend_rows" in fin:
        data["dividend"] = {
            "fields": ["end_date","cash_div_tax","div_proc","stk_div","ann_date"],
            "items": [list(r) for r in fin["dividend_rows"]],
        }

    # P0-1：多维交叉验证——读取 TDX wenda 检索结果组装 web_research
    if os.path.exists(research_file):
        with open(research_file, encoding="utf-8") as f:
            res = json.load(f)
        sections = {}
        reports = res.get("reports", [])
        if reports:
            sections["analyst_views"] = "\n".join(
                f"- {r.get('title','')}（{r.get('date','')}）" for r in reports[:10])
        news = res.get("news", []) + res.get("notices", [])
        if news:
            sections["recent_events"] = "\n".join(
                f"- {n.get('title','')}（{n.get('date','')}）" for n in news[:12])
        macro = res.get("macro", [])
        if macro:
            sections["industry_dynamics"] = "\n".join(
                f"- {m.get('title','')}" for m in macro[:8])
        if sections:
            data["web_research"] = {
                "source": "通达信 wenda 检索",
                "sources": [r.get("title", "") for r in reports[:5]],
                "fallback_used": False,
                "structured_without_llm": True,
                "sections": sections,
            }
            print(f"  web_research: {len(sections)} 个章节（研报{len(reports)}/新闻公告{len(news)}/宏观{len(macro)}）")

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
    custodian = fin.get("custodian", "")
    found_date = fin.get("found_date") or fin.get("establish_date", "")
    m_fee = fin.get("m_fee")
    c_fee = fin.get("c_fee")
    total_fee = fin.get("total_fee")
    aum_yi = fin.get("aum_yi")
    total_share_yi = fin.get("total_share_yi")
    turnover_rate = fin.get("turnover_rate")

    daily = fetch_etf_daily(code, days=300)
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

    # 场内实时状态：优先读 TDX 落盘的实时行情快照（零 token，已落盘 tdx_raw/<code>_quote.json）。
    # 快照含 现价/IOPV/成交额/换手率，全部来自同一时刻，可直接估算单日溢折率。
    # 字段说明：current_price=HQInfo.Now(现价)；prev_close=HQInfo.Close(昨收)；iopv=HQInfo.Jjjz。
    quote_file = os.path.join(PROJECT_DIR, "tdx_raw", f"{code}_quote.json")
    q_price = q_change = q_amount = q_turnover = q_iopv = None
    if os.path.exists(quote_file):
        with open(quote_file, encoding="utf-8") as f:
            q = json.load(f)
        q_price = q.get("current_price"); q_change = q.get("change_pct")
        q_amount = q.get("amount"); q_turnover = q.get("turnover_rate"); q_iopv = q.get("iopv")
        turnover_rate = q_turnover if q_turnover is not None else turnover_rate
        print(f"  实时行情来自 TDX 落盘快照(日期 {q.get('quote_date')}, 现价 {q_price})", flush=True)
    else:
        # 回退：由日线末两根算涨跌/成交额
        q_price = float(daily["close"].iloc[-1])
        q_change = round((q_price / float(daily["close"].iloc[-2]) - 1) * 100, 2) if len(daily) >= 2 else "N/A"
        q_amount = float(daily["amount"].iloc[-1]) if "amount" in daily.columns and pd.notna(daily["amount"].iloc[-1]) else "N/A"

    rt = {"price": q_price, "prev_close": q.get("prev_close") if os.path.exists(quote_file) else None,
          "change_pct": q_change, "amount": q_amount,
          "turnover_rate": q_turnover, "iopv": q_iopv, "source": "tdx_quote_snapshot"}

    # 指数估值历史（TDX 落盘，tdx_raw/<指数>_index_pe.json）：用于 PE 历史分位。
    # 字段为 [trade_date, pe]（TDX ph_agf10_gzfx 返回的为 PE 历史序列）。
    index_dailybasic = None
    pe_file = os.path.join(PROJECT_DIR, "tdx_raw", f"{idx_code.split('.')[0]}_index_pe.json")
    if os.path.exists(pe_file):
        with open(pe_file, encoding="utf-8") as f:
            pe = json.load(f)
        pdf = pd.DataFrame(pe["items"], columns=pe["fields"])
        pdf["trade_date"] = pdf["trade_date"].astype(str)
        pdf["pe"] = pd.to_numeric(pdf["pe"], errors="coerce")
        index_dailybasic = {"fields": ["trade_date", "pe"],
                            "items": pdf[["trade_date", "pe"]].values.tolist()}
        print(f"  指数PE历史来自 TDX 落盘({len(pdf)}行), 最新PE {pdf['pe'].dropna().iloc[-1]}", flush=True)

    data = {
        "ts_code": ts_code, "index_code": idx_code, "fetch_time": datetime.now().isoformat(),
        "basic": {"fields": ["name","management","fund_type","benchmark","custodian","found_date",
                             "m_fee","c_fee","total_fee","aum_yi","total_share_yi","turnover_rate","iopv"],
                  "items": [[name, mgmt, "ETF", idx_name, custodian, found_date,
                             m_fee, c_fee, total_fee, aum_yi, total_share_yi, q_turnover, q_iopv]]},
        "daily": {"fields": list(daily.columns), "items": _items(daily)},
        "index_daily": {"fields": ["trade_date","close"], "items": _items(idx)},
        "realtime_quote": rt,
    }
    if index_dailybasic is not None:
        data["index_dailybasic"] = index_dailybasic

    # 单日溢折率估算（收盘价 vs IOPV，均来自同一 TDX 快照；历史分位需 NAV 日度序列，此处留空）
    if q_price is not None and q_iopv:
        try:
            prem = round((float(q_price) - float(q_iopv)) / float(q_iopv) * 100, 2)
            data["premium_disc"] = {
                "current_premium": prem,
                "premium_percentile": None,
                "max_premium": None,
                "min_premium": None,
                "avg_premium": None,
                "note": "基于TDX快照现价与IOPV估算（单日），历史分位需单位净值日度序列",
            }
            print(f"  溢折率≈{prem}% (收盘 {q_price} vs IOPV {q_iopv})", flush=True)
        except Exception as e:
            print(f"  溢折率计算失败: {e}", flush=True)

    # A：尝试补 nav（单位净值）→ 溢价/折价。ETF 通常无 open_fund 净值，失败/空则跳过(B兜底N/A)
    try:
        nav = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值")
        if nav is not None and not nav.empty:
            nav = nav.rename(columns={"净值日期":"nav_date","单位净值":"unit_nav","累计净值":"accum_nav"})
            nav["nav_date"] = nav["nav_date"].astype(str).str.replace("-","")
            cols = ["nav_date"] + [c for c in ["unit_nav","accum_nav"] if c in nav.columns]
            data["nav"] = {"fields": cols, "items": _items(nav[cols].tail(250))}
            print(f"  nav={len(nav)} 行", flush=True)
        else:
            print("  nav: 空，跳过", flush=True)
    except Exception as e:
        print(f"  nav 取数失败: {e}", flush=True)

    # A：尝试补 portfolio（持仓 → 成分集中度）
    try:
        pf = ak.fund_portfolio_hold_em(symbol=code, date="2025")
        if pf is not None and not pf.empty:
            # 列名：股票代码/股票名称/占净值比例
            rename_map = {}
            for c in pf.columns:
                cl = c.lower()
                if "代码" in c or "code" in cl: rename_map[c] = "ts_code"
                elif "名称" in c or "name" in cl: rename_map[c] = "name"
                elif "比例" in c or "weight" in cl: rename_map[c] = "weight"
                elif "日期" in c or "date" in cl: rename_map[c] = "end_date"
            pf = pf.rename(columns=rename_map)
            pf["end_date"] = pf["end_date"].astype(str).str.replace("-","") if "end_date" in pf.columns else "N/A"
            pf["weight"] = pd.to_numeric(pf.get("weight", 0), errors="coerce")
            cols = [c for c in ["end_date","ts_code","name","weight"] if c in pf.columns]
            data["portfolio"] = {"fields": cols, "items": _items(pf[cols].head(20))}
            print(f"  portfolio={len(pf)} 行")
        else:
            print("  portfolio: 空，跳过")
    except Exception as e:
        print(f"  portfolio 取数失败: {e}")

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
