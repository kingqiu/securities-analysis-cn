#!/usr/bin/env python3
"""
Data Provider: 小德法 Tushare API（默认数据源）
通过委托模式调用现有的 step1_fetch_*.py 和 identify_code_type.py 中的函数。

注意：现有 fetch 模块通过 config.py 读取 TUSHARE_API_URL 和 TUSHARE_API_TOKEN，
而 config.py 已从 .env 环境变量加载这些值，所以无需额外注入。
"""

from __future__ import annotations

from .base import DataProvider


class TushareDataProvider(DataProvider):
    """小德法 Tushare API 数据源适配器"""

    def __init__(self, api_url: str, api_token: str):
        self._api_url = api_url
        self._api_token = api_token

    def fetch_stock_data(self, ts_code: str) -> dict:
        """获取A股完整数据"""
        from step1_fetch_stock_data import fetch_stock_data
        data = fetch_stock_data(ts_code)
        return self._enhance_stock_data(data, ts_code)

    def fetch_hk_stock_data(self, ts_code: str) -> dict:
        """获取港股完整数据"""
        from step1_fetch_hk_stock_data import fetch_hk_stock_data
        data = fetch_hk_stock_data(ts_code)
        return self._enhance_hk_stock_data(data, ts_code)

    def fetch_etf_data(self, ts_code: str, index_code: str) -> dict:
        """获取ETF完整数据"""
        from step1_fetch_real_data import fetch_all_data
        data = fetch_all_data(ts_code, index_code)
        return self._enhance_etf_data(data, ts_code)

    def identify_security(self, ts_code: str) -> tuple:
        """识别证券类型"""
        from identify_code_type import identify
        return identify(ts_code)

    def search_by_name(self, name: str) -> str:
        """按名称搜索"""
        from identify_code_type import search_by_name
        result = search_by_name(name)
        if result:
            return result
        return None

    def _free_market_enabled(self) -> bool:
        try:
            from config import ENABLE_FREE_MARKET_DATA
            return bool(ENABLE_FREE_MARKET_DATA)
        except Exception:
            return True

    def _enhance_stock_data(self, data: dict | None, ts_code: str) -> dict | None:
        if not data or not self._free_market_enabled():
            return data
        try:
            from .free_market_data import fetch_a_realtime, record_source
            quote = fetch_a_realtime(ts_code)
            if quote:
                data["realtime_quote"] = quote
                record_source(data, quote.get("source", "free_a_realtime"), "success", "补充A股实时行情")
            else:
                record_source(data, "free_a_realtime", "skipped", "未获取到A股实时行情")
        except Exception as exc:
            try:
                from .free_market_data import record_source
                record_source(data, "free_a_realtime", "failed", str(exc))
            except Exception:
                pass
        return data

    def _enhance_hk_stock_data(self, data: dict | None, ts_code: str) -> dict | None:
        if not data or not self._free_market_enabled():
            return data
        try:
            from .free_market_data import fetch_hk_daily, fetch_hk_realtime, has_items, record_source

            quote = fetch_hk_realtime(ts_code)
            if quote:
                data["realtime_quote"] = quote
                record_source(data, quote.get("source", "free_hk_realtime"), "success", "补充港股实时行情")
            else:
                record_source(data, "free_hk_realtime", "skipped", "未获取到港股实时行情")

            if not has_items(data.get("daily")):
                daily = fetch_hk_daily(ts_code)
                if daily:
                    data["daily"] = daily
                    record_source(data, daily.get("source", "free_hk_daily"), "success", "Tushare港股日线缺失时补充日线")
                else:
                    record_source(data, "akshare_stock_hk_hist", "skipped", "未获取到港股日线")
        except Exception as exc:
            try:
                from .free_market_data import record_source
                record_source(data, "free_hk_market_data", "failed", str(exc))
            except Exception:
                pass
        return data

    def _enhance_etf_data(self, data: dict | None, ts_code: str) -> dict | None:
        if not data or not self._free_market_enabled():
            return data
        try:
            from .free_market_data import fetch_etf_daily, fetch_etf_realtime, has_items, record_source

            quote = fetch_etf_realtime(ts_code)
            if quote:
                data["realtime_quote"] = quote
                record_source(data, quote.get("source", "free_etf_realtime"), "success", "补充ETF实时行情")
            else:
                record_source(data, "free_etf_realtime", "skipped", "未获取到ETF实时行情")

            if not has_items(data.get("daily")):
                daily = fetch_etf_daily(ts_code)
                if daily:
                    data["daily"] = daily
                    record_source(data, daily.get("source", "free_etf_daily"), "success", "Tushare ETF日线缺失时补充日线")
                else:
                    record_source(data, "akshare_fund_etf_hist_em", "skipped", "未获取到ETF日线")
        except Exception as exc:
            try:
                from .free_market_data import record_source
                record_source(data, "free_etf_market_data", "failed", str(exc))
            except Exception:
                pass
        return data
