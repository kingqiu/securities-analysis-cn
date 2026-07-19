#!/usr/bin/env python3
"""
研究报告"模型文字解读"模块。

默认【零 token 模式】：不调用任何外部大模型，直接输出基于量化指标的规则化研究解读，
与本项目"零 token、不向用户索取密钥、不调用外部 LLM"的定位一致。

如需启用 AI 润色，设置环境变量 TDX_AI_COMMENTARY=1（需平台/账号侧已配置可用的 LLM provider）。
启用后调用 MiniMax-M2.7 生成审慎的研究复盘文字；任何异常或质检失败均自动降级为规则化解读。
"""

import os

from analyst_model import build_stock_research_view, render_stock_research_brief
from etf_analyst_model import build_etf_research_view, render_etf_research_brief
from hk_analyst_model import build_hk_research_view, render_hk_research_brief
from providers import get_llm_provider

_ETF_PROMPT = """你是一位专业的基金研究员。请基于以下量化数据和已计算的 ETF 配置模型结论，对{name}（{ts_code}）给出简洁、审慎、可复盘的研究解读。

【ETF配置模型结论（必须遵守，不得擅自改研究状态或触发器）】
{etf_view}

数据摘要：
- 近1月/3月/1年收益率：{ret_1m}% / {ret_3m}% / {ret_1y}%
- 同类基金收益率排名：{similar_rank}
- 年化跟踪误差：{tracking_error}%（越小越好，<1%为优秀）
- 综合费率：{total_fee}%/年
- 基金规模：{aum}亿元，近期规模趋势：{aum_trend}
- 净值位置：当前净值在20日/60日均线{ma_position}
- 跟踪指数估值：PE={index_pe}（历史{index_pe_pct}%分位），PB={index_pb}（历史{index_pb_pct}%分位）
- 当前溢折率：{premium}%（历史{premium_pct}%分位）
- 场内实时状态：价格={current_price}，涨跌幅={change_pct}%，换手率={turnover_rate}%，成交额={amount}

请给出：
1. 配置研究状态与适用观察场景（解释模型状态，不要改成股票式“买入/卖出”）
2. 情景区间与观察触发器解释（强调是研究触发条件，不是确定性最佳点）
3. 核心理由（3条，每条1-2句）
4. 主要风险提示（至少2条）

要求：语言简洁专业，总字数350字以内；不要编造数据；不要使用“买入、卖出、建仓、加仓、减仓、止盈、止损、仓位建议、稳赚、最佳买点、必须买入”等直接交易或确定性表述。"""

_STOCK_PROMPT = """你是一位资深的证券研究员。请基于以下量化数据和已计算的投研模型结论，对{name}（{ts_code}）给出专业、审慎、可复盘的研究解读。

【投研模型结论（必须遵守，不得擅自改研究状态或价格情景区间）】
{analyst_view}

【估值维度】
- 所属行业：{industry}
- 当前PE（TTM）：{pe_ttm}，处于历史{pe_percentile}%分位（越低越便宜）
- 行业PE中位数：{industry_pe_median}，本股PE处于行业{industry_pe_pct}%分位
- 当前PB：{pb}
- 三情景目标价：乐观{price_bull}元 / 中性{price_base}元 / 谨慎{price_bear}元（当前{cur_price}元）

【盈利质量】
- 近1年营收增速：{rev_growth}%，净利润增速：{profit_growth}%
- 最新ROE：{roe}%
- 毛利率：{gross_margin}%
- 现金流质量：CFO/净利润={cfo_ratio}（>1为优秀）
- 审计意见：{audit_opinion}

【资金面信号】
- 近20日主力净流入：{net_mf_20d}万元
- 融资余额变化趋势：{margin_trend}
- 股东人数变化：{holder_change}
- 大宗交易（近3月）：{block_trade_info}
- 股权质押率：{pledge_ratio}%

【技术面】
- 股价位置：当前股价在20日/60日均线{ma_position}
- 资产负债率：{debt_ratio}%

【业绩预告】
- 最新业绩预告：{forecast_info}

【同行龙头参照】
{peer_context}

请给出：
1. 研究状态与适合观察的周期（明确周期，避免承诺收益）
2. 情景区间解释（说明这是研究复盘区间，不是确定性最佳点）
3. 核心逻辑（4条，每条1-2句，涵盖估值、质量、成长、资金技术）
4. 主要风险与反证条件（至少2条，说明什么情况会推翻原判断）
5. 后续观察触发器（只描述需继续验证的证据和复盘条件）

要求：语言专业凝练，总字数500字以内；不要编造数据；不要使用“买入、卖出、建仓、加仓、减仓、止盈、止损、仓位建议、稳赚、最佳买点、必须买入”等直接交易或确定性表述。"""

