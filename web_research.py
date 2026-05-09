#!/usr/bin/env python3
"""
互联网研究模块（兼容入口）。
实际逻辑已迁移至 providers/search_*.py。
本文件保留 search_company_news 函数签名，通过 SearchProvider 委托调用。
"""

import json
from providers import get_search_provider


def search_company_news(company_name: str, ts_code: str, market: str = "A股") -> dict:
    """
    通过 SearchProvider 获取公司近期重要新闻、事件、研报观点。
    返回结构化的研究摘要。
    """
    provider = get_search_provider()
    if not provider.is_available():
        return {"status": "no_api_key", "summary": "未配置搜索服务，跳过互联网研究"}

    return provider.search_company(company_name, ts_code, market)


if __name__ == "__main__":
    # 测试
    result = search_company_news("贵州茅台", "600519.SH", "A股")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
