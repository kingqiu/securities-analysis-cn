#!/usr/bin/env python3
"""
互联网研究模块：搜索公司近期新闻、事件、研报，
通过 AI 总结为结构化的投资参考信息。

数据来源：
1. 央视新闻（宏观政策）→ 已在 data fetch 中获取
2. MiniMax AI 联网搜索 → 获取公司近期事件/研报观点
"""

import os
import json
import requests
from config import MINIMA_API_URL, MINIMA_MODEL, MINIMA_API_KEY


def search_company_news(company_name: str, ts_code: str, market: str = "A股") -> dict:
    """
    通过 MiniMax AI 获取公司近期重要新闻、事件、研报观点。
    返回结构化的研究摘要。
    """
    if not MINIMA_API_KEY:
        return {"status": "no_api_key", "summary": "未配置 AI API Key，跳过互联网研究"}

    prompt = f"""你是一位专业的证券分析师助手。请基于你的知识，为以下公司提供近期重要信息汇总：

公司：{company_name}（{ts_code}，{market}市场）

请严格按照以下格式回答，每个部分都必须填写：

## 1. 公司近期重大事件（近3个月）
列出3-5条最重要的公司事件（如业绩发布、产品发布、管理层变动、并购重组、监管处罚等）。每条事件包含大致时间和简述。

## 2. 行业动态与竞争格局
- 该公司所在行业的近期重要趋势
- 主要竞争对手及相对竞争力
- 行业政策变化

## 3. 机构观点汇总
列出2-3家知名券商/机构的近期研报观点（如有）：
- 评级（买入/增持/中性/减持）
- 目标价
- 核心逻辑

## 4. 潜在风险提示
列出3-5条该公司当前面临的主要风险因素。

## 5. 关键催化剂
列出未来3-6个月可能影响股价的正面催化事件。

注意：如果某些信息你不确定，请如实说明"信息有限"而非编造。"""

    headers = {
        "content-type": "application/json",
        "x-api-key": MINIMA_API_KEY,
        "anthropic-version": "2023-06-01",
    }

    payload = {
        "model": MINIMA_MODEL,
        "max_tokens": 3000,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = requests.post(
            f"{MINIMA_API_URL}/v1/messages",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()

        # 提取回复文本
        content = ""
        if "content" in result:
            for block in result["content"]:
                if block.get("type") == "text":
                    content += block["text"]

        if content:
            # 解析为结构化数据
            sections = parse_research_sections(content)
            return {
                "status": "success",
                "company": company_name,
                "ts_code": ts_code,
                "raw_text": content,
                "sections": sections,
            }
        else:
            return {"status": "empty_response", "summary": "AI 未返回有效内容"}

    except requests.exceptions.Timeout:
        return {"status": "timeout", "summary": "AI 请求超时"}
    except Exception as e:
        return {"status": "error", "summary": f"研究请求失败: {str(e)}"}


def parse_research_sections(text: str) -> dict:
    """将 AI 返回的文本解析为结构化的各部分"""
    sections = {
        "recent_events": "",
        "industry_dynamics": "",
        "analyst_views": "",
        "risk_factors": "",
        "catalysts": "",
    }

    current_section = None
    current_lines = []

    for line in text.split("\n"):
        stripped = line.strip()
        if "重大事件" in stripped or "近期事件" in stripped:
            if current_section and current_lines:
                sections[current_section] = "\n".join(current_lines)
            current_section = "recent_events"
            current_lines = []
        elif "行业动态" in stripped or "竞争格局" in stripped:
            if current_section and current_lines:
                sections[current_section] = "\n".join(current_lines)
            current_section = "industry_dynamics"
            current_lines = []
        elif "机构观点" in stripped or "券商" in stripped or "研报" in stripped:
            if current_section and current_lines:
                sections[current_section] = "\n".join(current_lines)
            current_section = "analyst_views"
            current_lines = []
        elif "风险提示" in stripped or "潜在风险" in stripped:
            if current_section and current_lines:
                sections[current_section] = "\n".join(current_lines)
            current_section = "risk_factors"
            current_lines = []
        elif "催化剂" in stripped or "催化事件" in stripped:
            if current_section and current_lines:
                sections[current_section] = "\n".join(current_lines)
            current_section = "catalysts"
            current_lines = []
        elif current_section:
            if stripped:
                current_lines.append(stripped)

    # 最后一个 section
    if current_section and current_lines:
        sections[current_section] = "\n".join(current_lines)

    return sections


if __name__ == "__main__":
    # 测试
    result = search_company_news("贵州茅台", "600519.SH", "A股")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
