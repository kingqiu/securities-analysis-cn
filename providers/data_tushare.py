#!/usr/bin/env python3
"""
Data Provider: 小德法 Tushare API（默认数据源）
通过委托模式调用现有的 step1_fetch_*.py 和 identify_code_type.py 中的函数。

注意：现有 fetch 模块通过 config.py 读取 TUSHARE_API_URL 和 TUSHARE_API_TOKEN，
而 config.py 已从 .env 环境变量加载这些值，所以无需额外注入。
"""

from .base import DataProvider


class TushareDataProvider(DataProvider):
    """小德法 Tushare API 数据源适配器"""

    def __init__(self, api_url: str, api_token: str):
        self._api_url = api_url
        self._api_token = api_token

    def fetch_stock_data(self, ts_code: str) -> dict:
        """获取A股完整数据"""
        from step1_fetch_stock_data import fetch_stock_data
        return fetch_stock_data(ts_code)

    def fetch_hk_stock_data(self, ts_code: str) -> dict:
        """获取港股完整数据"""
        from step1_fetch_hk_stock_data import fetch_hk_stock_data
        return fetch_hk_stock_data(ts_code)

    def fetch_etf_data(self, ts_code: str, index_code: str) -> dict:
        """获取ETF完整数据"""
        from step1_fetch_real_data import fetch_all_data
        return fetch_all_data(ts_code, index_code)

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
