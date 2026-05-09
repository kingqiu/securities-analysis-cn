#!/usr/bin/env python3
"""
Search Provider: Tavily API
通过 Tavily 搜索引擎 API 获取公司近期新闻，再用 LLM 总结。
Tavily 官网：https://tavily.com
"""

import requests
from .base import SearchProvider, LLMProvider


class TavilySearchProvider(SearchProvider):
    """Tavily 搜索 + LLM 总结适配器"""

    def __init__(self, api_key: str, llm: LLMProvider):
        self._api_key = api_key
        self._llm = llm

    @property
    def name(self) -> str:
        return "Tavily Search"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def search_company(self, company_name: str, ts_code: str, market: str = "A股") -> dict:
        if not self._api_key:
            return {"status": "no_api_key", "summary": "未配置 Tavily API Key，跳过互联网研究"}

        # 执行搜索
        query = f"{company_name} {ts_code} 最新消息 研报 业绩"
        search_results = self._search(query)
        if not search_results:
            return {"status": "error", "summary": "Tavily 搜索无结果"}

        # 用 LLM 总结搜索结果
        if self._llm and self._llm.is_available():
            return self._summarize_with_llm(company_name, ts_code, market, search_results)
        else:
            # 无 LLM 时直接返回原始结果
            raw_text = "\n".join([f"- {r['title']}: {r['content'][:100]}" for r in search_results[:5]])
            return {
                "status": "success",
                "raw_text": raw_text,
                "sections": {"recent_events": raw_text},
            }

    def _search(self, query: str, max_results: int = 8) -> list:
        """调用 Tavily API"""
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": max_results,
                    "include_answer": False,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except Exception as e:
            print(f"  ✗ Tavily 搜索失败: {e}")
            return []

    def _summarize_with_llm(self, company_name, ts_code, market, results):
        """用 LLM 总结搜索结果"""
        context = "\n\n".join([
            f"来源: {r.get('url', '')}\n标题: {r.get('title', '')}\n内容: {r.get('content', '')[:300]}"
            for r in results[:6]
        ])

        prompt = f"""你是一位专业的证券分析师。请基于以下搜索结果，为{company_name}（{ts_code}，{market}）总结投资相关信息。

搜索结果：
{context}

请按以下格式输出：
## 1. 近期重大事件
## 2. 行业动态与竞争格局
## 3. 机构观点
## 4. 潜在风险
## 5. 关键催化剂

每部分2-3句话即可。如某方面搜索结果中无相关信息，注明"搜索结果中未涉及"。"""

        text = self._llm.chat(prompt, max_tokens=2000)
        if not text:
            return {"status": "error", "summary": "LLM 总结失败"}

        # 简单解析
        import re
        sections = {
            "recent_events": "",
            "industry_dynamics": "",
            "analyst_views": "",
            "risk_factors": "",
            "catalysts": "",
        }
        section_map = {"1": "recent_events", "2": "industry_dynamics", "3": "analyst_views", "4": "risk_factors", "5": "catalysts"}
        current_key = None
        current_lines = []
        for line in text.split("\n"):
            m = re.match(r"^##\s*(\d+)", line)
            if m:
                if current_key and current_lines:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = section_map.get(m.group(1))
                current_lines = []
            elif current_key:
                current_lines.append(line)
        if current_key and current_lines:
            sections[current_key] = "\n".join(current_lines).strip()

        return {"status": "success", "raw_text": text, "sections": sections}
