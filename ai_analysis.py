#!/usr/bin/env python3
"""
Minima AI 买卖建议模块
调用 MiniMax-M2.7 模型，基于量化指标生成投资建议文字
"""

import requests
from config import MINIMA_API_URL, MINIMA_MODEL, MINIMA_API_KEY

_ETF_PROMPT = """你是一位专业的基金分析师。请基于以下量化数据，对{name}（{ts_code}）给出简洁的投资建议。

数据摘要：
- 近1月/3月/1年收益率：{ret_1m}% / {ret_3m}% / {ret_1y}%
- 同类基金收益率排名：{similar_rank}
- 年化跟踪误差：{tracking_error}%（越小越好，<1%为优秀）
- 综合费率：{total_fee}%/年
- 基金规模：{aum}亿元，近期规模趋势：{aum_trend}
- 净值位置：当前净值在20日/60日均线{ma_position}
- 跟踪指数估值：PE={index_pe}（历史{index_pe_pct}%分位），PB={index_pb}（历史{index_pb_pct}%分位）
- 当前溢折率：{premium}%（历史{premium_pct}%分位）

请给出：
1. 投资评级（买入 / 持有 / 减持）
2. 核心理由（3条，每条1-2句）
3. 主要风险提示（1条）

要求：语言简洁专业，总字数200字以内，不要出现"根据以上数据"等套话。"""

_STOCK_PROMPT = """你是一位资深的卖方研究员。请基于以下多维度量化数据，对{name}（{ts_code}）给出专业深入的投资建议。

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

请给出：
1. 投资评级（强烈买入 / 买入 / 持有 / 减持 / 回避）
2. 核心逻辑（4条，每条1-2句，涵盖估值、成长性、资金面、催化剂）
3. 主要风险（2条）
4. 建议操作策略（1句话）

要求：语言专业凝练，总字数300字以内。"""

_FALLBACK = "暂无AI分析建议（API调用失败）"

_HK_STOCK_PROMPT = """你是一位专业的港股分析师。请基于以下量化数据，对{name}（{ts_code}）给出简洁的投资建议。

数据摘要：
- 当前PE（TTM）：{pe_ttm}，PB（TTM）：{pb_ttm}
- 最新ROE（平均）：{roe_avg}%
- 资产负债率：{debt_ratio}%
- 近1年营收增速：{rev_growth}%，净利润增速：{profit_growth}%
- 毛利率：{gross_margin}%
- 现金流质量：经营现金流/营收={ocf_sales}（>0.15为健康）
- 南向资金持仓比例：{southbound_ratio}%，近期趋势：{southbound_trend}
- 股价位置：当前股价在20日/60日均线{ma_position}

请给出：
1. 投资评级（买入 / 持有 / 减持）
2. 核心理由（3条，每条1-2句）
3. 主要风险提示（1条，需提及港股特有风险如汇率、流动性）

要求：语言简洁专业，总字数200字以内，不要出现"根据以上数据"等套话。"""


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
        rating = "买入"
    elif score >= 2:
        rating = "持有"
    else:
        rating = "观望"

    reasons = [
        f"近1月/3月/1年收益分别为{_fmt_pct(ret_1m)}、{_fmt_pct(ret_3m)}、{_fmt_pct(ret_1y)}，反映当前阶段表现。",
        f"年化跟踪误差为{_fmt_pct(te)}，误差越小代表对指数的跟踪稳定性越好。",
        f"当前同类排名为{summary_data.get('similar_rank', 'N/A')}，可结合同类相对强弱判断配置价值。",
    ]

    return "\n".join([
        "AI服务暂不可用，以下为基于量化指标的规则化建议：",
        f"1. 投资评级：{rating}",
        "2. 核心理由：",
        f"- {reasons[0]}",
        f"- {reasons[1]}",
        f"- {reasons[2]}",
        "3. 风险提示：短期波动与风格轮动可能放大净值回撤，建议控制仓位并分批配置。",
    ])


def _rule_based_stock_advice(summary_data: dict) -> str:
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
        rating = "买入"
    elif score >= 2:
        rating = "持有"
    else:
        rating = "观望"

    return "\n".join([
        "AI服务暂不可用，以下为基于量化指标的规则化建议：",
        f"1. 投资评级：{rating}",
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
        rating = "买入"
    elif score >= 2:
        rating = "持有"
    else:
        rating = "观望"

    return "\n".join([
        "AI服务暂不可用，以下为基于量化指标的规则化建议：",
        f"1. 投资评级：{rating}",
        "2. 核心理由：",
        f"- 当前PE(TTM)为{str(round(pe, 1)) if pe is not None else 'N/A'}，估值处于可比区间内。",
        f"- ROE(平均)为{_fmt_pct(roe)}，反映公司盈利质量。",
        f"- 资产负债率为{_fmt_pct(debt)}，可用于评估财务稳健性。",
        "3. 风险提示：港股流动性风险、汇率波动及南向资金情绪变化均可能造成较大回撤，建议控制仓位。",
    ])


def _fallback_advice(security_type: str, summary_data: dict) -> str:
    if security_type == "etf":
        return _rule_based_etf_advice(summary_data)
    if security_type == "stock":
        return _rule_based_stock_advice(summary_data)
    if security_type == "hk_stock":
        return _rule_based_hk_stock_advice(summary_data)
    return _FALLBACK


def _call_minima(prompt: str) -> str:
    if not MINIMA_API_KEY:
        return _FALLBACK

    headers = {
        "x-api-key": MINIMA_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": MINIMA_MODEL,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = requests.post(
            f"{MINIMA_API_URL}/v1/messages",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # 过滤出 text 类型（响应中可能包含 thinking 块）
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"].strip()
        return _FALLBACK
    except Exception as e:
        print(f"  ✗ Minima AI 调用失败: {e}")
        return _FALLBACK


def get_investment_advice(security_type: str, summary_data: dict) -> str:
    """
    生成买卖建议文字。

    参数:
        security_type: "etf"、"stock" 或 "hk_stock"
        summary_data: 量化指标字典（见各模板字段）
    返回:
        str - 包含评级+理由+风险的自然语言建议
    """
    print("  调用 Minima AI 生成买卖建议...")

    if security_type == "etf":
        d = summary_data
        prompt = _ETF_PROMPT.format(
            name=d.get("name", ""),
            ts_code=d.get("ts_code", ""),
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
        )
    elif security_type == "stock":
        d = summary_data
        prompt = _STOCK_PROMPT.format(
            name=d.get("name", ""),
            ts_code=d.get("ts_code", ""),
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
        )
    elif security_type == "hk_stock":
        d = summary_data
        prompt = _HK_STOCK_PROMPT.format(
            name=d.get("name", ""),
            ts_code=d.get("ts_code", ""),
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
        )
    else:
        return _fallback_advice(security_type, summary_data)

    ai_text = _call_minima(prompt)
    if ai_text == _FALLBACK:
        return _fallback_advice(security_type, summary_data)
    return ai_text
