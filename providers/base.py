#!/usr/bin/env python3
"""
适配器抽象基类定义。

三大可替换组件：
1. DataProvider  - 数据源（行情、财务、股东等）
2. LLMProvider   - AI大模型（生成投资建议）
3. SearchProvider - 新闻搜索/研究（获取公司近期事件）
"""

from abc import ABC, abstractmethod


class DataProvider(ABC):
    """数据源适配器基类"""

    @abstractmethod
    def fetch_stock_data(self, ts_code: str) -> dict:
        """获取A股完整数据，返回标准化 dict（与现有 JSON 结构兼容）"""
        pass

    @abstractmethod
    def fetch_hk_stock_data(self, ts_code: str) -> dict:
        """获取港股完整数据"""
        pass

    @abstractmethod
    def fetch_etf_data(self, ts_code: str, index_code: str) -> dict:
        """获取ETF完整数据"""
        pass

    @abstractmethod
    def identify_security(self, ts_code: str) -> tuple:
        """
        识别证券类型。
        返回: (type_str, metadata_dict)
            type_str: "etf" | "stock" | "hk_stock"
            metadata_dict: {"name": ..., "industry": ..., ...}
        """
        pass

    @abstractmethod
    def search_by_name(self, name: str) -> str:
        """按名称搜索证券，返回标准化代码（如 600519.SH）"""
        pass


class LLMProvider(ABC):
    """AI大模型适配器基类"""

    @abstractmethod
    def chat(self, prompt: str, max_tokens: int = 1024) -> str:
        """
        发送 prompt，返回模型回复文本。
        失败时应返回 None（由调用方决定降级策略）。
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查服务是否可用（有 key 配置）"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称，用于日志显示"""
        pass


class SearchProvider(ABC):
    """新闻搜索/研究适配器基类"""

    @abstractmethod
    def search_company(self, company_name: str, ts_code: str, market: str = "A股") -> dict:
        """
        搜索公司近期信息。
        返回: {
            "status": "success" | "error" | "no_api_key",
            "raw_text": "原始文本",
            "sections": {
                "recent_events": "...",
                "industry_dynamics": "...",
                "analyst_views": "...",
                "risk_factors": "...",
                "catalysts": "...",
            }
        }
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查服务是否可用"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""
        pass
