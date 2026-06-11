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

    if SEARCH_PROVIDER == "auto":
        from config import TAVILY_API_KEY
        from .search_ai import AISearchProvider
        from .search_tavily import TavilySearchProvider
        return _FallbackSearchProvider(
            primary=TavilySearchProvider(TAVILY_API_KEY, llm),
            fallback=AISearchProvider(llm),
        )

    elif SEARCH_PROVIDER == "ai_summary":
        from .search_ai import AISearchProvider
        return AISearchProvider(llm)

    elif SEARCH_PROVIDER == "tavily":
        from config import TAVILY_API_KEY
        from .search_ai import AISearchProvider
        from .search_tavily import TavilySearchProvider
        return _FallbackSearchProvider(
            primary=TavilySearchProvider(TAVILY_API_KEY, llm),
            fallback=AISearchProvider(llm),
        )

    elif SEARCH_PROVIDER == "none":
        # 禁用搜索
        return _NoopSearchProvider()

    else:
        raise ValueError(f"未知的 Search Provider: {SEARCH_PROVIDER}。支持: auto, tavily, ai_summary, none")


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

    def search_company(self, company_name, ts_code, market="A股", industry=""):
        return {"status": "disabled", "summary": "搜索功能已禁用", "sections": {}}


class _FallbackSearchProvider(SearchProvider):
    """搜索优先、AI降级。用于近期新闻和行业动态。"""

    def __init__(self, primary: SearchProvider, fallback: SearchProvider):
        self._primary = primary
        self._fallback = fallback

    @property
    def name(self) -> str:
        return f"{self._primary.name} -> {self._fallback.name}"

    def is_available(self) -> bool:
        return self._primary.is_available() or self._fallback.is_available()

    def search_company(self, company_name, ts_code, market="A股", industry=""):
        primary_result = None
        if self._primary.is_available():
            primary_result = self._primary.search_company(company_name, ts_code, market, industry)
            if primary_result.get("status") == "success":
                primary_result["source"] = primary_result.get("source", self._primary.name)
                primary_result["fallback_used"] = False
                return primary_result

        if self._fallback.is_available():
            fallback_result = self._fallback.search_company(company_name, ts_code, market, industry)
            fallback_result["fallback_used"] = True
            fallback_result["fallback_reason"] = (
                primary_result.get("summary") if primary_result else "Tavily未配置或不可用"
            )
            fallback_result["source"] = fallback_result.get("source", self._fallback.name)
            return fallback_result

        return {
            "status": "no_api_key",
            "summary": "未配置 Tavily API Key，且 AI 服务不可用，跳过互联网研究",
            "sections": {},
        }
