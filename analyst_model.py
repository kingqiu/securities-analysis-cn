#!/usr/bin/env python3
"""
Analyst-grade scoring and trading-plan helpers.

The LLM should explain conclusions, not invent the core recommendation.
This module turns already-fetched quantitative fields into a structured,
auditable research view that can be rendered in PDF reports or sent to an LLM.
"""

import re
from typing import Any


def _safe_float(value: Any, default=None):
    if value in (None, "", "N/A", "None"):
        return default
    try:
        if isinstance(value, str):
            match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
            if not match:
                return default
            value = match.group(0)
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt(value, suffix="", digits=1):
    v = _safe_float(value)
    if v is None:
        return "N/A"
    return f"{v:.{digits}f}{suffix}"


def _score_band(name: str, score: int, evidence: str) -> dict:
    return {"name": name, "score": score, "evidence": evidence}


def _rating(total_score: int, base_upside, risk_reward):
    if total_score >= 11 and (base_upside or 0) >= 25 and (risk_reward or 0) >= 1.5:
        return "强烈买入"
    if total_score >= 8 and (base_upside or 0) >= 15:
        return "买入"
    if total_score >= 5:
        return "谨慎买入"
    if total_score >= 2:
        return "持有"
    if total_score >= -1:
        return "观望"
    return "回避"


def _risk_level(total_score: int, bear_downside, pledge_ratio, debt_ratio):
    penalty = 0
    if bear_downside is not None and bear_downside < -25:
        penalty += 1
    if pledge_ratio is not None and pledge_ratio > 20:
        penalty += 1
    if debt_ratio is not None and debt_ratio > 70:
        penalty += 1
    if total_score < 0:
        penalty += 1
    if penalty >= 3:
        return "高"
    if penalty >= 1:
        return "中"
    return "低"


def _append_score(items: list, name: str, score: int, evidence: str):
    items.append(_score_band(name, score, evidence))


