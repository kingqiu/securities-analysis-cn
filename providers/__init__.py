#!/usr/bin/env python3
"""
Provider 工厂模块。
根据 config.py 中的配置，返回对应的适配器实例。
"""

from .base import DataProvider, LLMProvider, SearchProvider


def get_llm_provider() -> LLMProvider:
    """根据配置返回 LLM 实例"""
    from config import LLM_PROVIDER

    if LLM_PROVIDER == "minimax":
        from config import MINIMA_API_URL, MINIMA_MODEL, MINIMA_API_KEY
        from .llm_minimax import MiniMaxLLM
        return MiniMaxLLM(MINIMA_API_URL, MINIMA_API_KEY, MINIMA_MODEL)

    elif LLM_PROVIDER == "openai":
        from config import OPENAI_API_URL, OPENAI_API_KEY, OPENAI_MODEL
        from .llm_openai import OpenAILLM
        return OpenAILLM(OPENAI_API_URL, OPENAI_API_KEY, OPENAI_MODEL)

    else:
        raise ValueError(f"未知的 LLM Provider: {LLM_PROVIDER}。支持: minimax, openai")


def get_search_provider() -> SearchProvider:
    """根据配置返回搜索实例"""
    from config import SEARCH_PROVIDER

    llm = get_llm_provider()

    if SEARCH_PROVIDER == "ai_summary":
        from .search_ai import AISearchProvider
        return AISearchProvider(llm)

    elif SEARCH_PROVIDER == "tavily":
        from config import TAVILY_API_KEY
        from .search_tavily import TavilySearchProvider
        return TavilySearchProvider(TAVILY_API_KEY, llm)

    elif SEARCH_PROVIDER == "none":
        # 禁用搜索
        return _NoopSearchProvider()

    else:
        raise ValueError(f"未知的 Search Provider: {SEARCH_PROVIDER}。支持: ai_summary, tavily, none")


def get_data_provider() -> DataProvider:
    """根据配置返回数据源实例"""
    from config import DATA_PROVIDER

    if DATA_PROVIDER == "tushare":
        from config import TUSHARE_API_URL, TUSHARE_API_TOKEN
        from .data_tushare import TushareDataProvider
        return TushareDataProvider(TUSHARE_API_URL, TUSHARE_API_TOKEN)

    else:
        raise ValueError(f"未知的 Data Provider: {DATA_PROVIDER}。支持: tushare")


# ── 特殊实现：禁用搜索 ──

class _NoopSearchProvider(SearchProvider):
    """空实现：当用户选择 SEARCH_PROVIDER=none 时使用"""

    @property
    def name(self) -> str:
        return "None (disabled)"

    def is_available(self) -> bool:
        return False

    def search_company(self, company_name, ts_code, market="A股"):
        return {"status": "disabled", "summary": "搜索功能已禁用", "sections": {}}
