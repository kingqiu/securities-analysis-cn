#!/usr/bin/env python3
"""
自动识别证券代码类型：ETF、A股 或 港股
支持输入：代码（如 510300、600519.SH、00700.HK）或名称（如 贵州茅台、腾讯控股、沪深300ETF）
"""

import requests
from config import TUSHARE_API_URL as API_URL, TUSHARE_API_TOKEN as API_TOKEN
from config import api_rate_limiter


def _call_api(api_name, params):
    api_rate_limiter.acquire()
    data = {
        "api_name": api_name,
        "token": API_TOKEN,
        "params": params,
        "fields": ""
    }
    try:
        resp = requests.post(API_URL, json=data, headers={"Content-Type": "application/json"}, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            return result["data"]
    except Exception:
        pass
    return None


def _is_code_like(text: str) -> bool:
    """判断输入是否像一个代码（纯数字、或带市场后缀）"""
    text = text.strip()
    if "." in text:
        parts = text.split(".")
        return parts[0].isdigit() and parts[1].upper() in ("SH", "SZ", "HK")
    return text.isdigit()


def search_by_name(name: str) -> str:
    """
    根据名称搜索证券代码。
    先查A股股票，再查基金（ETF），最后查港股。
    返回 ts_code 或 None。
    """
    name = name.strip()

    # 1. 搜索A股股票
    stock_data = _call_api("stock_basic", {})
    if stock_data and stock_data.get("items"):
        fields = stock_data["fields"]
        name_idx = fields.index("name") if "name" in fields else None
        code_idx = fields.index("ts_code") if "ts_code" in fields else 0
        if name_idx is not None:
            for item in stock_data["items"]:
                if name in item[name_idx]:
                    return item[code_idx]

    # 2. 搜索基金（ETF）
    fund_data = _call_api("fund_basic", {"market": "E"})
    if fund_data and fund_data.get("items"):
        fields = fund_data["fields"]
        name_idx = fields.index("name") if "name" in fields else None
        code_idx = fields.index("ts_code") if "ts_code" in fields else 0
        if name_idx is not None:
            for item in fund_data["items"]:
                if name in item[name_idx]:
                    return item[code_idx]

    # 3. 搜索港股
    hk_data = _call_api("hk_basic", {})
    if hk_data and hk_data.get("items"):
        fields = hk_data["fields"]
        name_idx = fields.index("name") if "name" in fields else None
        code_idx = fields.index("ts_code") if "ts_code" in fields else 0
        if name_idx is not None:
            for item in hk_data["items"]:
                if name in item[name_idx]:
                    return item[code_idx]

    return None


def normalize_code(code: str) -> str:
    """补全市场后缀：510300 → 510300.SH，00700 → 00700.HK"""
    code = code.strip().upper()
    if "." in code:
        return code
    # 6位数字：A股逻辑
    if code.isdigit() and len(code) == 6:
        if code.startswith(("5", "6", "9")):
            return f"{code}.SH"
        return f"{code}.SZ"
    # ≤5位纯数字：港股
    if code.isdigit() and len(code) <= 5:
        return f"{code.zfill(5)}.HK"
    if code.startswith(("5", "6", "9")):
        return f"{code}.SH"
    return f"{code}.SZ"


def resolve_input(user_input: str) -> str:
    """
    智能解析用户输入：
    - 如果像代码（纯数字/带后缀），直接 normalize
    - 如果像名称（含中文或英文单词），按名称搜索
    返回 ts_code 或抛出异常
    """
    user_input = user_input.strip()
    if not user_input:
        raise ValueError("输入不能为空")

    if _is_code_like(user_input):
        return normalize_code(user_input)

    # 按名称搜索
    print(f"正在搜索「{user_input}」...")
    ts_code = search_by_name(user_input)
    if ts_code:
        print(f"  ✓ 找到：{ts_code}")
        return ts_code

    raise ValueError(f"无法识别「{user_input}」，请检查名称或代码是否正确")


def identify(ts_code: str) -> tuple:
    """
    识别证券类型。

    返回: ("etf", metadata) 或 ("stock", metadata) 或 ("hk_stock", metadata)
    metadata 包含 name 及类型相关字段。
    """
    # 港股：.HK 后缀直接查 hk_basic
    if ts_code.endswith(".HK"):
        hk_data = _call_api("hk_basic", {"ts_code": ts_code})
        if hk_data and hk_data.get("items"):
            fields = hk_data["fields"]
            item = hk_data["items"][0]
            row = dict(zip(fields, item))
            return ("hk_stock", {
                "name": row.get("name", ts_code),
                "market": row.get("market", ""),
                "fullname": row.get("fullname", ""),
                "list_date": row.get("list_date", ""),
            })
        raise ValueError(f"无法识别港股代码 {ts_code}，请检查代码是否正确")

    # 先查基金表（ETF在场内基金中）
    fund_data = _call_api("fund_basic", {"ts_code": ts_code, "market": "E"})
    if fund_data and fund_data.get("items"):
        fields = fund_data["fields"]
        item = fund_data["items"][0]
        row = dict(zip(fields, item))
        return ("etf", {
            "name": row.get("name", ts_code),
            "fund_type": row.get("fund_type", ""),
            "management": row.get("management", ""),
            "benchmark": row.get("benchmark", ""),
        })

    # 再查股票表
    stock_data = _call_api("stock_basic", {"ts_code": ts_code})
    if stock_data and stock_data.get("items"):
        fields = stock_data["fields"]
        item = stock_data["items"][0]
        row = dict(zip(fields, item))
        return ("stock", {
            "name": row.get("name", ts_code),
            "industry": row.get("industry", ""),
            "area": row.get("area", ""),
            "list_date": row.get("list_date", ""),
        })

    raise ValueError(f"无法识别证券代码 {ts_code}，请检查代码是否正确")


if __name__ == "__main__":
    import sys
    user_input = sys.argv[1] if len(sys.argv) > 1 else "510300"
    ts_code = resolve_input(user_input)
    code_type, meta = identify(ts_code)
    print(f"输入: {user_input}")
    print(f"代码: {ts_code}")
    print(f"类型: {code_type}")
    print(f"信息: {meta}")