def build_stock_research_view(summary_data: dict) -> dict:
    """Build a structured A-share research view from report summary fields."""
    pe_pct = _safe_float(summary_data.get("pe_percentile"))
    industry_pe_pct = _safe_float(summary_data.get("industry_pe_pct"))
    pe_ttm = _safe_float(summary_data.get("pe_ttm"))
    roe = _safe_float(summary_data.get("roe"))
    gross_margin = _safe_float(summary_data.get("gross_margin"))
    rev_growth = _safe_float(summary_data.get("rev_growth"))
    profit_growth = _safe_float(summary_data.get("profit_growth"))
    debt_ratio = _safe_float(summary_data.get("debt_ratio"))
    cfo_ratio = _safe_float(summary_data.get("cfo_ratio"))
    pledge_ratio = _safe_float(summary_data.get("pledge_ratio"))
    net_mf_20d = _safe_float(summary_data.get("net_mf_20d"))
    cur_price = _safe_float(summary_data.get("cur_price"))
    price_bull = _safe_float(summary_data.get("price_bull"))
    price_base = _safe_float(summary_data.get("price_base"))
    price_bear = _safe_float(summary_data.get("price_bear"))

    base_upside = None
    bull_upside = None
    bear_downside = None
    if cur_price and price_base:
        base_upside = round((price_base / cur_price - 1) * 100, 1)
    if cur_price and price_bull:
        bull_upside = round((price_bull / cur_price - 1) * 100, 1)
    if cur_price and price_bear:
        bear_downside = round((price_bear / cur_price - 1) * 100, 1)

    valuation = []
    valuation_score = 0
    if pe_pct is not None:
        if pe_pct <= 25:
            delta = 2
            msg = f"PE历史分位{pe_pct:.1f}%，处在偏低估区间"
        elif pe_pct <= 50:
            delta = 1
            msg = f"PE历史分位{pe_pct:.1f}%，估值不算拥挤"
        elif pe_pct >= 80:
            delta = -2
            msg = f"PE历史分位{pe_pct:.1f}%，处在偏高估区间"
        else:
            delta = 0
            msg = f"PE历史分位{pe_pct:.1f}%，估值中性"
        valuation_score += delta
        _append_score(valuation, "历史估值分位", delta, msg)
    if industry_pe_pct is not None:
        if industry_pe_pct <= 35:
            delta = 1
            msg = f"行业PE分位{industry_pe_pct:.1f}%，相对同行不贵"
        elif industry_pe_pct >= 75:
            delta = -1
            msg = f"行业PE分位{industry_pe_pct:.1f}%，相对同行偏贵"
        else:
            delta = 0
            msg = f"行业PE分位{industry_pe_pct:.1f}%，相对同行中性"
        valuation_score += delta
        _append_score(valuation, "同行估值位置", delta, msg)
    if base_upside is not None:
        if base_upside >= 30:
            delta = 3
            msg = f"中性情景上涨空间{base_upside:.1f}%，安全边际较厚"
        elif base_upside >= 15:
            delta = 2
            msg = f"中性情景上涨空间{base_upside:.1f}%，具备配置吸引力"
        elif base_upside >= 0:
            delta = 0
            msg = f"中性情景上涨空间{base_upside:.1f}%，风险收益比一般"
        else:
            delta = -2
            msg = f"中性情景下跌空间{abs(base_upside):.1f}%，当前位置偏贵"
        valuation_score += delta
        _append_score(valuation, "情景收益空间", delta, msg)
    if pe_ttm is not None and pe_ttm <= 0:
        valuation_score -= 2
        _append_score(valuation, "盈利估值有效性", -2, "PE为负或无效，常规估值参考价值下降")

    quality = []
    quality_score = 0
    if roe is not None:
        if roe >= 20:
            delta = 3
            msg = f"ROE {_fmt(roe, '%')} ，股东回报优秀"
        elif roe >= 15:
            delta = 2
            msg = f"ROE {_fmt(roe, '%')} ，盈利质量较好"
        elif roe >= 8:
            delta = 0
            msg = f"ROE {_fmt(roe, '%')} ，盈利质量中性"
        else:
            delta = -2
            msg = f"ROE {_fmt(roe, '%')} ，盈利质量偏弱"
        quality_score += delta
        _append_score(quality, "ROE", delta, msg)
    if cfo_ratio is not None:
        if cfo_ratio >= 1.0:
            delta = 2
            msg = f"CFO/净利润{cfo_ratio:.2f}，利润现金含量高"
        elif cfo_ratio >= 0.5:
            delta = 0
            msg = f"CFO/净利润{cfo_ratio:.2f}，现金流质量一般"
        else:
            delta = -2
            msg = f"CFO/净利润{cfo_ratio:.2f}，账面利润含金量偏弱"
        quality_score += delta
        _append_score(quality, "现金流质量", delta, msg)
    if debt_ratio is not None:
        if debt_ratio <= 40:
            delta = 1
            msg = f"资产负债率{debt_ratio:.1f}%，财务结构稳健"
        elif debt_ratio >= 70:
            delta = -2
            msg = f"资产负债率{debt_ratio:.1f}%，偿债与再融资压力需关注"
        else:
            delta = 0
            msg = f"资产负债率{debt_ratio:.1f}%，杠杆水平中性"
        quality_score += delta
        _append_score(quality, "资产负债率", delta, msg)

    growth = []
    growth_score = 0
    if rev_growth is not None:
        if rev_growth >= 20:
            delta = 2
            msg = f"营收增速{rev_growth:.1f}%，收入扩张较快"
        elif rev_growth >= 8:
            delta = 1
            msg = f"营收增速{rev_growth:.1f}%，收入保持增长"
        elif rev_growth < 0:
            delta = -2
            msg = f"营收增速{rev_growth:.1f}%，收入承压"
        else:
            delta = 0
            msg = f"营收增速{rev_growth:.1f}%，增长偏温和"
        growth_score += delta
        _append_score(growth, "收入增长", delta, msg)
    if profit_growth is not None:
        if profit_growth >= 25:
            delta = 3
            msg = f"净利增速{profit_growth:.1f}%，利润弹性强"
        elif profit_growth >= 10:
            delta = 2
            msg = f"净利增速{profit_growth:.1f}%，利润增长健康"
        elif profit_growth < 0:
            delta = -3
            msg = f"净利增速{profit_growth:.1f}%，盈利下滑"
        else:
            delta = 0
            msg = f"净利增速{profit_growth:.1f}%，利润增长偏弱"
        growth_score += delta
        _append_score(growth, "利润增长", delta, msg)

    market = []
    market_score = 0
    ma_position = str(summary_data.get("ma_position", "未知"))
    if "上方" in ma_position or "多头" in ma_position:
        market_score += 1
        _append_score(market, "趋势结构", 1, f"股价位于均线{ma_position}，趋势偏强")
    elif "下方" in ma_position or "空头" in ma_position:
        market_score -= 1
        _append_score(market, "趋势结构", -1, f"股价位于均线{ma_position}，短期趋势偏弱")
    if net_mf_20d is not None:
        if net_mf_20d > 0:
            market_score += 1
            _append_score(market, "资金流向", 1, f"近20日主力净流入{net_mf_20d:.0f}万元")
        elif net_mf_20d < 0:
            market_score -= 1
            _append_score(market, "资金流向", -1, f"近20日主力净流出{abs(net_mf_20d):.0f}万元")

    risks = []
    risk_score = 0
    audit = str(summary_data.get("audit_opinion", ""))
    if audit and audit not in ("N/A", "标准无保留意见", "无保留意见"):
        risk_score -= 2
        risks.append(f"审计意见为「{audit}」，需要核查财务披露质量")
    if pledge_ratio is not None:
        if pledge_ratio >= 30:
            risk_score -= 3
            risks.append(f"股权质押率{pledge_ratio:.1f}%，极端行情下可能放大股价压力")
        elif pledge_ratio >= 10:
            risk_score -= 1
            risks.append(f"股权质押率{pledge_ratio:.1f}%，需跟踪质押平仓风险")
    if bear_downside is not None and bear_downside < -20:
        risk_score -= 1
        risks.append(f"谨慎情景下跌空间约{abs(bear_downside):.1f}%，下行风险不可忽视")
    if not risks:
        risks.append("未识别到突出的单项风险，但仍需跟踪业绩兑现与估值波动")

    total_score = valuation_score + quality_score + growth_score + market_score + risk_score
    risk_reward = None
    if base_upside is not None and bear_downside is not None and bear_downside < 0:
        risk_reward = round(base_upside / abs(bear_downside), 2)

    rating = _rating(total_score, base_upside, risk_reward)
    risk_level = _risk_level(total_score, bear_downside, pledge_ratio, debt_ratio)

    buy_zone = None
    watch_zone = None
    take_profit_zone = None
    stop_loss = None
    if cur_price and price_base and price_bear:
        buy_low = round(price_bear * 1.05, 2)
        buy_high = round(price_base * 0.85, 2)
        if buy_low > buy_high:
            buy_low, buy_high = buy_high, buy_low
        buy_zone = [buy_low, buy_high]
        watch_zone = [round(buy_high, 2), round(price_base, 2)]
        stop_loss = round(min(cur_price * 0.92, price_bear * 0.95), 2)
    if price_base and price_bull:
        take_profit_zone = [round(price_base, 2), round(price_bull, 2)]

    if buy_zone and cur_price:
        if cur_price <= buy_zone[1]:
            action = "价格进入安全边际区，可考虑分批建仓，单次仓位不宜过重。"
            position_plan = "首仓30%-40%，若基本面验证且仍在买入区可逐步加至60%-70%。"
        elif watch_zone and cur_price <= watch_zone[1]:
            action = "价格处于观察区，适合等待回调或基本面催化确认后再加仓。"
            position_plan = "以观察或小仓位为主，等待回到买入区或业绩催化确认。"
        elif take_profit_zone and cur_price >= take_profit_zone[0]:
            action = "价格接近或进入目标区，应以持有复盘和分批止盈为主。"
            position_plan = "不宜追高加仓，可按目标区间分批降低仓位。"
        else:
            action = "当前位置缺少足够安全边际，不建议追高。"
            position_plan = "维持观察或轻仓，等待风险收益比改善。"
    else:
        action = "关键价格数据不足，建议先以基本面跟踪和小仓位观察为主。"
        position_plan = "关键价格区间缺失，不建议制定明确仓位上限。"

    positives = []
    for group in (valuation, quality, growth, market):
        positives.extend([item["evidence"] for item in group if item["score"] > 0])
    if not positives:
        positives.append("当前正向证据不足，需等待估值、盈利或趋势出现更明确改善。")

    watchpoints = []
    if profit_growth is not None and profit_growth < 10:
        watchpoints.append("后续财报中净利润增速是否改善")
    if cfo_ratio is not None and cfo_ratio < 1:
        watchpoints.append("经营现金流能否跟上账面利润")
    if pe_pct is not None and pe_pct > 70:
        watchpoints.append("高估值能否被业绩增长消化")
    watchpoints.extend([
        "行业景气度、政策变化和竞争格局是否发生反转",
        "股价跌破交易计划止损位后是否需要重新评估投资假设",
    ])

    return {
        "name": summary_data.get("name", ""),
        "ts_code": summary_data.get("ts_code", ""),
        "rating": rating,
        "rating_period": "6-12个月",
        "total_score": total_score,
        "risk_level": risk_level,
        "risk_reward": risk_reward,
        "valuation_score": valuation_score,
        "quality_score": quality_score,
        "growth_score": growth_score,
        "market_score": market_score,
        "risk_score": risk_score,
        "cur_price": cur_price,
        "price_bear": price_bear,
        "price_base": price_base,
        "price_bull": price_bull,
        "base_upside": base_upside,
        "bull_upside": bull_upside,
        "bear_downside": bear_downside,
        "buy_zone": buy_zone,
        "watch_zone": watch_zone,
        "take_profit_zone": take_profit_zone,
        "stop_loss": stop_loss,
        "action": action,
        "position_plan": position_plan,
        "positives": positives[:5],
        "risks": risks[:5],
        "watchpoints": watchpoints[:5],
        "score_detail": {
            "valuation": valuation,
            "quality": quality,
            "growth": growth,
            "market": market,
        },
    }