_FALLBACK = "暂无AI研究解读（API调用失败）"

_PROMPT_LEAK_MARKERS = (
    "the user wants",
    "the system says",
    "system says",
    "developer message",
    "we need to",
    "let's draft",
    "i need to",
    "prompt",
    "instruction",
    "instructions",
    "final answer",
    "analysis:",
    "assistant:",
    "user:",
    "system:",
)

_FORBIDDEN_TRADING_TERMS = (
    "买入",
    "卖出",
    "建仓",
    "加仓",
    "减仓",
    "止盈",
    "止损",
    "仓位建议",
    "稳赚",
    "最佳买点",
    "必须买入",
)

_STOCK_COMPARISON_PROMPT = """你是一位经验丰富的证券研究员，正在向一位完全没有金融背景的朋友解释多只股票的对比分析结果。

{industry_context}

以下是{count}只股票的核心数据：

{data_table}

请给出：
1. **综合观察排序**：从研究证据更充分到证据更弱排序，说明排序依据。
2. **各自优劣势**：每只股票用2-3句话说清核心优势和最大风险。
3. **估值解读**：谁便宜谁贵？贵的是否有道理（比如增速更快）？
4. **适合什么观察框架**：每只股票更适合从稳健、成长、弹性、风险复核中的哪个角度继续观察？

要求：
- 每个专业术语第一次出现时，用括号加一句大白话解释
- 多用比喻和生活化类比（如"开店""存银行""买手机"）
- 结论要清楚，但不要形成直接买卖建议
- 不要使用“买入、卖出、建仓、加仓、减仓、止盈、止损、仓位、推荐、最佳选择、如果只能买”等直接交易或确定性表述
- 风险提示要具体，说明哪些因素会削弱研究假设
- 总字数400字以内"""

_ETF_COMPARISON_PROMPT = """你是一位经验丰富的基金研究员，正在向一位完全没有金融背景的朋友解释多只ETF基金的对比分析结果。

以下是{count}只ETF的核心数据：

{data_table}

请给出：
1. **赛道观察顺序**：这几只ETF分别追踪什么方向？哪个方向当前研究证据更充分？
2. **产品优劣对比**：费率、跟踪精度、规模、流动性谁更好？
3. **收益与风险**：过去谁赚得多？谁波动小？谁"性价比"最高？
4. **适合什么观察框架**：每只ETF更适合从核心配置、行业暴露、费率、跟踪质量、流动性中的哪个角度继续观察？

要求：
- 每个专业术语第一次出现时，用括号加一句大白话解释
- 多用比喻（如"买套餐""复印机""坐过山车"）
- 把ETF比作日常生活中的东西，让完全不懂金融的人也能明白
- 结论要清楚，但不要形成直接买卖建议
- 不要使用“买入、卖出、建仓、加仓、减仓、止盈、止损、仓位、推荐、最佳选择、如果只能买”等直接交易或确定性表述
- 总字数400字以内"""

_HK_STOCK_PROMPT = """你是一位专业的港股研究员。请基于以下量化数据和已计算的港股投研模型结论，对{name}（{ts_code}）给出简洁、审慎、可复盘的研究解读。

【港股投研模型结论（必须遵守，不得擅自改研究状态、价格情景区间或风险复核线）】
{hk_view}

数据摘要：
- 当前PE（TTM）：{pe_ttm}，PB（TTM）：{pb_ttm}
- 最新ROE（平均）：{roe_avg}%
- 资产负债率：{debt_ratio}%
- 近1年营收增速：{rev_growth}%，净利润增速：{profit_growth}%
- 毛利率：{gross_margin}%
- 现金流质量：经营现金流/营收={ocf_sales}（>0.15为健康）
- 南向资金持仓比例：{southbound_ratio}%，近期趋势：{southbound_trend}
- 股价位置：当前股价在20日/60日均线{ma_position}
- 当前价格：{cur_price} HKD，价格来源：{price_source}

请给出：
1. 研究状态与适合观察的周期（解释模型状态，不要自行改状态）
2. 情景区间解释（说明这是研究复盘区间，不是确定性最佳点；若模型没有区间则说明价格数据不足）
3. 核心理由（3条，每条1-2句）
4. 主要风险与反证条件（至少2条，需提及港股特有风险如汇率、流动性、南向资金）

要求：语言简洁专业，总字数400字以内；不要编造数据；不要使用“买入、卖出、建仓、加仓、减仓、止盈、止损、仓位建议、稳赚、最佳买点、必须买入”等直接交易或确定性表述。"""


