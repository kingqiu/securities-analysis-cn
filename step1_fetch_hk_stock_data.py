#!/usr/bin/env python3
"""
步骤1（港股版）：从 Tushare API 获取港股数据
"""

import requests
import json
from datetime import datetime, timedelta
from config import TUSHARE_API_URL as API_URL, TUSHARE_API_TOKEN as API_TOKEN, STOCK_DAILY_DAYS, STOCK_FINANCIAL_YEARS

api_call_count = 0


def call_api(api_name, params, fields=""):
    global api_call_count
    api_call_count += 1
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


def fetch_hk_stock_data(ts_code: str) -> dict:
    """获取港股全量分析数据，返回包含6种数据类型的字典"""
    print("=" * 80)
    print(f"获取港股数据: {ts_code}")
    print("=" * 80)

    end_date = datetime.now().strftime("%Y%m%d")
    daily_start = (datetime.now() - timedelta(days=STOCK_DAILY_DAYS * 2)).strftime("%Y%m%d")
    fin_start_year = datetime.now().year - STOCK_FINANCIAL_YEARS

    data = {"ts_code": ts_code, "fetch_time": datetime.now().isoformat()}

    # 1. 基本信息
    print("1/6 获取基本信息...")
    basic = call_api("hk_basic", {"ts_code": ts_code})
    if basic and basic.get("items"):
        fields = basic["fields"]
        item = basic["items"][0]
        row = dict(zip(fields, item))
        data["basic"] = row
        print(f"  ✓ {row.get('name', ts_code)}")
    else:
        print("  ✗ 基本信息获取失败，终止")
        return None

    # 2. 日线行情
    print("2/6 获取日线行情...")
    daily = call_api("hk_daily", {"ts_code": ts_code, "start_date": daily_start, "end_date": end_date})
    if daily and daily.get("items"):
        data["daily"] = {"fields": daily["fields"], "items": daily["items"][:STOCK_DAILY_DAYS]}
        print(f"  ✓ {len(data['daily']['items'])} 条")
    else:
        print("  ✗ 日线行情获取失败")

    # 3. 财务指标（PE/PB/ROE等）
    print("3/6 获取财务指标...")
    fina = call_api("hk_fina_indicator", {"ts_code": ts_code, "start_date": f"{fin_start_year}0101", "end_date": end_date})
    if fina and fina.get("items"):
        data["fina_indicator"] = {"fields": fina["fields"], "items": fina["items"]}
        print(f"  ✓ {len(fina['items'])} 条")
    else:
        print("  ✗ 财务指标获取失败")

    # 4. 利润表（KV格式）
    print("4/6 获取利润表...")
    income = call_api("hk_income", {"ts_code": ts_code, "start_date": f"{fin_start_year}0101", "end_date": end_date})
    if income and income.get("items"):
        data["income"] = {"fields": income["fields"], "items": income["items"]}
        print(f"  ✓ {len(income['items'])} 条")
    else:
        print("  ✗ 利润表获取失败")

    # 5. 现金流量表（KV格式）
    print("5/6 获取现金流量表...")
    cashflow = call_api("hk_cashflow", {"ts_code": ts_code, "start_date": f"{fin_start_year}0101", "end_date": end_date})
    if cashflow and cashflow.get("items"):
        data["cashflow"] = {"fields": cashflow["fields"], "items": cashflow["items"]}
        print(f"  ✓ {len(cashflow['items'])} 条")
    else:
        print("  ✗ 现金流量表获取失败")

    # 6. 南向资金持仓
    print("6/9 获取南向资金持仓...")
    hold = call_api("hk_hold", {"ts_code": ts_code})
    if hold and hold.get("items"):
        # 按日期降序取最近60条
        items_sorted = sorted(hold["items"], key=lambda x: x[hold["fields"].index("trade_date")], reverse=True)
        data["hold"] = {"fields": hold["fields"], "items": items_sorted[:60]}
        print(f"  ✓ {len(data['hold']['items'])} 条")
    else:
        print("  ✗ 南向资金数据为空（该股票可能不在港股通范围内）")
        data["hold"] = {"fields": [], "items": []}

    # ── 以下为增强数据 ──

    # 7. 资产负债表
    print("7/9 获取资产负债表...")
    balance = call_api("hk_balancesheet", {"ts_code": ts_code, "start_date": f"{fin_start_year}0101", "end_date": end_date})
    if balance and balance.get("items"):
        data["balancesheet"] = {"fields": balance["fields"], "items": balance["items"]}
        print(f"  ✓ {len(balance['items'])} 条")
    else:
        print("  ✗ 资产负债表获取失败")

    # 8. 分红数据（从 fina_indicator 中已包含 divi_ratio/dividend_rate）
    # 港股的分红信息在 hk_fina_indicator 中已有 dps_hkd 字段
    # 此处补充获取概念/板块（尝试 concept_detail）
    print("8/9 获取概念板块...")
    concept = call_api("concept_detail", {"ts_code": ts_code})
    if concept and concept.get("items"):
        data["concepts"] = {"fields": concept["fields"], "items": concept["items"]}
        print(f"  ✓ {len(concept['items'])} 个概念")
    else:
        print("  ○ 无概念板块数据（港股通常无此数据）")

    # 9. 央视新闻（用于宏观环境参考）
    print("9/9 获取宏观新闻...")
    from datetime import date
    today_str = date.today().strftime("%Y%m%d")
    news = call_api("cctv_news", {"date": today_str})
    if news and news.get("items"):
        data["macro_news"] = {"fields": news["fields"], "items": news["items"][:10]}
        print(f"  ✓ {len(data['macro_news']['items'])} 条")
    else:
        # 尝试前一天
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
        news = call_api("cctv_news", {"date": yesterday})
        if news and news.get("items"):
            data["macro_news"] = {"fields": news["fields"], "items": news["items"][:10]}
            print(f"  ✓ {len(data['macro_news']['items'])} 条（昨日）")
        else:
            print("  ○ 无宏观新闻")

    print(f"\n✓ 数据获取完成，共调用 {api_call_count} 次 API")
    return data


if __name__ == "__main__":
    import sys
    ts_code = sys.argv[1] if len(sys.argv) > 1 else "09992.HK"
    result = fetch_hk_stock_data(ts_code)
    if result:
        out = f"temp_{ts_code.replace('.', '_')}_hk_data.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"已保存到 {out}")