def render_stock_research_brief(view: dict) -> str:
    """Render the structured research view as compact markdown."""
    if not view:
        return "专业投研模型：关键数据不足，无法形成结构化交易计划。"

    def zone_text(zone):
        if not zone:
            return "N/A"
        return f"{zone[0]:.2f}-{zone[1]:.2f}元"

    lines = [
        "### 专业投研模型结论",
        f"- 评级：{view.get('rating', 'N/A')}（周期：{view.get('rating_period', 'N/A')}；风险等级：{view.get('risk_level', 'N/A')}）",
        f"- 综合得分：{view.get('total_score', 'N/A')}（估值{view.get('valuation_score', 0)} / 质量{view.get('quality_score', 0)} / 成长{view.get('growth_score', 0)} / 资金技术{view.get('market_score', 0)} / 风险{view.get('risk_score', 0)}）",
        f"- 当前价格：{_fmt(view.get('cur_price'), '元', 2)}；谨慎/中性/乐观价值：{_fmt(view.get('price_bear'), '元', 2)} / {_fmt(view.get('price_base'), '元', 2)} / {_fmt(view.get('price_bull'), '元', 2)}",
        f"- 安全边际买入区：{zone_text(view.get('buy_zone'))}；观察区：{zone_text(view.get('watch_zone'))}；分批止盈区：{zone_text(view.get('take_profit_zone'))}；复盘止损位：{_fmt(view.get('stop_loss'), '元', 2)}",
        f"- 中性空间：{_fmt(view.get('base_upside'), '%')}；谨慎情景回撤：{_fmt(view.get('bear_downside'), '%')}；风险收益比：{view.get('risk_reward') if view.get('risk_reward') is not None else 'N/A'}",
        f"- 操作策略：{view.get('action', 'N/A')}",
        f"- 仓位计划：{view.get('position_plan', 'N/A')}",
        "",
        "核心正向证据：",
    ]
    lines.extend([f"- {item}" for item in view.get("positives", [])])
    lines.append("主要风险：")
    lines.extend([f"- {item}" for item in view.get("risks", [])])
    lines.append("后续复盘触发器：")
    lines.extend([f"- {item}" for item in view.get("watchpoints", [])])
    return "\n".join(lines)