def _fmt_pct(value):
    try:
        v = float(value)
        return f"{v:.2f}%"
    except (TypeError, ValueError):
        return "N/A"


def _safe_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rule_based_etf_advice(summary_data: dict) -> str:
    ret_1m = _safe_float(summary_data.get("ret_1m"))
    ret_3m = _safe_float(summary_data.get("ret_3m"))
    ret_1y = _safe_float(summary_data.get("ret_1y"))
    te = _safe_float(summary_data.get("tracking_error"))

    score = 0
    if ret_1m is not None and ret_1m > 0:
        score += 1
    if ret_3m is not None and ret_3m > 0:
        score += 1
    if ret_1y is not None and ret_1y > 0:
        score += 1
    if te is not None and te < 1:
        score += 1

    if score >= 3:
        rating = "积极观察"
    elif score >= 2:
        rating = "中性观察"
    else:
        rating = "等待验证"

    reasons = [
        f"近1月/3月/1年收益分别为{_fmt_pct(ret_1m)}、{_fmt_pct(ret_3m)}、{_fmt_pct(ret_1y)}，反映当前阶段表现。",
        f"年化跟踪误差为{_fmt_pct(te)}，误差越小代表对指数的跟踪稳定性越好。",
        f"当前同类排名为{summary_data.get('similar_rank', 'N/A')}，可结合同类相对强弱判断配置价值。",
    ]

    return "\n".join([
        "AI服务暂不可用，以下为基于量化指标的规则化研究解读：",
        f"1. 研究状态：{rating}",
        "2. 核心理由：",
        f"- {reasons[0]}",
        f"- {reasons[1]}",
        f"- {reasons[2]}",
        "3. 风险提示：短期波动与风格轮动可能放大净值回撤，需要结合估值、跟踪误差和流动性持续复核。",
    ])


def _rule_based_stock_advice(summary_data: dict) -> str:
    view = build_stock_research_view(summary_data)
    if view:
        return "\n".join([
            "AI服务暂不可用，以下为基于专业投研模型的规则化研究解读：",
            render_stock_research_brief(view),
        ])

    pe = _safe_float(summary_data.get("pe_ttm"))
    roe = _safe_float(summary_data.get("roe"))
    debt = _safe_float(summary_data.get("debt_ratio"))

    score = 0
    if pe is not None and pe < 30:
        score += 1
    if roe is not None and roe > 10:
        score += 1
    if debt is not None and debt < 60:
        score += 1

    if score >= 3:
        rating = "积极观察"
    elif score >= 2:
        rating = "中性观察"
    else:
        rating = "等待验证"

    return "\n".join([
        "AI服务暂不可用，以下为基于量化指标的规则化研究解读：",
        f"1. 研究状态：{rating}",
        "2. 核心理由：",
        f"- 当前PE(TTM)为{_fmt_pct(pe).replace('%', '') if pe is not None else 'N/A'}，估值处于可比区间内。",
        f"- ROE为{_fmt_pct(roe)}，反映公司盈利质量。",
        f"- 资产负债率为{_fmt_pct(debt)}，可用于评估财务稳健性。",
        "3. 风险提示：业绩兑现不及预期、估值收缩与行业景气下行都可能造成回撤。",
    ])


