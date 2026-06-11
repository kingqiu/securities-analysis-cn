#!/usr/bin/env python3
"""Deterministic Hong Kong stock analyst model.

The model is intentionally conservative. It produces reproducible scenario
bands from available report data before any LLM wording is added.
"""

from __future__ import annotations


def _f(value, default=None):
    try:
        if value in ("", None, "N/A"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _round(value, digits=2):
    return round(value, digits) if value is not None else None


def build_hk_research_view(summary: dict) -> dict:
    price = _f(summary.get("cur_price"))
    pe = _f(summary.get("pe_ttm"))
    pb = _f(summary.get("pb"))
    roe = _f(summary.get("roe"))
    rev_growth = _f(summary.get("rev_growth"))
    profit_growth = _f(summary.get("profit_growth"))
    debt_ratio = _f(summary.get("debt_ratio"))
    ocf_sales = _f(summary.get("ocf_sales"))
    southbound_ratio = _f(summary.get("southbound_ratio"))
    dividend_rate = _f(summary.get("dividend_rate"))
    avg_turnover_hkd = _f(summary.get("avg_turnover_hkd"))
    avg_volume = _f(summary.get("avg_volume"))
    buyback_signal = summary.get("buyback_signal", "未知")
    adr_ticker = summary.get("adr_ticker", "")
    currency = summary.get("currency", "HKD")
    regulatory_sensitivity = summary.get("regulatory_sensitivity", "未知")
    business_segments = summary.get("business_segments", [])
    ma_position = summary.get("ma_position", "未知")
    southbound_trend = summary.get("southbound_trend", "未知")

    score = 0
    scores = {}
    positives = []
    risks = []

    valuation = 0
    if pe is not None:
        if 0 < pe <= 12:
            valuation += 2
            positives.append(f"PE(TTM){pe:.1f}倍，估值具备一定安全边际")
        elif pe <= 20:
            valuation += 1
        elif pe >= 35:
            valuation -= 2
            risks.append(f"PE(TTM){pe:.1f}倍，港股流动性折价下估值容错偏低")
    if pb is not None:
        if 0 < pb <= 1.2:
            valuation += 1
        elif pb >= 4:
            valuation -= 1
    scores["valuation"] = valuation
    score += valuation

    quality = 0
    if roe is not None:
        if roe >= 15:
            quality += 2
            positives.append(f"ROE {roe:.1f}%，盈利质量较强")
        elif roe < 8:
            quality -= 1
            risks.append(f"ROE {roe:.1f}%，股东回报效率偏弱")
    if ocf_sales is not None:
        if ocf_sales >= 0.15:
            quality += 1
        elif ocf_sales < 0.05:
            quality -= 1
            risks.append("经营现金流/营收比偏低，利润现金含量需要复核")
    if debt_ratio is not None and debt_ratio > 70:
        quality -= 1
        risks.append(f"资产负债率{debt_ratio:.1f}%，财务杠杆偏高")
    scores["quality"] = quality
    score += quality

    growth = 0
    if rev_growth is not None:
        growth += 1 if rev_growth > 5 else -1 if rev_growth < -5 else 0
    if profit_growth is not None:
        growth += 1 if profit_growth > 5 else -2 if profit_growth < -10 else 0
    if growth < 0:
        risks.append("收入或利润增长承压，估值修复需要业绩确认")
    elif growth > 0:
        positives.append("收入/利润增速仍有正贡献")
    scores["growth"] = growth
    score += growth

    capital = 0
    if southbound_trend == "增持":
        capital += 1
        positives.append("南向资金近期增持，内地资金定价支持增强")
    elif southbound_trend == "减持":
        capital -= 1
        risks.append("南向资金近期减持，短期资金面偏弱")
    if southbound_ratio is not None and southbound_ratio >= 10:
        capital += 1
    if "多头" in ma_position:
        capital += 1
    elif "空头" in ma_position:
        capital -= 1
        risks.append("价格位于主要均线下方，趋势尚未修复")
    scores["capital_technical"] = capital
    score += capital

    income = 0
    if dividend_rate is not None:
        if dividend_rate >= 5:
            income += 2
            positives.append(f"股息率约{dividend_rate:.1f}%，具备高股息吸引力")
        elif dividend_rate >= 3:
            income += 1
    if buyback_signal == "有回购线索":
        income += 1
        positives.append("公开研究中出现回购线索，可能增强股东回报预期")
    scores["income"] = income
    score += income

    hk_specific = 0
    hk_notes = []
    data_gaps = []
    if avg_turnover_hkd is not None:
        if avg_turnover_hkd >= 500_000_000:
            hk_specific += 1
            hk_notes.append(f"近20日成交额估算约{avg_turnover_hkd/100_000_000:.1f}亿港元/日，流动性较好")
        elif avg_turnover_hkd < 50_000_000:
            hk_specific -= 2
            risks.append("近20日成交额偏低，港股流动性折价和交易滑点需重点关注")
        else:
            hk_notes.append(f"近20日成交额估算约{avg_turnover_hkd/100_000_000:.1f}亿港元/日，流动性中等")
    elif avg_volume is not None:
        hk_notes.append(f"近20日成交量约{avg_volume/10_000:.1f}万股/日，但缺少成交额字段，流动性判断需谨慎")
        data_gaps.append("缺少港股成交额，暂以成交量和价格估算流动性")
    else:
        data_gaps.append("缺少港股成交额/成交量，无法量化流动性折价")

    if currency and currency != "HKD":
        hk_notes.append(f"财务报表币种为{currency}，需注意与港股交易币种HKD之间的换算")
    else:
        hk_notes.append("交易和多数财务口径以港元或港币相关口径呈现，内地投资者还需关注人民币/港元汇率")

    if adr_ticker:
        hk_notes.append(f"存在可跟踪ADR/美股映射：{adr_ticker}；当前未接入ADR实时价差，暂不计算跨市场折溢价")
        data_gaps.append("ADR实时价差未接入，不能判断港股相对美股映射的折溢价")
    else:
        data_gaps.append("未识别到ADR/美股映射，跨市场估值锚有限")

    if regulatory_sensitivity and regulatory_sensitivity != "未知":
        hk_specific -= 1 if "高" in regulatory_sensitivity else 0
        hk_notes.append(f"监管敏感度：{regulatory_sensitivity}")
    if business_segments:
        hk_notes.append("业务拆分关注点：" + "、".join(business_segments[:5]))

    scores["hk_specific"] = hk_specific
    score += hk_specific

    if price:
        fair_base = price * (1 + max(min(score, 6), -4) * 0.035)
        fair_bear = fair_base * 0.88
        fair_bull = fair_base * 1.13
        buy_low = fair_bear * 0.92
        buy_high = fair_base * 0.96
        watch_high = fair_base * 1.03
        take_low = fair_base * 1.08
        take_high = fair_bull
        stop = min(buy_low * 0.96, price * 0.9)
    else:
        fair_base = fair_bear = fair_bull = None
        buy_low = buy_high = watch_high = take_low = take_high = stop = None

    if not price:
        position = "当前缺少港股日线价格，暂不生成价格区间；先以估值、南向资金、股息和财务质量判断配置价值。"
    elif score >= 5:
        rating = "积极关注"
        position = "估值和质量证据相对积极，但仍需观察南向资金和成交额确认。"
    elif score >= 2:
        rating = "审慎关注"
        position = "等待估值、南向资金或业绩至少一个维度继续验证。"
    elif score >= -1:
        rating = "观望"
        position = "当前证据偏中性，需等待估值、资金或业绩信号改善。"
    else:
        rating = "风险优先"
        position = "负向证据较多，优先等待基本面和流动性信号修复。"

    risk_level = "高" if score <= -2 or (debt_ratio and debt_ratio > 75) else "中" if score < 3 else "低"
    if not positives:
        positives.append("暂未形成足够强的正向证据")
    if not risks:
        risks.append("港股受汇率、海外流动性和风险偏好影响，需提高情景复核频率")
    risks.append("人民币/港元汇率波动会影响内地投资者实际收益")

    if score >= 5:
        rating = "积极关注"
    elif score >= 2:
        rating = "审慎关注"
    elif score >= -1:
        rating = "观望"
    else:
        rating = "风险优先"

    return {
        "rating": rating,
        "score": score,
        "scores": scores,
        "risk_level": risk_level,
        "cur_price": _round(price, 3),
        "price_bear": _round(fair_bear, 3),
        "price_base": _round(fair_base, 3),
        "price_bull": _round(fair_bull, 3),
        "buy_zone": (_round(buy_low, 3), _round(buy_high, 3)) if buy_low and buy_high else None,
        "watch_zone": (_round(buy_high, 3), _round(watch_high, 3)) if buy_high and watch_high else None,
        "take_profit_zone": (_round(take_low, 3), _round(take_high, 3)) if take_low and take_high else None,
        "stop_loss": _round(stop, 3),
        "position_plan": position,
        "positives": positives[:5],
        "risks": risks[:6],
        "southbound_trend": southbound_trend,
        "hk_notes": hk_notes[:8],
        "data_gaps": data_gaps[:6],
        "adr_ticker": adr_ticker,
        "business_segments": business_segments,
        "regulatory_sensitivity": regulatory_sensitivity,
    }


def render_hk_research_brief(view: dict) -> str:
    if not view:
        return "港股投研模型数据不足。"
    buy = view.get("buy_zone")
    watch = view.get("watch_zone")
    take = view.get("take_profit_zone")
    lines = [
        f"- 研究状态：{view.get('rating')}（风险等级：{view.get('risk_level')}；综合得分：{view.get('score')}）",
    ]
    if view.get("cur_price") is not None:
        lines.append(
            f"- 当前价/谨慎/中性/乐观价值：{view.get('cur_price')} / {view.get('price_bear')} / {view.get('price_base')} / {view.get('price_bull')} HKD"
        )
    else:
        lines.append("- 当前缺少港股日线价格，暂不生成价格区间。")
    if buy:
        lines.append(f"- 估值安全边际观察区：{buy[0]}-{buy[1]} HKD")
    if watch:
        lines.append(f"- 中性观察区：{watch[0]}-{watch[1]} HKD")
    if take:
        lines.append(f"- 高估值复核区：{take[0]}-{take[1]} HKD")
    if view.get("stop_loss") is not None:
        lines.append(f"- 风险复核线：{view.get('stop_loss')} HKD")
    lines.append(f"- 情景观察：{view.get('position_plan')}")
    lines.append("核心正向证据：")
    lines.extend([f"  - {x}" for x in view.get("positives", [])])
    lines.append("主要风险与反证条件：")
    lines.extend([f"  - {x}" for x in view.get("risks", [])])
    if view.get("hk_notes"):
        lines.append("港股特有维度：")
        lines.extend([f"  - {x}" for x in view.get("hk_notes", [])])
    if view.get("data_gaps"):
        lines.append("当前数据缺口：")
        lines.extend([f"  - {x}" for x in view.get("data_gaps", [])])
    return "\n".join(lines)
