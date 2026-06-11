#!/usr/bin/env python3
"""Deterministic ETF allocation and trading-plan model."""

from __future__ import annotations


def _f(value, default=None):
    try:
        if value in ("", None, "N/A"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def classify_etf(name: str, index_code: str = "") -> str:
    text = f"{name} {index_code}"
    if any(k in text for k in ("沪深300", "中证500", "创业板", "科创50", "上证50", "500", "300")):
        return "宽基/核心指数"
    if any(k in text for k in ("酒", "消费", "医药", "芯片", "半导体", "新能源", "军工", "券商", "银行")):
        return "行业/主题指数"
    if any(k in text for k in ("红利", "价值", "低波")):
        return "策略指数"
    return "指数基金"


def build_etf_research_view(summary: dict) -> dict:
    name = summary.get("name", "")
    etf_type = classify_etf(name, summary.get("index_code", ""))
    ret_1m = _f(summary.get("ret_1m"))
    ret_3m = _f(summary.get("ret_3m"))
    ret_1y = _f(summary.get("ret_1y"))
    tracking_error = _f(summary.get("tracking_error"))
    total_fee = _f(summary.get("total_fee"))
    aum = _f(summary.get("aum"))
    pe_pct = _f(summary.get("index_pe_pct"))
    pb_pct = _f(summary.get("index_pb_pct"))
    premium = _f(summary.get("premium"))
    current_price = _f(summary.get("current_price"))
    change_pct = _f(summary.get("change_pct"))
    turnover_rate = _f(summary.get("turnover_rate"))
    amount = _f(summary.get("amount"))
    flow_trend = summary.get("flow_trend", "未知")
    aum_trend = summary.get("aum_trend", "未知")
    ma_position = summary.get("ma_position", "未知")

    allocation = 0
    trading = 0
    notes = []
    risks = []

    val_pct = pe_pct if pe_pct is not None else pb_pct
    if val_pct is not None:
        if val_pct <= 30:
            allocation += 3
            trading += 1
            notes.append(f"指数估值分位约{val_pct:.1f}%，长期配置性价比较好")
        elif val_pct <= 60:
            allocation += 1
            notes.append(f"指数估值分位约{val_pct:.1f}%，处于中性区间")
        elif val_pct >= 80:
            allocation -= 2
            trading -= 1
            risks.append(f"指数估值分位约{val_pct:.1f}%，追高容错率偏低")

    if tracking_error is not None:
        if tracking_error <= 2:
            allocation += 2
            notes.append(f"年化跟踪误差{tracking_error:.2f}%，跟踪质量较好")
        elif tracking_error >= 5:
            allocation -= 1
            risks.append(f"年化跟踪误差{tracking_error:.2f}%，跟踪质量需复核")

    if total_fee is not None:
        if total_fee <= 0.6:
            allocation += 1
            notes.append(f"综合费率{total_fee:.2f}%/年，成本优势较好")
        elif total_fee >= 1.2:
            allocation -= 1
            risks.append(f"综合费率{total_fee:.2f}%/年，同类成本偏高")

    if aum is not None:
        if aum >= 20:
            allocation += 1
            trading += 1
        elif aum < 2:
            allocation -= 2
            trading -= 2
            risks.append("基金规模低于2亿元，需关注清盘和流动性风险")

    if premium is not None:
        if abs(premium) <= 0.3:
            trading += 1
        elif premium > 1:
            trading -= 1
            risks.append(f"场内溢价约{premium:.2f}%，不适合追价买入")
        elif premium < -1:
            notes.append(f"场内折价约{abs(premium):.2f}%，可关注折价收敛机会")

    if change_pct is not None:
        if change_pct >= 3 and val_pct and val_pct >= 60:
            trading -= 1
            risks.append(f"盘中涨幅约{change_pct:.2f}%，且估值不低，不宜追价")
        elif change_pct <= -2 and val_pct is not None and val_pct <= 40:
            notes.append(f"盘中回调约{abs(change_pct):.2f}%，若溢价不高可作为分批观察点")

    if turnover_rate is not None and turnover_rate < 0.2:
        trading -= 1
        risks.append(f"换手率约{turnover_rate:.2f}%，场内流动性偏弱")

    if amount is not None and amount < 20_000_000:
        trading -= 1
        risks.append("成交额低于约2000万元，买卖价差和冲击成本需关注")

    if "多头" in ma_position:
        trading += 1
    elif "空头" in ma_position:
        trading -= 1
        risks.append("净值位于主要均线下方，短期趋势偏弱")

    if flow_trend == "净申购" or aum_trend == "增长":
        trading += 1
        notes.append("份额或规模扩张，资金关注度改善")
    elif flow_trend == "净赎回" and aum_trend == "缩减":
        trading -= 1
        risks.append("份额和规模收缩，短期资金关注度偏弱")

    if ret_1y is not None and ret_1y > 25 and val_pct and val_pct > 60:
        trading -= 1
        risks.append("近一年涨幅较大且估值不低，需防止阶段性回撤")
    if ret_3m is not None and ret_3m < -10 and val_pct and val_pct <= 40:
        notes.append("短期回撤叠加估值偏低，适合定投而非一次性重仓")

    if allocation >= 5:
        allocation_rating = "适合核心配置"
    elif allocation >= 2:
        allocation_rating = "适合定投观察"
    elif allocation >= 0:
        allocation_rating = "中性配置"
    else:
        allocation_rating = "谨慎配置"

    if trading >= 3:
        trading_rating = "可分批买入"
    elif trading >= 1:
        trading_rating = "等待回调低吸"
    elif trading >= -1:
        trading_rating = "观望"
    else:
        trading_rating = "暂缓买入"

    if not notes:
        notes.append("当前数据未形成明显优势，建议结合指数估值和资金趋势继续观察")
    if not risks:
        risks.append("ETF仍承担标的指数系统性波动风险")

    return {
        "etf_type": etf_type,
        "allocation_score": allocation,
        "trading_score": trading,
        "allocation_rating": allocation_rating,
        "trading_rating": trading_rating,
        "current_price": current_price,
        "change_pct": change_pct,
        "turnover_rate": turnover_rate,
        "amount": amount,
        "dca_plan": "适合用定投/分批方式建仓，估值分位越低可提高单期投入；估值进入高分位后转为再平衡。",
        "add_condition": "估值分位低于30%、溢价率接近0且份额不持续萎缩时，可考虑加仓。",
        "rebalance_condition": "估值分位高于80%、短期涨幅过快或场内溢价超过1%时，考虑止盈或再平衡。",
        "notes": notes[:6],
        "risks": risks[:6],
    }


def render_etf_research_brief(view: dict) -> str:
    if not view:
        return "ETF配置模型数据不足。"
    lines = [
        f"- ETF类型：{view.get('etf_type')}",
        f"- 配置评级：{view.get('allocation_rating')}（配置分{view.get('allocation_score')}）",
        f"- 交易评级：{view.get('trading_rating')}（交易分{view.get('trading_score')}）",
    ]
    if view.get("current_price") is not None:
        lines.append(
            f"- 场内实时状态：价格{view.get('current_price')}，涨跌幅{view.get('change_pct')}%，换手率{view.get('turnover_rate')}%"
        )
    lines.extend([
        f"- 定投计划：{view.get('dca_plan')}",
        f"- 加仓条件：{view.get('add_condition')}",
        f"- 止盈/再平衡：{view.get('rebalance_condition')}",
        "核心依据：",
    ])
    lines.extend([f"  - {x}" for x in view.get("notes", [])])
    lines.append("主要风险：")
    lines.extend([f"  - {x}" for x in view.get("risks", [])])
    return "\n".join(lines)