def _rule_based_hk_stock_advice(summary_data: dict) -> str:
    pe = _safe_float(summary_data.get("pe_ttm"))
    roe = _safe_float(summary_data.get("roe_avg"))
    debt = _safe_float(summary_data.get("debt_ratio"))

    score = 0
    if pe is not None and pe < 25:
        score += 1
    if roe is not None and roe > 10:
        score += 1
    if debt is not None and debt < 60:
        score += 1

    if score >= 3:
        rating = "积极观察"
    elif score >= 2:
        rating = "中性观察"
    else:
        rating = "等待验证"

    return "\n".join([
        "AI服务暂不可用，以下为基于量化指标的规则化研究解读：",
        f"1. 研究状态：{rating}",
        "2. 核心理由：",
        f"- 当前PE(TTM)为{str(round(pe, 1)) if pe is not None else 'N/A'}，估值处于可比区间内。",
        f"- ROE(平均)为{_fmt_pct(roe)}，反映公司盈利质量。",
        f"- 资产负债率为{_fmt_pct(debt)}，可用于评估财务稳健性。",
        "3. 风险提示：港股流动性风险、汇率波动及南向资金情绪变化均可能造成较大回撤，需要提高复核频率。",
    ])


def _fallback_advice(security_type: str, summary_data: dict) -> str:
    if security_type == "etf":
        return _rule_based_etf_advice(summary_data)
    if security_type == "stock":
        return _rule_based_stock_advice(summary_data)
    if security_type == "hk_stock":
        return _rule_based_hk_stock_advice(summary_data)
    return _FALLBACK


def _call_llm(prompt: str) -> str:
    """通过 Provider 调用 AI 大模型"""
    try:
        llm = get_llm_provider()
        if not llm.is_available():
            return _FALLBACK
        result = llm.chat(prompt, max_tokens=1024)
        return result if result else _FALLBACK
    except Exception as e:
        print(f"  ✗ AI 调用失败: {e}")
        return _FALLBACK


def _ascii_ratio(text: str) -> float:
    if not text:
        return 0.0
    ascii_count = sum(1 for ch in text if ord(ch) < 128 and ch.isalpha())
    return ascii_count / max(len(text), 1)


def _is_unsafe_llm_output(text: str) -> bool:
    """识别提示词泄露、内部推理泄露和直接交易建议类异常输出。"""
    if not text or text == _FALLBACK:
        return True

    lower = text.lower()
    if any(marker in lower for marker in _PROMPT_LEAK_MARKERS):
        return True

    # 正常中文报告里可能有少量英文指标，但不应大段英文叙述。
    if _ascii_ratio(text) > 0.35 and len(text) > 160:
        return True

    if any(term in text for term in _FORBIDDEN_TRADING_TERMS):
        return True

    return False


