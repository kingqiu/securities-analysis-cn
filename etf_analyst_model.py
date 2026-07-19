#!/usr/bin/env python3
"""Deterministic ETF allocation and scenario-review model."""

from __future__ import annotations


def _f(value, default=None):
    try:
        if value in ("", None, "N/A"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _w(value, suffix="%"):
    """权重/百分比展示：数值→'x.x%'，None/非数值(N/A/未获取)→'未获取'（不留 'N/A%'）。"""
    try:
        return f"{float(value):.1f}{suffix}"
    except (TypeError, ValueError):
        return "未获取"


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
    tracking_bias = _f(summary.get("tracking_bias"))
    premium_pct = _f(summary.get("premium_pct"))
    net_flow_20d = _f(summary.get("net_flow_20d"))
    net_flow_60d = _f(summary.get("net_flow_60d"))
    top10_weight = _f(summary.get("top10_weight"))
    top20_weight = _f(summary.get("top20_weight"))
    flow_trend = summary.get("flow_trend", "未知")
    aum_trend = summary.get("aum_trend", "未知")
    ma_position = summary.get("ma_position", "未知")
    industry_weight_status = summary.get("industry_weight_status", "缺少行业映射")

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
    if tracking_bias is not None and abs(tracking_bias) >= 0.05:
        risks.append(f"日均跟踪偏差约{tracking_bias:.3f}%，需观察是否存在持续系统性偏离")

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
            notes.append(f"当前溢折率约{premium:.2f}%，场内价格与净值偏离较小")
        elif premium > 1:
            trading -= 1
            risks.append(f"场内溢价约{premium:.2f}%，场内价格相对净值偏高，需关注溢价回落")
        elif premium < -1:
            notes.append(f"场内折价约{abs(premium):.2f}%，可关注折价收敛机会")
    if premium_pct is not None and premium_pct >= 85:
        trading -= 1
        risks.append(f"溢折率处于近一年{premium_pct:.1f}%分位，需防范溢价回落影响持有体验")

    if change_pct is not None:
        if change_pct >= 3 and val_pct and val_pct >= 60:
            trading -= 1
            risks.append(f"盘中涨幅约{change_pct:.2f}%，且估值不低，短期波动容错偏低")
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
    if net_flow_20d is not None:
        notes.append(f"近20日份额变化约{net_flow_20d:.2f}万份，近60日约{net_flow_60d:.2f}万份" if net_flow_60d is not None else f"近20日份额变化约{net_flow_20d:.2f}万份")

    concentration_note = None
    if top10_weight is not None:
        if top10_weight >= 50:
            risks.append(f"指数前十大权重约{top10_weight:.1f}%，集中度较高，需关注龙头股单一风险")
        elif top10_weight >= 30:
            concentration_note = f"指数前十大权重约{top10_weight:.1f}%，集中度中等"
        else:
            concentration_note = f"指数前十大权重约{top10_weight:.1f}%，成分分散度较好"
        if concentration_note:
            notes.append(concentration_note)

    if ret_1y is not None and ret_1y > 25 and val_pct and val_pct > 60:
        trading -= 1
        risks.append("近一年涨幅较大且估值不低，需防止阶段性回撤")
    if ret_3m is not None and ret_3m < -10 and val_pct and val_pct <= 40:
        notes.append("短期回撤叠加估值偏低，更适合用分阶段观察替代一次性判断")

    if allocation >= 5:
        allocation_rating = "适合核心配置"
    elif allocation >= 2:
        allocation_rating = "适合定投观察"
    elif allocation >= 0:
        allocation_rating = "中性配置"
    else:
        allocation_rating = "谨慎配置"

    if trading >= 3:
        trading_rating = "积极观察"
    elif trading >= 1:
        trading_rating = "等待信号"
    elif trading >= -1:
        trading_rating = "观望"
    else:
        trading_rating = "风险复核"

    if not notes:
        notes.append("当前数据未形成明显优势，建议结合指数估值和资金趋势继续观察")
    if not risks:
        risks.append("ETF仍承担标的指数系统性波动风险")

    strategy_fit = {
        "定投": "适合" if allocation >= 2 and (val_pct is None or val_pct <= 70) else "谨慎",
        "波段": "适合" if trading >= 2 and premium is not None and abs(premium) <= 0.5 else "等待信号",
        "资产配置": "适合" if etf_type == "宽基/核心指数" and allocation >= 0 else "卫星配置",
    }

    return {
        "etf_type": etf_type,
        "allocation_score": allocation,
        "trading_score": trading,
        "allocation_rating": allocation_rating,
        "trading_rating": trading_rating,
        "current_price": current_price if current_price is not None else "N/A",
        "change_pct": change_pct if change_pct is not None else "N/A",
        "turnover_rate": turnover_rate if turnover_rate is not None else "N/A",
        "amount": amount if amount is not None else "N/A",
        "tracking_bias": tracking_bias if tracking_bias is not None else "N/A",
        "premium": premium if premium is not None else "N/A",
        "premium_pct": premium_pct if premium_pct is not None else "N/A",
        "net_flow_20d": net_flow_20d if net_flow_20d is not None else "N/A",
        "net_flow_60d": net_flow_60d if net_flow_60d is not None else "N/A",
        "top10_weight": top10_weight if top10_weight is not None else "N/A",
        "top20_weight": top20_weight if top20_weight is not None else "N/A",
        "industry_weight_status": industry_weight_status,
        "strategy_fit": strategy_fit,
        "dca_plan": "可用定期观察框架跟踪估值分位、跟踪误差和规模份额，避免把单日价格当作结论。",
        "add_condition": "估值分位低于30%、溢价率接近0且份额不持续萎缩时，说明配置性价比证据可能增强。",
        "rebalance_condition": "估值分位高于80%、短期涨幅过快或场内溢价超过1%时，需要复核是否已充分反映乐观预期。",
        "notes": notes[:6],
        "risks": risks[:6],
    }


def render_etf_research_brief(view: dict) -> str:
    if not view:
        return "ETF配置模型数据不足。"
    lines = [
        f"- ETF类型：{view.get('etf_type')}",
        f"- 配置研究状态：{view.get('allocation_rating')}（配置分{view.get('allocation_score')}）",
        f"- 场内观察状态：{view.get('trading_rating')}（观察分{view.get('trading_score')}）",
    ]
    if view.get("current_price") is not None:
        lines.append(
            f"- 场内实时状态：价格{view.get('current_price')}，涨跌幅{view.get('change_pct')}%，换手率{view.get('turnover_rate')}%"
        )
    lines.extend([
        f"- 定期观察框架：{view.get('dca_plan')}",
        f"- 正向触发器：{view.get('add_condition')}",
        f"- 高估值复核：{view.get('rebalance_condition')}",
        f"- 策略适配：定投={view.get('strategy_fit', {}).get('定投')}；波段={view.get('strategy_fit', {}).get('波段')}；资产配置={view.get('strategy_fit', {}).get('资产配置')}",
        f"- 成分集中度：前十大{_w(view.get('top10_weight'))}，前二十大{_w(view.get('top20_weight'))}；行业权重状态：{view.get('industry_weight_status')}",
        "核心依据：",
    ])
    lines.extend([f"  - {x}" for x in view.get("notes", [])])
    lines.append("主要风险：")
    lines.extend([f"  - {x}" for x in view.get("risks", [])])
    return "\n".join(lines)


def build_etf_monitor(summary: dict) -> dict:
    """规则化生成 ETF 跟踪监控框架（对标股票报告 §18）。零 token，全部由现有字段推导。"""
    pe_pct = _f(summary.get("index_pe_pct"))
    premium = _f(summary.get("premium"))
    total_fee = _f(summary.get("total_fee"))
    aum = _f(summary.get("aum"))
    te = _f(summary.get("tracking_error"))
    flow = summary.get("flow_trend", "未知")
    amount = _f(summary.get("amount"))

    strengthen = []
    falsify = []
    milestones = []

    if pe_pct is not None:
        strengthen.append(f"指数估值分位回落至 30% 以下（当前 {pe_pct:.1f}%）→ 长期配置性价比证据增强")
    if premium is not None:
        strengthen.append(f"场内溢折率持续接近 0（当前 {premium:.2f}%）→ 价格与净值偏离小，申赎容错高")
    if flow == "净申购":
        strengthen.append("份额/规模不再持续萎缩（近期净申购）→ 资金面企稳")
    if te is not None:
        strengthen.append(f"年化跟踪误差稳定 ≤ 2%（当前 {te:.2f}%）→ 跟踪质量可靠")
    if amount is not None and amount >= 50_000_000:
        strengthen.append(f"成交额维持活跃（近期约 {amount / 1e4:.0f} 万元）→ 流动性无忧")
    if not strengthen:
        strengthen.append("当前数据未形成明显强化信号，建议继续跟踪指数估值、跟踪误差与份额变化")

    if pe_pct is not None:
        falsify.append(f"指数估值分位突破 80%（当前 {pe_pct:.1f}%）→ 追高容错率下降，需复核是否已反映乐观预期")
    if premium is not None and premium > 1:
        falsify.append(f"场内溢价率超过 1%（当前 {premium:.2f}%）→ 价格相对净值偏高，警惕溢价回落")
    elif premium is not None and premium < -3:
        falsify.append(f"场内折价超过 3%（当前 {premium:.2f}%）→ 关注流动性与申赎机制是否异常")
    if aum is not None:
        falsify.append(f"基金规模跌破 2 亿元（当前 {aum:.1f} 亿元）→ 触发清盘/流动性风险预警")
    if te is not None:
        falsify.append(f"年化跟踪误差扩大至 ≥ 5%（当前 {te:.2f}%）→ 复制质量需复核")
    falsify.append("单日涨幅过大且估值不低 → 短期波动容错偏低，需防阶段性回撤")
    if not falsify:
        falsify.append("当前未检出明显证伪信号，但指数系统性下跌与跟踪偏差扩大仍需持续跟踪")

    milestones.append("指数成分股定期调整日（中证指数公司每半年审核，通常 6 月 / 12 月）→ 关注权重股换仓对跟踪与集中度影响")
    milestones.append("基金定期报告 / 季报披露期 → 关注规模与份额变化趋势")
    milestones.append("基金分红公告（若有）→ 关注除息对净值的影响")
    milestones.append("上市公司财报季 → 成分股盈利变化影响指数估值与 PE 分位")

    return {"strengthen": strengthen, "falsify": falsify, "milestones": milestones}


def build_etf_business_model(summary: dict) -> dict:
    """被动指数基金赚钱机制拆解（对标股票报告 §19）。零 token，规则化。"""
    ret_1y = _f(summary.get("ret_1y"))
    total_fee = _f(summary.get("total_fee"))
    m_fee = _f(summary.get("m_fee"))
    c_fee = _f(summary.get("c_fee"))
    te = _f(summary.get("tracking_error"))

    rows = [["维度", "数值 / 判断"]]
    if ret_1y is not None:
        rows.append(["收益来源（β）", f"跟踪指数收益，近1年约 {ret_1y:.2f}% 【事实】"])
    else:
        rows.append(["收益来源（β）", "近1年收益数据不足（日线不足1年）【事实】"])
    if total_fee is not None:
        fee_detail = f"（管理费 {m_fee:.2f}% + 托管费 {c_fee:.2f}%）" if (m_fee is not None and c_fee is not None) else ""
        rows.append(["成本侵蚀", f"综合费率 {total_fee:.2f}%/年{fee_detail}，每年从净值中扣除 【事实】"])
    if te is not None:
        rows.append(["跟踪误差", f"年化 {te:.2f}%，实际与指数的偏离，越高越偏离指数 【事实】"])
    rows.append(["现金拖累", "为应对日常申赎保留的现金/等价物，牛市中轻微跑输指数（规则化）"])
    rows.append(["复制方式", "宽基 ETF 多采用完全复制或抽样复制，以招募说明书为准（规则化）"])
    rows.append(["申赎套利", "机构一篮子申赎使 IOPV 与价格趋同，抑制大幅折溢价（规则化）"])

    erode = total_fee if total_fee is not None else 0.0
    te_v = te if te is not None else 0.0
    narrative = (
        "被动指数基金本身不“创造”超额收益，其赚钱机制是：拿到指数成分股的长期 β 收益，"
        "再减去费率和跟踪误差的损耗。因此选 ETF 的核心看三点：① 跟踪的指数长期有没有 β；"
        "② 费率是否够低（成本按年复利侵蚀）；③ 跟踪误差是否够小。"
    )
    if total_fee is not None or te is not None:
        narrative += (
            f" 本基金综合费率 {total_fee:.2f}%/年、年化跟踪误差 {te:.2f}%，"
            f"意味着长期持有每年约损耗 {erode + te_v:.2f}% 的相对指数收益（不含现金拖累）。"
        )
    return {"rows": rows, "narrative": narrative}


def build_etf_bear_case(view: dict, summary: dict) -> dict:
    """空方逻辑与风险推演（对标股票报告 §21）。量化信号取自配置模型 risks，黑天鹅为规则化情景。零 token。"""
    bear = list(view.get("risks", [])) if view else []
    if not bear:
        bear.append("ETF 仍承担标的指数系统性波动风险，指数下跌时净值同步下跌")

    aum = _f(summary.get("aum"))
    te = _f(summary.get("tracking_error"))

    swans = [
        "指数权重股（如半导体龙头）突发重大负面（财务/合规/技术路线更替）→ 指数单日大幅回撤，ETF 同步下挫且流动性骤降",
        "极端行情下申赎挤兑 + 折溢价异常 → 做市机制短暂失效，IOPV 与价格背离扩大",
    ]
    if te is not None:
        swans.append(f"跟踪误差因大额申赎或成分股停牌异常扩大至 ≥ 5%（当前 {te:.2f}%）→ 长期跑输指数且偏离难控")
    if aum is not None and aum < 20:
        swans.append(f"基金规模持续萎缩（当前 {aum:.1f} 亿元）→ 逼近清盘线，被迫清盘或合并，持有人被动退出")
    swans.append("政策/交易机制变动（涨跌幅、融券、做市规则调整）→ 影响套利与定价效率")
    return {"bear": bear, "swans": swans}
