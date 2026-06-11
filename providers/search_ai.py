#!/usr/bin/env python3
"""
Search Provider: AI 联网总结（通过大模型的知识库获取公司信息）
这是默认的搜索方式，利用 LLM 自身知识来总结公司近期信息。
"""

import re
from .base import SearchProvider, LLMProvider


class AISearchProvider(SearchProvider):
    """通过 AI 大模型知识库获取公司研究信息（默认方式）"""

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    @property
    def name(self) -> str:
        return f"AI Summary (via {self._llm.name})"

    def is_available(self) -> bool:
        return self._llm.is_available()

    def search_company(self, company_name: str, ts_code: str, market: str = "A股", industry: str = "") -> dict:
        if not self._llm.is_available():
            return {"status": "no_api_key", "summary": "未配置 AI API Key，跳过互联网研究"}

        from datetime import date
        today = date.today().strftime("%Y年%m月%d日")

        prompt = f"""你是一位专业的证券分析师助手。今天日期是{today}。请基于你的知识，为以下公司提供近期重要信息汇总：

公司：{company_name}（{ts_code}，{market}市场）

请严格按照以下格式回答，每个部分都必须填写：

## 1. 公司近期重大事件
列出3-5条该公司最重要的近期新闻/公告/事件，按重要性排序。每条包含：大致时间、事件类型、简述。

## 2. 行业动态与竞争格局
分析该公司所在行业的当前态势：行业增速、政策风向、主要竞争对手动态。

## 3. 机构观点
汇总近期主要券商/机构对该公司的业务判断、盈利预测变化和核心逻辑；不要输出直接交易建议。

## 4. 潜在风险提示
列出3-5条该公司当前面临的主要风险因素。

## 5. 关键催化剂
列出未来3-6个月可能影响市场预期或经营验证的正面催化事件。

重要约束：
- 今天是{today}，"近期"是指最近6个月内的事件。
- 绝对不要列出超过1年前的旧事件。如果你无法确认某事件的确切时间，就不要列出。
- 如果你的知识截止日期较早，无法提供近期信息，请明确说明"信息截止于YYYY年MM月，近期动态请查阅公司公告"，不要用旧信息冒充近期事件。
- 如果某些信息你不确定或信息有限，请如实说明"信息有限"而非编造。"""

        text = self._llm.chat(prompt, max_tokens=3000)
        if not text:
            return {"status": "error", "summary": "AI 研究请求失败"}

        # 解析结构化内容
        sections = self._parse_sections(text)
        return {
            "status": "success",
            "source": "ai_summary",
            "raw_text": text,
            "sections": sections,
        }

    def _parse_sections(self, text: str) -> dict:
        """从 AI 回复中提取各个章节"""
        sections = {
            "recent_events": "",
            "industry_dynamics": "",
            "analyst_views": "",
            "risk_factors": "",
            "catalysts": "",
        }

        section_map = {
            "1": "recent_events",
            "2": "industry_dynamics",
            "3": "analyst_views",
            "4": "risk_factors",
            "5": "catalysts",
        }

        current_key = None
        current_lines = []

        for line in text.split("\n"):
            header_match = re.match(r"^##\s*(\d+)", line)
            if header_match:
                if current_key and current_lines:
                    sections[current_key] = "\n".join(current_lines).strip()
                num = header_match.group(1)
                current_key = section_map.get(num)
                current_lines = []
            elif current_key:
                current_lines.append(line)

        if current_key and current_lines:
            sections[current_key] = "\n".join(current_lines).strip()

        return sections
