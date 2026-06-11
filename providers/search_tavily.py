#!/usr/bin/env python3
"""
Search Provider: Tavily API
通过 Tavily 搜索引擎 API 获取公司近期新闻，再用 LLM 总结。
Tavily 官网：https://tavily.com
"""

import requests
import re
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

    def search_company(self, company_name: str, ts_code: str, market: str = "A股", industry: str = "") -> dict:
        if not self._api_key:
            return {"status": "no_api_key", "summary": "未配置 Tavily API Key，跳过互联网研究"}

        industry = industry or self._infer_industry(company_name)
        company_results = self._collect_company_results(company_name, ts_code)
        industry_results = self._collect_industry_results(company_name, ts_code, industry)
        analyst_results = self._collect_analyst_results(company_name, ts_code)
        search_results = self._dedupe(company_results + industry_results + analyst_results)
        if not search_results:
            return {"status": "error", "summary": "Tavily 搜索无高相关结果"}

        sections = self._build_sections(company_name, industry, company_results, industry_results, analyst_results)
        return {
            "status": "success",
            "source": "tavily",
            "raw_text": "\n\n".join(v for v in sections.values() if v),
            "sources": self._format_sources(search_results),
            "sections": sections,
            "summary": "Tavily 结构化搜索摘要",
            "llm_summary_failed": False,
            "structured_without_llm": True,
        }

    def _summarize_intelligence_with_llm(self, company_name, ts_code, market, industry, company_results, industry_results, analyst_results):
        context = self._compact_context("公司事件", company_results[:4])
        context += "\n" + self._compact_context("行业动态", industry_results[:5])
        context += "\n" + self._compact_context("机构观点", analyst_results[:3])
        prompt = f"""你是证券研究助理。只能基于下方 Tavily 搜索片段，为{company_name}（{ts_code}，{market}，{industry or '未知行业'}）生成高质量信息动态。

{context}

要求：
- 不使用模型自身知识补新闻；没有证据就写“搜索结果未提供足够证据”。
- 不要罗列来源标题，要提炼“发生了什么 + 对公司/行业/股价可能意味着什么”。
- 对日期未标明的来源，不得写成近期事实，只能写成背景参考。
- 每节2-4条，短句，证券分析口吻。

请严格按以下标题输出：
## 1. 近期重大事件
## 2. 行业动态与竞争格局
## 3. 机构观点
## 4. 潜在风险因素
## 5. 关键催化剂"""
        text = self._llm.chat(prompt, max_tokens=1200)
        if not text:
            return None
        sections = self._parse_sections(text)
        return sections if any(sections.values()) else None

    def _compact_context(self, label, results):
        lines = [f"【{label}】"]
        for idx, item in enumerate(results, 1):
            title = self._clean_text(item.get("title") or "", 80)
            content = self._clean_text(item.get("content") or "", 160)
            if self._is_low_quality(title) or self._is_low_quality(content):
                continue
            date = self._date_label(item)
            source = self._source_name(item.get("url") or "")
            lines.append(f"{idx}. 日期:{date}；来源:{source}；标题:{title}；摘要:{content}")
        return "\n".join(lines)

    def _parse_sections(self, text):
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
            match = re.match(r"^##\s*(\d+)", line.strip())
            if match:
                if current_key and current_lines:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = section_map.get(match.group(1))
                current_lines = []
            elif current_key:
                current_lines.append(line)
        if current_key and current_lines:
            sections[current_key] = "\n".join(current_lines).strip()
        return sections

    def _collect_company_results(self, company_name, ts_code):
        queries = [
            f"{company_name} {ts_code} 2026 最新 公告 业绩 分红 提价 渠道 动销",
            f"{company_name} {ts_code} 近期 经营 价格 渠道 改革 风险",
        ]
        results = []
        for query in queries:
            results.extend(self._search(query, max_results=6))
        return self._rank_results(self._dedupe(self._filter_relevant(results, company_name, ts_code)))

    def _collect_industry_results(self, company_name, ts_code, industry):
        terms = self._industry_terms(industry)
        query_terms = " ".join(terms[:6])
        queries = [
            f"中国 {query_terms} 2026 最新 政策 批价 库存 动销 竞争格局",
            f"{query_terms} 行业 2026 春节 动销 分化 龙头 渠道 库存",
        ]
        results = []
        for query in queries:
            results.extend(self._search(query, max_results=6))
        return self._rank_results(self._dedupe(self._filter_by_terms(results, terms + [company_name])))

    def _collect_analyst_results(self, company_name, ts_code):
        results = self._search(f"{company_name} {ts_code} 2026 研报 评级 目标价 盈利预测", max_results=5)
        return self._rank_results(self._dedupe(self._filter_relevant(results, company_name, ts_code)))

    def _search(self, query: str, max_results: int = 8, recent: bool = False) -> list:
        """调用 Tavily API"""
        payload = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        if recent:
            payload.update({
                "topic": "news",
                "days": 90,
            })
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except Exception as e:
            if recent:
                return self._search(query, max_results=max_results, recent=False)
            print(f"  ✗ Tavily 搜索失败: {e}")
            return []

    def _dedupe(self, results):
        seen = set()
        deduped = []
        for item in results:
            url = item.get("url") or item.get("title")
            if not url or url in seen:
                continue
            seen.add(url)
            deduped.append(item)
        return deduped[:10]

    def _rank_results(self, results):
        return sorted(results, key=self._quality_score, reverse=True)

    def _quality_score(self, item):
        title = item.get("title") or ""
        content = item.get("content") or ""
        url = item.get("url") or ""
        text = title + " " + content
        score = 0
        preferred = ("stcn.com", "21jingji.com", "cls.cn", "news.cn", "pdf.dfcfw.com", "weeklyonstock.com")
        if any(domain in url for domain in preferred):
            score += 3
        if item.get("published_date"):
            score += 2
        if re.search(r"202[5-6]", text):
            score += 2
        for word in ("批价", "库存", "动销", "渠道", "提价", "分红", "业绩", "改革", "春节", "分化", "回暖", "寻底"):
            if word in text:
                score += 1
        if self._is_low_value_source(item):
            score -= 10
        return score

    def _filter_relevant(self, results, company_name, ts_code):
        code_core = (ts_code or "").split(".")[0]
        tokens = [company_name, ts_code, code_core]
        tokens = [t.lower() for t in tokens if t]
        relevant = []
        for item in results:
            haystack = " ".join([
                str(item.get("title") or ""),
                str(item.get("content") or ""),
                str(item.get("url") or ""),
            ]).lower()
            if any(token in haystack for token in tokens):
                relevant.append(item)
        return relevant

    def _filter_by_terms(self, results, terms):
        tokens = [t.lower() for t in terms if t]
        relevant = []
        for item in results:
            haystack = " ".join([
                str(item.get("title") or ""),
                str(item.get("content") or ""),
                str(item.get("url") or ""),
            ]).lower()
            if any(token in haystack for token in tokens):
                relevant.append(item)
        return relevant

    def _infer_industry(self, company_name):
        if any(name in company_name for name in ("茅台", "五粮液", "泸州老窖", "汾酒", "洋河")):
            return "白酒"
        if any(name in company_name for name in ("腾讯", "阿里", "美团", "京东", "网易", "快手", "百度")):
            return "互联网"
        return ""

    def _industry_terms(self, industry):
        if industry == "白酒":
            return ["白酒", "高端白酒", "茅台", "五粮液", "泸州老窖", "批价", "库存", "动销"]
        if industry == "互联网":
            return ["互联网", "游戏", "广告", "云计算", "AI", "腾讯", "社交", "视频号"]
        if industry:
            return [industry, f"{industry}行业", "龙头", "政策", "供需", "价格", "竞争格局"]
        return ["行业", "龙头", "政策", "供需", "价格", "竞争格局"]

    def _build_sections(self, company_name, industry, company_results, industry_results, analyst_results):
        company_cards = self._cards(company_results, limit=3, category="company")
        industry_cards = self._cards(industry_results, limit=4, category="industry")
        analyst_cards = self._cards(analyst_results, limit=3, category="analyst")

        risk_cards = [c for c in company_cards + industry_cards if c["tone"] in ("风险", "中性偏负")]
        catalyst_cards = [c for c in company_cards + industry_cards if c["tone"] in ("正面", "中性偏正")]

        return {
            "recent_events": self._render_cards(
                company_cards,
                f"Tavily 未获得足够高质量的 {company_name} 近期公司事件来源。",
            ),
            "industry_dynamics": self._render_cards(
                industry_cards,
                f"Tavily 未获得足够高质量的{industry or '所属'}行业动态来源。",
            ),
            "analyst_views": self._render_cards(
                analyst_cards,
                "Tavily 未获得足够高质量的近期机构观点来源。",
            ),
            "risk_factors": self._render_cards(
                risk_cards[:3],
                "当前 Tavily 高相关来源中未提取到明确新增风险；仍需关注价格、库存、消费需求和政策变量。",
            ),
            "catalysts": self._render_cards(
                catalyst_cards[:3],
                "当前 Tavily 高相关来源中未提取到明确短期催化；后续重点跟踪业绩、价格和渠道库存变化。",
            ),
        }

    def _cards(self, results, limit=4, category="general"):
        cards = []
        for item in results:
            if self._is_low_value_source(item):
                continue
            title = self._clean_text(item.get("title") or "", 90)
            content = self._clean_text(item.get("content") or "", 180)
            if not title or self._is_low_quality(title):
                continue
            if self._is_low_quality(content):
                content = ""
            summary = self._best_summary(title, content, category)
            if not summary or self._is_low_quality(summary):
                continue
            if self._is_old_background(summary):
                continue
            if not self._has_useful_signal(title + " " + summary, category):
                continue
            date = self._date_label(item)
            if self._is_stale_or_bad_date(date):
                continue
            tone = self._tone(title + " " + content)
            theme = self._theme(title + " " + summary)
            cards.append({
                "date": date,
                "theme": theme,
                "summary": summary,
                "tone": tone,
                "impact": self._impact(title + " " + content, tone),
                "source": self._source_name(item.get("url") or ""),
            })
            if len(cards) >= limit:
                break
        return cards

    def _render_cards(self, cards, empty):
        if not cards:
            return empty
        lines = []
        for card in cards:
            lines.append(
                f"- 【{card['theme']}】{card['date']}｜{card['summary']}。投研含义：{card['impact']}（信号：{card['tone']}；来源：{card['source']}）"
            )
        return "\n".join(lines)

    def _best_summary(self, title, content, category):
        text = content if len(content) >= 28 else title
        if (
            "请务必阅读正文之后" in text
            or "请务必仔细阅读正文之后" in text
            or "评级说明和重要声明" in text
            or text.startswith("证券研究报告")
            or "点赞收藏" in text
            or "下载界面新闻" in text
        ):
            text = title
        text = re.split(r"[。；;.!?]\s*", text)[0].strip()
        if len(text) < 18:
            text = title
        text = re.sub(r"^(登录|注册|首页|财经|要闻|股票|行情|数据)[ 　|｜、，,]+", "", text)
        if category == "company" and re.match(r"^(实现|同比|归母|营业|收入|净利润)", text):
            text = f"来源片段披露公司经营数据：{text}"
        if category == "analyst" and title and "研报" in title and len(text) < 40:
            text = title
        if len(text) > 120:
            text = text[:120].rstrip() + "..."
        return text

    def _theme(self, text):
        if any(word in text for word in ("批价", "价格", "提价", "吨价")):
            return "价格/批价"
        if any(word in text for word in ("库存", "动销", "春节", "渠道", "经销商", "直销")):
            return "渠道/动销"
        if any(word in text for word in ("营业总收入", "收入", "净利润", "业绩", "盈利预测")):
            return "业绩/预期"
        if any(word in text for word in ("分红", "回购", "股息")):
            return "股东回报"
        if any(word in text for word in ("政策", "消费税", "监管", "中央经济工作会议")):
            return "政策/需求"
        if any(word in text for word in ("竞争", "五粮液", "泸州老窖", "分化", "龙头")):
            return "竞争格局"
        return "综合信号"

    def _has_useful_signal(self, text, category):
        common = ("收入", "净利润", "业绩", "分红", "回购", "提价", "价格", "批价", "库存", "动销", "渠道", "改革", "增长", "下滑", "承压", "回暖", "拐点", "分化", "盈利预测", "评级", "目标价", "政策", "消费")
        if any(word in text for word in common):
            return True
        if category == "industry" and any(word in text for word in ("寻底", "顺周期", "春节", "高端白酒", "白酒")):
            return True
        if category == "analyst" and any(word in text for word in ("研报", "点评", "优于大市", "买入", "增持")):
            return True
        return False

    def _tone(self, text):
        positive = ("提价", "增长", "转暖", "回暖", "超预期", "稳定", "低于去年同期", "动销同比增长", "拐点", "看好", "上调")
        negative = ("下滑", "承压", "净卖出", "库存高", "批价下跌", "需求疲弱", "风险", "降级", "低于预期", "双降")
        policy = ("监管", "消费税", "政策", "限制", "处罚")
        pos = sum(1 for word in positive if word in text)
        neg = sum(1 for word in negative if word in text)
        pol = sum(1 for word in policy if word in text)
        if neg > pos:
            return "风险"
        if pos > neg:
            return "正面"
        if pol:
            return "中性偏负"
        return "中性"

    def _impact(self, text, tone):
        if "批价" in text or "价格" in text:
            return "影响估值锚和渠道信心，需跟踪终端价格是否持续稳定"
        if "库存" in text or "动销" in text:
            return "影响收入确认质量和渠道健康度，是短期景气度核心变量"
        if "寻底" in text or "筑底" in text:
            return "说明行业仍在修复阶段，买点更依赖价格企稳和需求验证"
        if "提价" in text:
            return "若渠道接受度良好，有利于利润率和盈利预期"
        if "业绩" in text or "盈利预测" in text:
            return "影响市场对未来利润增速和估值中枢的判断"
        if tone == "风险":
            return "可能压制估值或推迟买入时点，需要等待数据验证"
        if tone == "正面":
            return "有利于改善风险偏好，但仍需结合估值和成交确认"
        return "信息偏背景，需要和财务、价格、资金面交叉验证"

    def _date_label(self, item):
        date = item.get("published_date")
        if date:
            return str(date)[:16]
        text = f"{item.get('title') or ''} {item.get('content') or ''}"
        match = re.search(r"(20\d{2})[年/-](\d{1,2})[月/-]?(\d{1,2})?", text)
        if match:
            month = int(match.group(2))
            day = int(match.group(3)) if match.group(3) else None
            if month < 1 or month > 12 or (day is not None and (day < 1 or day > 31)):
                return "日期未标明"
            label = f"{match.group(1)}-{month:02d}"
            if day:
                label += f"-{day:02d}"
            return label
        return "日期未标明"

    def _is_stale_or_bad_date(self, date_label):
        if not date_label or date_label == "日期未标明":
            return False
        match = re.match(r"(20\d{2})", date_label)
        if not match:
            return False
        return int(match.group(1)) < 2025

    def _source_name(self, url):
        match = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
        return match.group(1) if match else "Tavily"

    def _summarize_with_llm(self, company_name, ts_code, market, results):
        """用 LLM 总结搜索结果"""
        context = "\n\n".join([
            f"来源: {r.get('url', '')}\n发布日期: {r.get('published_date', '未知')}\n标题: {self._clean_text(r.get('title', ''), 120)}\n内容: {self._clean_text(r.get('content', ''), 220)}"
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

        prompt += """

重要约束：
- 优先使用发布日期在最近90天内的搜索结果。
- 如果搜索结果没有明确日期，必须写成“搜索结果未显示明确日期”，不得把它表述为近期事实。
- 不要把1年以上的旧公告、旧研报写成“近期重大事件”；旧材料只能作为长期背景或估值历史参考。
- 所有行业动态必须来自搜索结果，不要使用模型自身知识补充新闻。"""

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

        return {
            "status": "success",
            "source": "tavily",
            "raw_text": text,
            "sources": self._format_sources(results),
            "sections": sections,
        }

    def _raw_result(self, results, note):
        lines = []
        for item in results[:6]:
            date = item.get("published_date") or "日期未标明"
            title = self._clean_text(item.get("title") or "未命名来源", 70)
            if title:
                lines.append(f"- {date}｜{title}")
        raw_text = "\n".join(lines)
        return {
            "status": "success",
            "source": "tavily",
            "raw_text": raw_text,
            "sources": self._format_sources(results),
            "sections": {
                "recent_events": note + "\n以下仅列出 Tavily 返回的相关来源标题；因摘要失败，不把网页正文片段写成近期事实。\n" + raw_text,
                "industry_dynamics": "Tavily 已返回相关来源，但自动总结失败。本节暂不额外生成行业判断，避免把未核实网页内容写成结论。",
            },
            "summary": note,
            "llm_summary_failed": True,
        }

    def _clean_text(self, value, max_len):
        text = str(value or "")
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
        text = re.sub(r"[|#*_`<>\\]+", " ", text)
        text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9，。；：、（）()《》“”\"'/%+.-]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
        nav_words = ("登录", "注册", "首页", "要闻", "股票", "新股", "期指", "期权", "行情", "数据", "全球", "美股", "港股", "期货", "外汇", "黄金", "银行", "基金吧", "博客", "视频")
        if sum(1 for word in nav_words if word in text) >= 4:
            return ""
        if len(text) > max_len:
            text = text[:max_len].rstrip() + "..."
        return text

    def _is_low_quality(self, text):
        if not text:
            return True
        if re.search(r"[\u0590-\u05ff\uac00-\ud7af]", text):
            return True
        chinese_count = len(re.findall(r"[\u4e00-\u9fff]", text))
        if len(text) >= 30 and chinese_count / max(len(text), 1) < 0.18:
            return True
        if len(re.findall(r"[\u4e00-\u9fff]\s+[\u4e00-\u9fff]", text)) >= 3:
            return True
        if re.match(r"^[0-9.%+/\- ]+$", text):
            return True
        repeated_symbols = len(re.findall(r"[-_=]{3,}", text))
        return repeated_symbols > 0

    def _is_low_value_source(self, item):
        title = self._clean_text(item.get("title") or "", 120)
        content = self._clean_text(item.get("content") or "", 240)
        url = item.get("url") or ""
        low_value_words = ("分红配股", "行情中心", "详细报价", "Detail Quote", "F10", "重大事项备忘", "免责声明")
        if any(word in title for word in low_value_words):
            return True
        if ("请务必阅读正文之后" in content or "评级说明和重要声明" in content) and len(content) < 140:
            return True
        low_value_domains = ("basic.10jqka.com.cn", "vip.stock.finance.sina.com.cn", "q.stock.sohu.com", "aastocks.com", "xueqiu.com")
        return any(domain in url for domain in low_value_domains)

    def _is_old_background(self, text):
        years = [int(y) for y in re.findall(r"20\d{2}", text)]
        if years and max(years) < 2025:
            return True
        return False

    def _format_sources(self, results):
        sources = []
        for item in results[:8]:
            sources.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "published_date": item.get("published_date", ""),
                "score": item.get("score"),
            })
        return sources