def get_investment_advice(security_type: str, summary_data: dict) -> str:
    """
    生成研究解读文字。

    参数:
        security_type: "etf"、"stock" 或 "hk_stock"
        summary_data: 量化指标字典（见各模板字段）
    返回:
        str - 包含研究状态、理由和风险的自然语言解读
    """
    # ── 零 token 模式（默认）──
    # 不调用任何外部大模型，直接输出规则化研究解读，兑现"零 token / 不调外部 LLM"定位。
    if os.environ.get("TDX_AI_COMMENTARY", "") != "1":
        print("  AI 解读已禁用（零 token 模式），使用规则化研究解读")
        return _fallback_advice(security_type, summary_data)

    print("  调用 Minima AI 生成研究解读...")

    if security_type == "etf":
        d = summary_data
        etf_view = render_etf_research_brief(build_etf_research_view(d))
        prompt = _ETF_PROMPT.format(
            name=d.get("name", ""),
            ts_code=d.get("ts_code", ""),
            etf_view=etf_view,
            ret_1m=d.get("ret_1m", "N/A"),
            ret_3m=d.get("ret_3m", "N/A"),
            ret_1y=d.get("ret_1y", "N/A"),
            similar_rank=d.get("similar_rank", "N/A"),
            tracking_error=d.get("tracking_error", "N/A"),
            total_fee=d.get("total_fee", "N/A"),
            aum=d.get("aum", "N/A"),
            aum_trend=d.get("aum_trend", "未知"),
            ma_position=d.get("ma_position", "未知"),
            index_pe=d.get("index_pe", "N/A"),
            index_pe_pct=d.get("index_pe_pct", "N/A"),
            index_pb=d.get("index_pb", "N/A"),
            index_pb_pct=d.get("index_pb_pct", "N/A"),
            premium=d.get("premium", "N/A"),
            premium_pct=d.get("premium_pct", "N/A"),
            current_price=d.get("current_price", "N/A"),
            change_pct=d.get("change_pct", "N/A"),
            turnover_rate=d.get("turnover_rate", "N/A"),
            amount=d.get("amount", "N/A"),
        )
    elif security_type == "stock":
        d = summary_data
        analyst_view = render_stock_research_brief(build_stock_research_view(d))
        prompt = _STOCK_PROMPT.format(
            name=d.get("name", ""),
            ts_code=d.get("ts_code", ""),
            analyst_view=analyst_view,
            industry=d.get("industry", "未知"),
            pe_ttm=d.get("pe_ttm", "N/A"),
            pe_percentile=d.get("pe_percentile", "N/A"),
            industry_pe_median=d.get("industry_pe_median", "N/A"),
            industry_pe_pct=d.get("industry_pe_pct", "N/A"),
            pb=d.get("pb", "N/A"),
            rev_growth=d.get("rev_growth", "N/A"),
            profit_growth=d.get("profit_growth", "N/A"),
            roe=d.get("roe", "N/A"),
            gross_margin=d.get("gross_margin", "N/A"),
            debt_ratio=d.get("debt_ratio", "N/A"),
            cfo_ratio=d.get("cfo_ratio", "N/A"),
            audit_opinion=d.get("audit_opinion", "N/A"),
            net_mf_20d=d.get("net_mf_20d", "N/A"),
            margin_trend=d.get("margin_trend", "N/A"),
            holder_change=d.get("holder_change", "N/A"),
            block_trade_info=d.get("block_trade_info", "N/A"),
            pledge_ratio=d.get("pledge_ratio", "N/A"),
            price_bull=d.get("price_bull", "N/A"),
            price_base=d.get("price_base", "N/A"),
            price_bear=d.get("price_bear", "N/A"),
            cur_price=d.get("cur_price", "N/A"),
            ma_position=d.get("ma_position", "未知"),
            forecast_info=d.get("forecast_info", "N/A"),
            peer_context=d.get("peer_context", "N/A"),
        )
    elif security_type == "hk_stock":
        d = summary_data
        hk_view = render_hk_research_brief(build_hk_research_view(d))
        prompt = _HK_STOCK_PROMPT.format(
            name=d.get("name", ""),
            ts_code=d.get("ts_code", ""),
            hk_view=hk_view,
            pe_ttm=d.get("pe_ttm", "N/A"),
            pb_ttm=d.get("pb_ttm", "N/A"),
            roe_avg=d.get("roe_avg", "N/A"),
            debt_ratio=d.get("debt_ratio", "N/A"),
            rev_growth=d.get("rev_growth", "N/A"),
            profit_growth=d.get("profit_growth", "N/A"),
            gross_margin=d.get("gross_margin", "N/A"),
            ocf_sales=d.get("ocf_sales", "N/A"),
            southbound_ratio=d.get("southbound_ratio", "N/A"),
            southbound_trend=d.get("southbound_trend", "未知"),
            ma_position=d.get("ma_position", "未知"),
            cur_price=d.get("cur_price", "N/A"),
            price_source=d.get("price_source", "N/A"),
        )
    else:
        return _fallback_advice(security_type, summary_data)

    ai_text = _call_llm(prompt)
    if _is_unsafe_llm_output(ai_text):
        if ai_text != _FALLBACK:
            print("  ⚠ AI 输出未通过质检，改用规则化研究解读")
        return _fallback_advice(security_type, summary_data)
    return ai_text


