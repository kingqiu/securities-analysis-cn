#!/usr/bin/env python3
"""
Peer comparison helpers for A-share reports.

The goal is to distinguish the target company from:
- direct industry peers
- market-cap leaders
- quality leaders
- valuation anchors
"""

from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default=None):
    if value in (None, "", "N/A", "None"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt(value, suffix="", digits=1):
    v = _safe_float(value)
    if v is None:
        return "N/A"
    return f"{v:.{digits}f}{suffix}"


def _median(values: list[float]):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def _percentile_rank(values: list[float], current):
    cur = _safe_float(current)
    vals = [v for v in values if v is not None]
    if cur is None or not vals:
        return None
    return round(sum(1 for v in vals if v < cur) / len(vals) * 100, 1)


def _label_peer(peer: dict, leader_codes: set, quality_code, value_code):
    labels = []
    code = peer.get("ts_code")
    if code in leader_codes:
        labels.append("市值龙头")
    if quality_code and code == quality_code:
        labels.append("质量标杆")
    if value_code and code == value_code:
        labels.append("估值锚")
    return " / ".join(labels) if labels else "直接可比"


def build_peer_view(target: dict, industry_peers: dict | None) -> dict:
    if not industry_peers or not industry_peers.get("peers"):
        return {}

    peers = [p for p in industry_peers.get("peers", []) if p.get("ts_code")]
    if not peers:
        return {}

    pe_values = [_safe_float(p.get("pe_ttm")) for p in peers]
    pb_values = [_safe_float(p.get("pb")) for p in peers]
    roe_values = [_safe_float(p.get("roe")) for p in peers]
    mv_values = [_safe_float(p.get("mv_bn")) for p in peers]

    valid_mv = [p for p in peers if _safe_float(p.get("mv_bn")) is not None]
    leaders = sorted(valid_mv, key=lambda p: _safe_float(p.get("mv_bn"), 0), reverse=True)[:3]
    leader_codes = {p.get("ts_code") for p in leaders}

    quality_candidates = [p for p in peers if _safe_float(p.get("roe")) is not None]
    quality_leader = max(quality_candidates, key=lambda p: _safe_float(p.get("roe"), -999), default=None)
    value_candidates = [p for p in peers if _safe_float(p.get("pe_ttm")) is not None and _safe_float(p.get("pe_ttm")) > 0]
    value_anchor = min(value_candidates, key=lambda p: _safe_float(p.get("pe_ttm"), 9999), default=None)

    target_pe = _safe_float(target.get("pe_ttm"))
    target_pb = _safe_float(target.get("pb"))
    target_roe = _safe_float(target.get("roe"))
    target_mv = _safe_float(target.get("mv_bn"))
    industry_pe_median = _median([v for v in pe_values if v and v > 0])
    industry_pb_median = _median([v for v in pb_values if v and v > 0])
    industry_roe_median = _median([v for v in roe_values if v is not None])
    industry_mv_median = _median([v for v in mv_values if v is not None])

    pe_pct = _percentile_rank([v for v in pe_values if v and v > 0], target_pe)
    roe_pct = _percentile_rank([v for v in roe_values if v is not None], target_roe)
    mv_pct = _percentile_rank([v for v in mv_values if v is not None], target_mv)

    peer_rows = []
    quality_code = quality_leader.get("ts_code") if quality_leader else None
    value_code = value_anchor.get("ts_code") if value_anchor else None
    for peer in sorted(peers, key=lambda p: _safe_float(p.get("mv_bn"), 0), reverse=True)[:8]:
        peer_rows.append({
            "name": peer.get("name") or peer.get("ts_code"),
            "ts_code": peer.get("ts_code"),
            "role": _label_peer(peer, leader_codes, quality_code, value_code),
            "mv_bn": _safe_float(peer.get("mv_bn")),
            "pe_ttm": _safe_float(peer.get("pe_ttm")),
            "pb": _safe_float(peer.get("pb")),
            "roe": _safe_float(peer.get("roe")),
            "gross_margin": _safe_float(peer.get("gross_margin")),
            "rev_growth": _safe_float(peer.get("rev_growth")),
            "profit_growth": _safe_float(peer.get("profit_growth")),
        })

    target_role = "目标公司"
    if mv_pct is not None and mv_pct >= 80:
        target_role += " / 行业头部"
    if roe_pct is not None and roe_pct >= 75:
        target_role += " / 质量领先"
    if pe_pct is not None and pe_pct <= 30:
        target_role += " / 估值折价"

    interpretation = []
    if industry_pe_median and target_pe:
        if target_pe < industry_pe_median * 0.85:
            interpretation.append("目标公司估值低于同行中位数，可能存在折价机会，但需确认折价是否来自成长或治理风险。")
        elif target_pe > industry_pe_median * 1.2:
            interpretation.append("目标公司估值高于同行中位数，需要更强的盈利质量、成长性或行业地位来支撑溢价。")
        else:
            interpretation.append("目标公司估值接近同行中位数，投资结论更依赖基本面质量和增长持续性。")
    if industry_roe_median and target_roe:
        if target_roe > industry_roe_median:
            interpretation.append("目标公司ROE高于同行中位数，说明股东回报质量相对更好。")
        else:
            interpretation.append("目标公司ROE未明显领先同行，估值溢价需要谨慎看待。")
    if leaders and target_mv:
        top = leaders[0]
        top_mv = _safe_float(top.get("mv_bn"))
        if top_mv and target_mv < top_mv * 0.5:
            interpretation.append(f"相较行业市值龙头{top.get('name') or top.get('ts_code')}，目标公司体量仍有差距，应关注份额提升空间与竞争压力。")

    return {
        "industry": industry_peers.get("industry", ""),
        "trade_date": industry_peers.get("trade_date", ""),
        "peer_count": len(peers),
        "target_role": target_role,
        "target": {
            "name": target.get("name"),
            "ts_code": target.get("ts_code"),
            "role": target_role,
            "mv_bn": target_mv,
            "pe_ttm": target_pe,
            "pb": target_pb,
            "roe": target_roe,
            "gross_margin": _safe_float(target.get("gross_margin")),
            "rev_growth": _safe_float(target.get("rev_growth")),
            "profit_growth": _safe_float(target.get("profit_growth")),
        },
        "industry_median": {
            "mv_bn": industry_mv_median,
            "pe_ttm": industry_pe_median,
            "pb": industry_pb_median,
            "roe": industry_roe_median,
        },
        "percentile": {
            "pe_ttm": pe_pct,
            "roe": roe_pct,
            "mv_bn": mv_pct,
        },
        "leaders": leaders,
        "quality_leader": quality_leader,
        "value_anchor": value_anchor,
        "peer_rows": peer_rows,
        "interpretation": interpretation,
    }


def render_peer_brief(view: dict) -> str:
    if not view:
        return "同行对比：可比公司数据不足，暂无法形成龙头参照。"

    med = view.get("industry_median", {})
    pct = view.get("percentile", {})
    lines = [
        "### 同行龙头参照结论",
        f"- 行业：{view.get('industry', 'N/A')}；可比样本：{view.get('peer_count', 0)}只；目标定位：{view.get('target_role', 'N/A')}",
        f"- 行业中位数：PE {_fmt(med.get('pe_ttm'))} / PB {_fmt(med.get('pb'))} / ROE {_fmt(med.get('roe'), '%')}",
        f"- 目标分位：PE处于同行{_fmt(pct.get('pe_ttm'), '%')}分位，ROE处于同行{_fmt(pct.get('roe'), '%')}分位，市值处于同行{_fmt(pct.get('mv_bn'), '%')}分位。",
    ]

    if view.get("leaders"):
        leader_names = "、".join([p.get("name") or p.get("ts_code") for p in view["leaders"][:3]])
        lines.append(f"- 市值龙头参照：{leader_names}")
    if view.get("quality_leader"):
        p = view["quality_leader"]
        lines.append(f"- 质量标杆：{p.get('name') or p.get('ts_code')}（ROE {_fmt(p.get('roe'), '%')}）")
    if view.get("value_anchor"):
        p = view["value_anchor"]
        lines.append(f"- 估值锚：{p.get('name') or p.get('ts_code')}（PE {_fmt(p.get('pe_ttm'))}）")

    lines.append("专业解读：")
    lines.extend([f"- {item}" for item in view.get("interpretation", [])])
    return "\n".join(lines)
