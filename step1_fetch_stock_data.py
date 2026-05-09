#!/usr/bin/env python3
"""
步骤1（股票版）：从 Tushare API 获取股票数据
"""

import requests
import json
from datetime import datetime, timedelta
import time
from config import TUSHARE_API_URL as API_URL, TUSHARE_API_TOKEN as API_TOKEN, STOCK_DAILY_DAYS, STOCK_FINANCIAL_YEARS
from config import api_rate_limiter

api_call_count = 0


def call_api(api_name, params, fields=""):
    global api_call_count
    api_call_count += 1
    api_rate_limiter.acquire()
    data = {
        "api_name": api_name,
        "token": API_TOKEN,
        "params": params,
        "fields": fields,
    }
    try:
        resp = requests.post(API_URL, json=data, headers={"Content-Type": "application/json"}, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            return result["data"]
        else:
            print(f"  ✗ API错误 ({api_name}): {result.get('msg')}")
    except Exception as e:
        print(f"  ✗ API调用失败 ({api_name}): {e}")
    return None


def fetch_stock_data(ts_code: str) -> dict:
    """获取股票全量分析数据，返回包含9种数据类型的字典"""
    print("=" * 80)
    print(f"获取股票数据: {ts_code}")
    print("=" * 80)

    end_date = datetime.now().strftime("%Y%m%d")
    daily_start = (datetime.now() - timedelta(days=STOCK_DAILY_DAYS * 2)).strftime("%Y%m%d")
    fin_start_year = datetime.now().year - STOCK_FINANCIAL_YEARS

    data = {"ts_code": ts_code, "fetch_time": datetime.now().isoformat()}

    # 1. 基本信息
    print("1/9 获取基本信息...")
    basic = call_api("stock_basic", {"ts_code": ts_code, "fields": "ts_code,name,area,industry,list_date,market"})
    if basic and basic.get("items"):
        data["basic"] = {"fields": basic["fields"], "items": basic["items"]}
        print(f"  ✓ {basic['items'][0][1]}")
    else:
        print("  ✗ 基本信息获取失败，终止")
        return None

    # 2. 日线行情
    print("2/9 获取日线行情...")
    daily = call_api("daily", {"ts_code": ts_code, "start_date": daily_start, "end_date": end_date})
    if daily:
        data["daily"] = {"fields": daily["fields"], "items": daily["items"][:STOCK_DAILY_DAYS]}
        print(f"  ✓ {len(data['daily']['items'])} 条")

    # 3. 每日估值指标（PE/PB/市值）
    print("3/9 获取估值指标...")
    daily_basic = call_api("daily_basic", {"ts_code": ts_code, "start_date": daily_start, "end_date": end_date})
    if daily_basic:
        data["daily_basic"] = {"fields": daily_basic["fields"], "items": daily_basic["items"][:STOCK_DAILY_DAYS]}
        print(f"  ✓ {len(data['daily_basic']['items'])} 条")

    # 4. 利润表
    print("4/9 获取利润表...")
    income = call_api("income", {"ts_code": ts_code, "start_date": f"{fin_start_year}0101", "end_date": end_date, "report_type": "1"})
    if income:
        data["income"] = {"fields": income["fields"], "items": income["items"]}
        print(f"  ✓ {len(income['items'])} 条")

    # 5. 资产负债表
    print("5/9 获取资产负债表...")
    balance = call_api("balancesheet", {"ts_code": ts_code, "start_date": f"{fin_start_year}0101", "end_date": end_date, "report_type": "1"})
    if balance:
        data["balancesheet"] = {"fields": balance["fields"], "items": balance["items"]}
        print(f"  ✓ {len(balance['items'])} 条")

    # 6. 现金流量表
    print("6/9 获取现金流量表...")
    cashflow = call_api("cashflow", {"ts_code": ts_code, "start_date": f"{fin_start_year}0101", "end_date": end_date, "report_type": "1"})
    if cashflow:
        data["cashflow"] = {"fields": cashflow["fields"], "items": cashflow["items"]}
        print(f"  ✓ {len(cashflow['items'])} 条")

    # 7. 财务指标（ROE/毛利率等）
    print("7/9 获取财务指标...")
    fina = call_api("fina_indicator", {"ts_code": ts_code, "start_date": f"{fin_start_year}0101", "end_date": end_date})
    if fina:
        data["fina_indicator"] = {"fields": fina["fields"], "items": fina["items"]}
        print(f"  ✓ {len(fina['items'])} 条")

    # 8. 前十大股东
    print("8/9 获取前十大股东...")
    holders = call_api("top10_holders", {"ts_code": ts_code})
    if holders:
        data["top10_holders"] = {"fields": holders["fields"], "items": holders["items"]}
        print(f"  ✓ {len(holders['items'])} 条")

    # 9. 行业指数（用于对比，取上证综指作为基准）
    print("9/10 获取行业基准指数...")
    index = call_api("index_daily", {"ts_code": "000001.SH", "start_date": daily_start, "end_date": end_date})
    if index:
        data["index_daily"] = {"fields": index["fields"], "items": index["items"][:STOCK_DAILY_DAYS]}
        print(f"  ✓ {len(data['index_daily']['items'])} 条")

    # 10. 行业可比估值（同行业股票最新PE/PB）
    print("10/10 获取行业可比估值...")
    try:
        industry = ""
        if data.get("basic", {}).get("items"):
            basic_fields = data["basic"]["fields"]
            basic_item = data["basic"]["items"][0]
            basic_dict = dict(zip(basic_fields, basic_item))
            industry = basic_dict.get("industry", "")

        if industry:
            # 拉全量 stock_basic，Python 侧过滤同行业
            all_stocks = call_api("stock_basic", {})
            if all_stocks and all_stocks.get("items"):
                sb_fields = all_stocks["fields"]
                sb_idx = {f: i for i, f in enumerate(sb_fields)}
                code_i = sb_idx.get("ts_code", 0)
                ind_i = sb_idx.get("industry", 4)

                peer_codes = [
                    item[code_i] for item in all_stocks["items"]
                    if len(item) > ind_i and item[ind_i] == industry and item[code_i] != ts_code
                ][:10]

                peer_start = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
                peer_vals = []
                for peer_code in peer_codes:
                    pr = call_api("daily_basic", {"ts_code": peer_code, "start_date": peer_start, "end_date": end_date})
                    if pr and pr.get("items"):
                        pf = pr["fields"]
                        pi = {f: i for i, f in enumerate(pf)}
                        latest = pr["items"][0]
                        pe_v = latest[pi["pe_ttm"]] if "pe_ttm" in pi else None
                        pb_v = latest[pi["pb"]] if "pb" in pi else None
                        peer_vals.append({"ts_code": peer_code, "pe_ttm": pe_v, "pb": pb_v})

                data["industry_peers"] = {
                    "industry": industry,
                    "peers": peer_vals,
                    "trade_date": end_date,
                }
                print(f"  ✓ 行业「{industry}」同类股票: {len(peer_vals)} 只")
            else:
                print(f"  ✗ 无法获取股票列表")
        else:
            print(f"  ✗ 行业信息为空，跳过")
    except Exception as e:
        print(f"  ✗ 行业可比数据获取失败: {e}")

    # ── 以下为增强数据（报告深度分析用） ──

    # 11. 主营业务构成（按产品分）
    print("11/20 获取主营业务构成...")
    mainbz_p = call_api("fina_mainbz", {"ts_code": ts_code, "type": "P"})
    if mainbz_p and mainbz_p.get("items"):
        data["mainbz_product"] = {"fields": mainbz_p["fields"], "items": mainbz_p["items"]}
        print(f"  ✓ {len(mainbz_p['items'])} 条（按产品）")
    # 按地区
    mainbz_d = call_api("fina_mainbz", {"ts_code": ts_code, "type": "D"})
    if mainbz_d and mainbz_d.get("items"):
        data["mainbz_region"] = {"fields": mainbz_d["fields"], "items": mainbz_d["items"]}
        print(f"  ✓ {len(mainbz_d['items'])} 条（按地区）")

    # 12. 分红送股历史
    print("12/20 获取分红历史...")
    div = call_api("dividend", {"ts_code": ts_code})
    if div and div.get("items"):
        data["dividend"] = {"fields": div["fields"], "items": div["items"]}
        print(f"  ✓ {len(div['items'])} 条")

    # 13. 业绩预告
    print("13/20 获取业绩预告...")
    forecast = call_api("forecast", {"ts_code": ts_code})
    if forecast and forecast.get("items"):
        data["forecast"] = {"fields": forecast["fields"], "items": forecast["items"]}
        print(f"  ✓ {len(forecast['items'])} 条")

    # 14. 股东人数变化
    print("14/20 获取股东人数...")
    holder_num = call_api("stk_holdernumber", {"ts_code": ts_code})
    if holder_num and holder_num.get("items"):
        data["holder_number"] = {"fields": holder_num["fields"], "items": holder_num["items"]}
        print(f"  ✓ {len(holder_num['items'])} 条")

    # 15. 主力资金流向（近30天）
    print("15/20 获取资金流向...")
    mf_start = (datetime.now() - timedelta(days=45)).strftime("%Y%m%d")
    moneyflow = call_api("moneyflow", {"ts_code": ts_code, "start_date": mf_start, "end_date": end_date})
    if moneyflow and moneyflow.get("items"):
        data["moneyflow"] = {"fields": moneyflow["fields"], "items": moneyflow["items"]}
        print(f"  ✓ {len(moneyflow['items'])} 条")

    # 16. 融资融券（近30天）
    print("16/20 获取融资融券...")
    margin = call_api("margin_detail", {"ts_code": ts_code, "start_date": mf_start, "end_date": end_date})
    if margin and margin.get("items"):
        data["margin"] = {"fields": margin["fields"], "items": margin["items"]}
        print(f"  ✓ {len(margin['items'])} 条")

    # 17. 大宗交易（近3个月）
    print("17/20 获取大宗交易...")
    bt_start = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
    block = call_api("block_trade", {"ts_code": ts_code, "start_date": bt_start, "end_date": end_date})
    if block and block.get("items"):
        data["block_trade"] = {"fields": block["fields"], "items": block["items"]}
        print(f"  ✓ {len(block['items'])} 条")

    # 18. 概念板块
    print("18/20 获取概念板块...")
    concept = call_api("concept_detail", {"ts_code": ts_code})
    if concept and concept.get("items"):
        data["concepts"] = {"fields": concept["fields"], "items": concept["items"]}
        print(f"  ✓ {len(concept['items'])} 个概念")

    # 19. 股权质押
    print("19/20 获取股权质押...")
    pledge = call_api("pledge_stat", {"ts_code": ts_code})
    if pledge and pledge.get("items"):
        data["pledge"] = {"fields": pledge["fields"], "items": pledge["items"][:10]}
        print(f"  ✓ 近 {min(10, len(pledge['items']))} 期")

    # 20. 审计意见
    print("20/21 获取审计意见...")
    audit = call_api("fina_audit", {"ts_code": ts_code})
    if audit and audit.get("items"):
        data["audit"] = {"fields": audit["fields"], "items": audit["items"][:5]}
        print(f"  ✓ 近 {min(5, len(audit['items']))} 期")

    # 21. 央视新闻（宏观环境参考）
    print("21/21 获取宏观新闻...")
    from datetime import date
    today_str = date.today().strftime("%Y%m%d")
    news = call_api("cctv_news", {"date": today_str})
    if news and news.get("items"):
        data["macro_news"] = {"fields": news["fields"], "items": news["items"][:10]}
        print(f"  ✓ {len(data['macro_news']['items'])} 条")
    else:
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
        news = call_api("cctv_news", {"date": yesterday})
        if news and news.get("items"):
            data["macro_news"] = {"fields": news["fields"], "items": news["items"][:10]}
            print(f"  ✓ {len(data['macro_news']['items'])} 条（昨日）")

    print(f"\n✓ 数据获取完成，共调用 {api_call_count} 次 API")
    return data


if __name__ == "__main__":
    import sys, os
    ts_code = sys.argv[1] if len(sys.argv) > 1 else "600519.SH"
    result = fetch_stock_data(ts_code)
    if result:
        out = f"temp_{ts_code.replace('.', '_')}_stock_data.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"已保存到 {out}")
