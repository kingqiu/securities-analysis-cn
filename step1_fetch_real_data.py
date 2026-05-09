#!/usr/bin/env python3
"""
步骤1：获取真实数据并保存到文件
请在本地运行此脚本，它会将真实数据保存为 JSON 文件
"""

import requests
import json
from datetime import datetime, timedelta
import pandas as pd
import time
import re
from config import TUSHARE_API_URL as API_URL, TUSHARE_API_TOKEN as API_TOKEN

# API 调用计数器
api_call_count = 0


def call_api(api_name, params, fields=""):
    """调用 API"""
    global api_call_count
    api_call_count += 1

    data = {
        "api_name": api_name,
        "token": API_TOKEN,
        "params": params,
        "fields": fields
    }

    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(API_URL, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        if result.get("code") == 0:
            return result["data"]
        else:
            print(f"✗ API 错误 ({api_name}): {result.get('msg')}")
            return None

    except Exception as e:
        print(f"✗ API 调用失败 ({api_name}): {str(e)}")
        return None


def _to_float(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _calc_nav_returns(nav_items, nav_fields):
    if not nav_items:
        return {"1M": None, "3M": None, "6M": None}
    nav_df = pd.DataFrame(nav_items, columns=nav_fields)
    if "unit_nav" not in nav_df.columns or "nav_date" not in nav_df.columns:
        return {"1M": None, "3M": None, "6M": None}
    nav_df = nav_df.sort_values("nav_date").copy()
    nav_df["unit_nav"] = pd.to_numeric(nav_df["unit_nav"], errors="coerce")
    nav_df = nav_df.dropna(subset=["unit_nav"])
    if nav_df.empty:
        return {"1M": None, "3M": None, "6M": None}

    latest = nav_df["unit_nav"].iloc[-1]
    out = {}
    for k, days in (("1M", 21), ("3M", 63), ("6M", 126)):
        if len(nav_df) > days:
            past = nav_df["unit_nav"].iloc[-days]
            out[k] = round((latest / past - 1) * 100, 2) if past else None
        else:
            out[k] = None
    return out


def _extract_theme_keywords(fund_name, index_code):
    cleaned = fund_name or ""
    for w in ["ETF", "基金", "联接", "增强", "指数", "A", "C", "嘉实", "华夏", "易方达", "汇添富", "南方", "广发", "富国", "华宝", "景顺", "前海", "开源", "摩根"]:
        cleaned = cleaned.replace(w, "")

    keywords = []
    for kw in ["科创", "芯片", "半导体", "沪深300", "300", "中证500", "500", "创业板", "红利", "价值", "消费", "医药", "新能源", "军工", "券商", "银行", "酒"]:
        if kw in (fund_name or ""):
            keywords.append(kw)

    if not keywords:
        parts = [p for p in re.split(r"[^一-龥A-Za-z0-9]+", cleaned) if len(p) >= 2]
        keywords.extend(parts[:3])

    if index_code == "000688.SH":
        keywords.extend(["科创", "芯片", "半导体"])
    elif index_code == "000300.SH":
        keywords.extend(["沪深300", "300"])
    elif index_code == "000905.SH":
        keywords.extend(["中证500", "500"])

    uniq = []
    for k in keywords:
        if k and k not in uniq:
            uniq.append(k)
    return uniq[:6]


def fetch_all_data(ts_code, index_code):
    """获取所有数据"""
    print("=" * 80)
    print("获取 ETF 真实数据")
    print("=" * 80)
    print(f"ETF 代码: {ts_code}")
    print(f"指数代码: {index_code}")
    print("=" * 80)

    data = {
        "ts_code": ts_code,
        "index_code": index_code,
        "fetch_time": datetime.now().isoformat()
    }

    # 1. 基础信息
    print("\n1/10 获取基础信息...")
    basic_data = call_api("fund_basic", {"ts_code": ts_code})
    if basic_data and basic_data.get("items"):
        data["basic"] = {
            "fields": basic_data["fields"],
            "items": basic_data["items"]
        }
        print(f"  ✓ 基础信息: {len(basic_data['items'])} 条")
    else:
        print("  ✗ 基础信息获取失败")
        return None

    # 2. 基金经理
    print("2/10 获取基金经理信息...")
    manager_data = call_api("fund_manager", {"ts_code": ts_code})
    if manager_data:
        data["manager"] = {
            "fields": manager_data["fields"],
            "items": manager_data["items"]
        }
        print(f"  ✓ 基金经理: {len(manager_data['items'])} 条")

    # 3. 净值数据（近3年）
    print("3/10 获取净值数据...")
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=1095)).strftime("%Y%m%d")
    nav_data = call_api("fund_nav", {"ts_code": ts_code, "start_date": start_date, "end_date": end_date})
    if nav_data:
        data["nav"] = {
            "fields": nav_data["fields"],
            "items": nav_data["items"]
        }
        print(f"  ✓ 净值数据: {len(nav_data['items'])} 条")

    # 4. 日线行情
    print("4/10 获取日线行情...")
    daily_data = call_api("fund_daily", {"ts_code": ts_code, "start_date": start_date, "end_date": end_date})
    if daily_data:
        data["daily"] = {
            "fields": daily_data["fields"],
            "items": daily_data["items"]
        }
        print(f"  ✓ 日线行情: {len(daily_data['items'])} 条")

    # 5. 持仓数据
    print("5/10 获取持仓数据...")
    portfolio_data = call_api("fund_portfolio", {"ts_code": ts_code})
    if portfolio_data:
        data["portfolio"] = {
            "fields": portfolio_data["fields"],
            "items": portfolio_data["items"]
        }
        print(f"  ✓ 持仓数据: {len(portfolio_data['items'])} 条")

    # 6. 规模数据
    print("6/10 获取规模数据...")
    share_data = call_api("fund_share", {"ts_code": ts_code})
    if share_data:
        data["share"] = {
            "fields": share_data["fields"],
            "items": share_data["items"]
        }
        print(f"  ✓ 规模数据: {len(share_data['items'])} 条")

    # 7. 申购赎回
    print("7/10 获取申购赎回数据...")
    sales_vol_data = call_api("fund_sales_vol", {"ts_code": ts_code})
    if sales_vol_data:
        data["sales_vol"] = {
            "fields": sales_vol_data["fields"],
            "items": sales_vol_data["items"]
        }
        print(f"  ✓ 申购赎回: {len(sales_vol_data['items'])} 条")

    # 8. 分红数据
    print("8/10 获取分红数据...")
    div_data = call_api("fund_div", {"ts_code": ts_code})
    if div_data:
        data["div"] = {
            "fields": div_data["fields"],
            "items": div_data["items"]
        }
        print(f"  ✓ 分红数据: {len(div_data['items'])} 条")

    # 9. 指数数据
    print("9/10 获取指数数据...")
    index_daily_data = call_api("index_daily", {"ts_code": index_code, "start_date": start_date, "end_date": end_date})
    if index_daily_data:
        data["index_daily"] = {
            "fields": index_daily_data["fields"],
            "items": index_daily_data["items"]
        }
        print(f"  ✓ 指数数据: {len(index_daily_data['items'])} 条")

    # 10. 指数成分权重
    print("10/11 获取指数成分权重...")
    index_weight_data = call_api("index_weight", {"index_code": index_code})
    if index_weight_data:
        data["index_weight"] = {
            "fields": index_weight_data["fields"],
            "items": index_weight_data["items"][:100]  # 只保存前100条
        }
        print(f"  ✓ 指数权重: {len(index_weight_data['items'])} 条（保存前100条）")

    # 10.5. 指数估值数据（新增）
    print("10.5/11 获取指数估值数据...")
    index_dailybasic_data = call_api("index_dailybasic", {"ts_code": index_code, "start_date": start_date, "end_date": end_date})
    if index_dailybasic_data:
        data["index_dailybasic"] = {
            "fields": index_dailybasic_data["fields"],
            "items": index_dailybasic_data["items"]
        }
        print(f"  ✓ 指数估值: {len(index_dailybasic_data['items'])} 条")
    else:
        print(f"  ✗ 指数估值数据获取失败（可能该指数不支持估值数据）")

    # 11. 获取持仓股票的名称（优化方法：批量获取所有股票）
    print("11/13 获取股票名称映射表...")
    stock_names = {}

    try:
        # 获取上交所所有股票
        print("  获取上交所股票...")
        sse_data = call_api("stock_basic", {"exchange": "SSE"})
        if sse_data and sse_data.get("items"):
            for item in sse_data["items"]:
                if len(item) > 2:
                    stock_names[item[0]] = item[2]  # ts_code -> name
            print(f"  ✓ 上交所: {len(stock_names)} 只")

        # 获取深交所所有股票
        print("  获取深交所股票...")
        szse_data = call_api("stock_basic", {"exchange": "SZSE"})
        if szse_data and szse_data.get("items"):
            for item in szse_data["items"]:
                if len(item) > 2:
                    stock_names[item[0]] = item[2]  # ts_code -> name
            print(f"  ✓ 深交所: {len(stock_names) - len(sse_data.get('items', []))} 只")

        data["stock_names"] = stock_names
        print(f"  ✓ 股票名称映射表: 总计 {len(stock_names)} 只")

        # 验证持仓股票是否都有名称
        if portfolio_data and portfolio_data.get("items"):
            portfolio_codes = set([item[3] for item in portfolio_data["items"] if len(item) > 3])
            matched = sum(1 for code in portfolio_codes if code in stock_names)
            print(f"  ✓ 持仓股票匹配: {matched}/{len(portfolio_codes)} = {matched/len(portfolio_codes)*100:.1f}%")

    except Exception as e:
        print(f"  ✗ 获取股票名称失败: {str(e)}")
        data["stock_names"] = {}

    # 12. 获取同类基金（同赛道候选池 + 潜力评分 Top5）
    print("12/13 获取同类基金数据...")
    similar_funds_data = call_api("fund_basic", {"market": "E"})  # E=场内基金
    if similar_funds_data and similar_funds_data.get("items"):
        fields = similar_funds_data["fields"]
        idx = {f: i for i, f in enumerate(fields)}

        name_idx = idx.get("name", 1)
        code_idx = idx.get("ts_code", 0)
        fee_idx = idx.get("m_fee")
        cfee_idx = idx.get("c_fee")
        list_idx = idx.get("list_date")

        base_name = ""
        if data.get("basic", {}).get("items"):
            base_name = data["basic"]["items"][0][name_idx] if len(data["basic"]["items"][0]) > name_idx else ""
        keywords = _extract_theme_keywords(base_name, index_code)
        print(f"  候选关键词: {keywords}")

        # 候选池：必须ETF且非当前基金，优先同赛道关键词匹配
        candidates = []
        fallback = []
        for item in similar_funds_data["items"]:
            code = item[code_idx] if len(item) > code_idx else ""
            name = item[name_idx] if len(item) > name_idx else ""
            if code == ts_code or "ETF" not in name:
                continue

            record = {"item": item, "code": code, "name": name}
            if any(k in name for k in keywords):
                candidates.append(record)
            else:
                fallback.append(record)

        pool = candidates[:20]
        if len(pool) < 20:
            pool.extend(fallback[: max(0, 20 - len(pool))])

        scored = []
        similar_nav_data = {}

        for rec in pool:
            fund_code = rec["code"]
            item = rec["item"]

            nav_data = call_api("fund_nav", {"ts_code": fund_code, "start_date": start_date, "end_date": end_date})
            if not (nav_data and nav_data.get("items")):
                continue

            similar_nav_data[fund_code] = {
                "fields": nav_data["fields"],
                "items": nav_data["items"][:250]
            }

            returns = _calc_nav_returns(nav_data["items"][:250], nav_data["fields"])
            r1m = returns.get("1M")
            r3m = returns.get("3M")
            r6m = returns.get("6M")

            m_fee = _to_float(item[fee_idx], 0.6) if fee_idx is not None and len(item) > fee_idx else 0.6
            c_fee = _to_float(item[cfee_idx], 0.1) if cfee_idx is not None and len(item) > cfee_idx else 0.1
            total_fee = m_fee + c_fee

            listed_days = 365
            if list_idx is not None and len(item) > list_idx and item[list_idx]:
                try:
                    d0 = datetime.strptime(str(item[list_idx]), "%Y%m%d")
                    listed_days = max(1, (datetime.now() - d0).days)
                except Exception:
                    pass

            similarity_bonus = 30 if any(k in rec["name"] for k in keywords) else 0
            momentum = (r1m or 0) * 0.25 + (r3m or 0) * 0.35 + (r6m or 0) * 0.40
            fee_score = max(0, 20 - total_fee * 20)
            maturity_score = min(15, listed_days / 120)

            score = round(similarity_bonus + momentum + fee_score + maturity_score, 2)

            scored.append({
                "item": item,
                "code": fund_code,
                "score": score,
                "returns": returns,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        top5 = scored[:5]

        if top5:
            selected_codes = {x["code"] for x in top5}
            selected_items = [x["item"] for x in top5]

            data["similar_funds"] = {
                "fields": fields,
                "items": selected_items
            }
            data["similar_nav_data"] = {k: v for k, v in similar_nav_data.items() if k in selected_codes}
            data["similar_selection_meta"] = {
                "method": "同赛道候选池+潜力评分Top5",
                "keywords": keywords,
                "top_scores": [
                    {
                        "ts_code": x["code"],
                        "score": x["score"],
                        "ret_1m": x["returns"].get("1M"),
                        "ret_3m": x["returns"].get("3M"),
                        "ret_6m": x["returns"].get("6M"),
                    }
                    for x in top5
                ],
            }

            print(f"  ✓ 同类基金（潜力Top5）: {len(selected_items)} 只")
            print(f"  ✓ 同类基金净值: {len(data['similar_nav_data'])} 只")

    return data


if __name__ == "__main__":
    import os

    ts_code = "510300.SH"
    index_code = "000300.SH"

    start_time = time.time()

    # 获取数据
    data = fetch_all_data(ts_code, index_code)

    if data:
        # 保存到文件
        current_dir = os.path.dirname(os.path.abspath(__file__))
        output_file = os.path.join(current_dir, "etf_real_data.json")

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        elapsed_time = time.time() - start_time

        print("\n" + "=" * 80)
        print("✓ 数据获取完成！")
        print(f"✓ 数据已保存到: {output_file}")
        print(f"✓ API 调用次数: {api_call_count} 次")
        print(f"✓ 耗时: {elapsed_time:.1f} 秒")
        print("=" * 80)
        print("\n💡 频次说明：")
        print("  - 120积分用户：每分钟限50次，每天限8000次")
        print("  - 本次调用：{} 次，完全在安全范围内".format(api_call_count))
        print("=" * 80)
        print("\n下一步：运行 step2_generate_report_from_real_data.py 生成报告")
    else:
        print("\n" + "=" * 80)
        print("✗ 数据获取失败")
        print("=" * 80)