def get_comparison_advice(compare_type: str, summaries: list) -> str:
    """
    生成多标的对比分析的 AI 研究解读。

    参数:
        compare_type: "stock" / "hk_stock" / "etf" / "mixed"
        summaries: 每只标的的摘要字典列表
    返回:
        str - 通俗易懂的对比分析文字
    """
    print("  调用 AI 生成对比研究解读...")

    count = len(summaries)

    # 构建数据表格文本
    if compare_type == "etf":
        lines = []
        for s in summaries:
            lines.append(
                f"【{s.get('name', '?')}（{s.get('ts_code', '?')}）】\n"
                f"  近1月/3月/1年收益率：{s.get('ret_1m', 'N/A')}% / {s.get('ret_3m', 'N/A')}% / {s.get('ret_1y', 'N/A')}%\n"
                f"  年化跟踪误差：{s.get('tracking_error', 'N/A')}%\n"
                f"  综合费率：{s.get('total_fee', 'N/A')}%/年\n"
                f"  基金规模：{s.get('aum', 'N/A')}亿元\n"
                f"  跟踪指数PE分位：{s.get('index_pe_pct', 'N/A')}%\n"
                f"  场内实时：价格{s.get('cur_price', 'N/A')}，涨跌{s.get('change_pct', 'N/A')}%，换手{s.get('turnover_rate', 'N/A')}%，成交额{s.get('amount', 'N/A')}"
            )
        data_table = "\n\n".join(lines)
        prompt = _ETF_COMPARISON_PROMPT.format(count=count, data_table=data_table)
    else:
        # stock / hk_stock / mixed 通用
        industries = [s.get("industry", "未知") for s in summaries]
        if len(set(industries)) == 1:
            industry_context = f"这{count}只股票都属于【{industries[0]}】行业，可以直接横向对比。"
        else:
            industry_context = (
                f"注意：这{count}只股票分属不同行业（{'、'.join(set(industries))}），"
                "估值体系不同，不能简单比较PE高低，需要结合各行业特点分析。"
            )

        lines = []
        for s in summaries:
            lines.append(
                f"【{s.get('name', '?')}（{s.get('ts_code', '?')}）— {s.get('industry', '未知')}】\n"
                f"  市值：{s.get('market_cap', 'N/A')}亿元\n"
                f"  PE(TTM)：{s.get('pe_ttm', 'N/A')}　PB：{s.get('pb', 'N/A')}\n"
                f"  营收增速：{s.get('rev_growth', 'N/A')}%　净利增速：{s.get('profit_growth', 'N/A')}%\n"
                f"  ROE：{s.get('roe', 'N/A')}%　毛利率：{s.get('gross_margin', 'N/A')}%\n"
                f"  资产负债率：{s.get('debt_ratio', 'N/A')}%\n"
                f"  股息率：{s.get('dividend_yield', 'N/A')}%\n"
                f"  实时行情：价格{s.get('cur_price', 'N/A')}，涨跌{s.get('change_pct', 'N/A')}%，来源{s.get('price_source', 'N/A')}"
            )
        data_table = "\n\n".join(lines)
        prompt = _STOCK_COMPARISON_PROMPT.format(
            industry_context=industry_context, count=count, data_table=data_table
        )

    ai_text = _call_llm(prompt)
    if _is_unsafe_llm_output(ai_text):
        # 降级：简单文本摘要
        names = [s.get("name", "?") for s in summaries]
        return f"模型服务暂不可用。以下{count}只标的（{'、'.join(names)}）的详细数据请参考后续各章节图表。"
    return ai_text


# ============================================================
# 行业与公司动态新闻（替代央视通用新闻）
# ============================================================

_INDUSTRY_NEWS_PROMPT = """你是一位专业的证券分析师。请为以下公司提供与其业务密切相关的近期行业与公司动态摘要。

公司：{name}（{ts_code}）
所属行业：{industry}
市场：{market}

请提供以下内容（每条1-2句话，共5-8条）：

1. 该公司近期重要公告或经营动态（如有）
2. 所在行业的最新政策动向（补贴、监管、标准等）
3. 行业供需变化或市场趋势
4. 主要竞争对手的近期动态
5. 可能影响该公司股价的宏观经济因素

要求：
- 只提供与「{industry}」行业和「{name}」公司直接相关的信息
- 不要提供与该公司无关的泛泛宏观新闻
- 如果某方面信息有限，如实说明即可
- 每条以「•」开头，简洁明了"""


def get_industry_news(name: str, ts_code: str, industry: str, market: str = "A股") -> str:
    """
    生成与该公司/行业相关的动态新闻摘要。
    优先使用搜索服务；仅当 Tavily 未配置或不可用时，SearchProvider 才会降级到 AI。
    """
    from web_research import search_company_news

    print("  通过搜索服务获取行业动态...")
    result = search_company_news(name, ts_code, market, industry)
    if result.get("status") != "success":
        return f"搜索服务暂不可用，无法获取{name}（{industry}行业）的相关动态：{result.get('summary', '未知原因')}"

    sections = result.get("sections", {})
    lines = []
    for key in ("recent_events", "industry_dynamics", "analyst_views", "risk_factors", "catalysts"):
        content = sections.get(key)
        if content:
            lines.append(content)
    if not lines:
        return result.get("summary") or "搜索结果中未提取到可用行业动态。"
    return "\n\n".join(lines)
