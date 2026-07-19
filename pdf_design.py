#!/usr/bin/env python3
"""Shared ReportLab design system for securities research PDFs."""

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle


def register_cn_font():
    candidates = [
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
        "/Library/Fonts/Arial Unicode MS.ttf",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("CN", path))
                return "CN"
            except Exception:
                continue
    return "Helvetica"


CN_FONT = register_cn_font()


THEMES = {
    "stock": {
        "accent": "#A33A3A",
        "accent_dark": "#6E1F28",
        "accent_soft": "#F8ECEC",
        "cover_tint": "#F5E7E4",
        "label": "A-SHARE EQUITY RESEARCH",
    },
    "hk": {
        "accent": "#2864A6",
        "accent_dark": "#14395F",
        "accent_soft": "#EAF1F8",
        "cover_tint": "#E6EEF7",
        "label": "HONG KONG EQUITY RESEARCH",
    },
    "etf": {
        "accent": "#1E7C78",
        "accent_dark": "#124F4D",
        "accent_soft": "#E7F4F1",
        "cover_tint": "#E3F0EE",
        "label": "ETF AND INDEX FUND RESEARCH",
    },
}

BASE = {
    "ink": "#18202A",
    "muted": "#5E6874",
    "subtle": "#8A949F",
    "line": "#D9DEE5",
    "panel": "#F7F8FA",
    "header": "#EEF1F5",
    "zebra": "#FAFBFC",
}


def theme_for(kind):
    theme = dict(BASE)
    theme.update(THEMES.get(kind, THEMES["stock"]))
    return theme


def build_styles(kind="stock"):
    theme = theme_for(kind)

    def s(name, **kw):
        return ParagraphStyle(name, fontName=CN_FONT, **kw)

    return {
        "title": s(
            "T",
            fontSize=25,
            leading=31,
            alignment=TA_LEFT,
            spaceAfter=8,
            textColor=colors.HexColor(theme["ink"]),
        ),
        "subtitle": s(
            "ST",
            fontSize=12,
            leading=18,
            alignment=TA_LEFT,
            spaceAfter=4,
            textColor=colors.HexColor(theme["muted"]),
        ),
        "cover_label": s(
            "CL",
            fontSize=7.5,
            leading=10,
            alignment=TA_LEFT,
            textColor=colors.HexColor(theme["accent_dark"]),
        ),
        "cover_meta": s(
            "CM",
            fontSize=9,
            leading=14,
            alignment=TA_LEFT,
            textColor=colors.HexColor(theme["muted"]),
        ),
        "cover_title": s(
            "CoverTitle",
            fontSize=31,
            leading=38,
            alignment=TA_LEFT,
            spaceAfter=5,
            textColor=colors.HexColor(theme["ink"]),
        ),
        "cover_subtitle": s(
            "CoverSubtitle",
            fontSize=14,
            leading=20,
            alignment=TA_LEFT,
            spaceAfter=4,
            textColor=colors.HexColor(theme["muted"]),
        ),
        "cover_big": s(
            "CoverBig",
            fontSize=22,
            leading=28,
            alignment=TA_LEFT,
            textColor=colors.HexColor(theme["ink"]),
        ),
        "h1": s(
            "H1",
            fontSize=14,
            leading=20,
            spaceBefore=14,
            spaceAfter=7,
            textColor=colors.HexColor(theme["accent_dark"]),
        ),
        "h2": s(
            "H2",
            fontSize=11.2,
            leading=16,
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.HexColor(theme["ink"]),
        ),
        "body": s(
            "B",
            fontSize=9.6,
            leading=15,
            spaceAfter=4,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor(theme["ink"]),
        ),
        "caption": s(
            "C",
            fontSize=7.6,
            leading=11,
            textColor=colors.HexColor(theme["subtle"]),
            alignment=TA_CENTER,
        ),
        "small": s(
            "S",
            fontSize=7.8,
            leading=11,
            textColor=colors.HexColor(theme["muted"]),
        ),
        "card_label": s(
            "CardLabel",
            fontSize=7.4,
            leading=10,
            textColor=colors.HexColor(theme["muted"]),
        ),
        "card_value": s(
            "CardValue",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor(theme["ink"]),
        ),
        "callout": s(
            "Callout",
            fontSize=9.3,
            leading=14,
            textColor=colors.HexColor(theme["ink"]),
        ),
        "advice": s(
            "A",
            fontSize=9.6,
            leading=15,
            spaceAfter=4,
            textColor=colors.HexColor(theme["ink"]),
        ),
    }


def _as_para(value, style):
    if isinstance(value, Paragraph):
        return value
    return Paragraph(str(value), style)


def styled_table(data, col_widths=None, kind="stock", compact=False, numeric_cols=None):
    theme = theme_for(kind)
    font_size = 8.2 if compact else 8.7
    pad_y = 3 if compact else 5

    # 自动将含 HTML 标记的单元格包装为 Paragraph（否则 <font> 等标签会原样显示）
    body_style = ParagraphStyle(
        name=f"_tbl_body_{kind}", fontName=CN_FONT,
        fontSize=font_size, leading=font_size + 3,
        alignment=0,  # LEFT; 表格内 ALIGN 由 TableStyle 控制
        wordWrap="CJK",
    )
    wrapped_data = []
    for ri, row in enumerate(data):
        wr = []
        for ci, cell in enumerate(row):
            # 已是 Flowable（如 Paragraph）→ 透传，避免 str(Paragraph) 得到 repr 再二次包装
            if isinstance(cell, Flowable):
                wr.append(cell)
                continue
            s = str(cell) if cell is not None else ""
            # 首行表头、含 XML 标记、或含 CJK / 长文本 → 包装为 Paragraph 以支持自动换行。
            # 裸字符串在 ReportLab Table 中不换行，会导致长中文溢出/重叠。
            if ri == 0 or "<" in s or len(s) > 15 or any("\u4e00" <= ch <= "\u9fff" for ch in s):
                wr.append(Paragraph(s, body_style))
            else:
                wr.append(s)
        wrapped_data.append(wr)

    table = Table(wrapped_data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme["header"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(theme["ink"])),
        ("FONTNAME", (0, 0), (-1, -1), CN_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("LEADING", (0, 0), (-1, -1), font_size + 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(theme["zebra"])]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(theme["accent"])),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor(theme["line"])),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad_y),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad_y),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ])
    if numeric_cols:
        for col in numeric_cols:
            style.add("ALIGN", (col, 1), (col, -1), "RIGHT")
    table.setStyle(style)
    return table


def metric_cards(items, kind="stock", columns=3):
    theme = theme_for(kind)
    styles = build_styles(kind)
    cells = []
    for item in items:
        label, value, note = item if len(item) == 3 else (item[0], item[1], "")
        content = [
            _as_para(label, styles["card_label"]),
            Spacer(1, 0.04 * cm),
            _as_para(value, styles["card_value"]),
        ]
        if note:
            content.extend([Spacer(1, 0.03 * cm), _as_para(note, styles["small"])])
        cells.append(content)

    rows = []
    for idx in range(0, len(cells), columns):
        row = cells[idx:idx + columns]
        while len(row) < columns:
            row.append("")
        rows.append(row)

    table = Table(rows, colWidths=[16 * cm / columns] * columns, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(theme["panel"])),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor(theme["line"])),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(theme["line"])),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]))
    return table


def callout_box(text, kind="stock"):
    theme = theme_for(kind)
    styles = build_styles(kind)
    table = Table([[Paragraph(text, styles["callout"])]], colWidths=[16 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(theme["accent_soft"])),
        ("LINEBEFORE", (0, 0), (0, -1), 2.0, colors.HexColor(theme["accent"])),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor(theme["line"])),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return table


def _cover_meta_strip(meta_rows, kind):
    theme = theme_for(kind)
    pairs = []
    for label, value in meta_rows:
        pairs.extend([label, value])
    if len(pairs) % 2:
        pairs.append("")
    rows = []
    for idx in range(0, len(pairs), 4):
        row = pairs[idx:idx + 4]
        while len(row) < 4:
            row.append("")
        rows.append(row)
    table = Table(rows, colWidths=[2.0 * cm, 5.5 * cm, 2.0 * cm, 5.5 * cm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), CN_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(theme["ink"])),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(theme["muted"])),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor(theme["muted"])),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor(theme["line"])),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _cover_bands(bands, kind):
    if not bands:
        return None
    theme = theme_for(kind)
    styles = build_styles(kind)
    palette = [
        ("#E6F2EA", "#2F7D4F"),
        ("#FFF4D6", "#9A6A00"),
        (theme["accent_soft"], theme["accent_dark"]),
    ]
    cells = []
    for idx, item in enumerate(bands[:3]):
        label, value, note = item if len(item) == 3 else (item[0], item[1], "")
        bg, fg = palette[idx % len(palette)]
        cell = [
            Paragraph(f"<font color='{fg}'>{label}</font>", styles["card_label"]),
            Spacer(1, 0.06 * cm),
            Paragraph(str(value), styles["card_value"]),
        ]
        if note:
            cell.append(Paragraph(str(note), styles["small"]))
        cells.append(cell)
    while len(cells) < 3:
        cells.append("")
    band_value = ParagraphStyle(
        "BandValue",
        fontName=CN_FONT,
        fontSize=10.2,
        leading=13,
        textColor=colors.HexColor(theme["ink"]),
    )
    for cell in cells:
        if isinstance(cell, list) and len(cell) > 2:
            cell[2] = Paragraph(cell[2].getPlainText(), band_value) if isinstance(cell[2], Paragraph) else Paragraph(str(cell[2]), band_value)
    table = Table([cells], colWidths=[5.2 * cm, 4.4 * cm, 5.4 * cm], rowHeights=[1.9 * cm], hAlign="LEFT")
    table_style = TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor(theme["line"])),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(theme["line"])),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])
    for idx in range(3):
        table_style.add("BACKGROUND", (idx, 0), (idx, 0), colors.HexColor(palette[idx][0]))
    table.setStyle(table_style)
    return table


def evidence_map(story, rows, kind="stock"):
    theme = theme_for(kind)
    styles = build_styles(kind)
    story.append(Paragraph("研究假设与证据地图", styles["h1"]))
    story.append(Paragraph(
        "本节不是给出确定性判断，而是把当前可见数据整理为研究假设、证据强度和后续观察方向。证据强度较弱的部分仅用于提示思考，不应单独作为决策依据。",
        styles["caption"],
    ))
    story.append(Spacer(1, 0.15 * cm))

    head_style = ParagraphStyle(
        "EvidenceHead",
        fontName=CN_FONT,
        fontSize=7.6,
        leading=10,
        textColor=colors.HexColor(theme["ink"]),
    )
    body_style = ParagraphStyle(
        "EvidenceBody",
        fontName=CN_FONT,
        fontSize=7.4,
        leading=10.5,
        textColor=colors.HexColor(theme["ink"]),
    )
    muted_style = ParagraphStyle(
        "EvidenceMuted",
        parent=body_style,
        textColor=colors.HexColor(theme["muted"]),
    )

    table_data = [[
        Paragraph("研究假设", head_style),
        Paragraph("当前可见证据", head_style),
        Paragraph("强度", head_style),
        Paragraph("如何理解", head_style),
        Paragraph("还需观察", head_style),
    ]]
    for row in rows:
        hypothesis, evidence, strength, reading, watch = row
        table_data.append([
            Paragraph(str(hypothesis), body_style),
            Paragraph(str(evidence), muted_style),
            Paragraph(str(strength), body_style),
            Paragraph(str(reading), body_style),
            Paragraph(str(watch), muted_style),
        ])

    table = Table(
        table_data,
        colWidths=[3.0 * cm, 3.5 * cm, 1.5 * cm, 4.2 * cm, 3.8 * cm],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme["header"])),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(theme["accent"])),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(theme["zebra"])]),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor(theme["line"])),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(theme["line"])),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.3 * cm))


def add_followup_watchlist(story, rows, kind="stock"):
    theme = theme_for(kind)
    styles = build_styles(kind)
    block = [
        Paragraph("后续重点观察清单", styles["h1"]),
        Paragraph(
            "以下清单用于提示后续复盘重点。观察窗口代表适合重新检查证据的时间范围，不对应任何交易动作。",
            styles["caption"],
        ),
        Spacer(1, 0.12 * cm),
    ]

    head_style = ParagraphStyle(
        "WatchHead",
        fontName=CN_FONT,
        fontSize=7.8,
        leading=10.5,
        textColor=colors.HexColor(theme["ink"]),
        alignment=1,
    )
    body_style = ParagraphStyle(
        "WatchBody",
        fontName=CN_FONT,
        fontSize=7.6,
        leading=10.8,
        textColor=colors.HexColor(theme["ink"]),
    )
    table_data = [[Paragraph(str(item), head_style) for item in ["观察主题", "当前证据", "观察窗口", "复核重点"]]]
    for row in rows:
        table_data.append([Paragraph(str(item), body_style) for item in row])

    table = styled_table(
        table_data,
        col_widths=[3.1 * cm, 4.7 * cm, 3.5 * cm, 4.7 * cm],
        kind=kind,
        compact=True,
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    block.append(table)
    block.append(Spacer(1, 0.35 * cm))
    story.append(KeepTogether(block))


def add_report_reading_guide(story, kind="stock", report_type="single"):
    styles = build_styles(kind)
    theme = theme_for(kind)
    head_style = ParagraphStyle(
        "GuideHead",
        fontName=CN_FONT,
        fontSize=8.0,
        leading=11,
        textColor=colors.HexColor(theme["ink"]),
        alignment=1,
    )
    cell_style = ParagraphStyle(
        "GuideCell",
        fontName=CN_FONT,
        fontSize=7.9,
        leading=11.2,
        textColor=colors.HexColor(theme["ink"]),
    )

    def _guide_table(headers, rows, widths):
        table_data = [[Paragraph(str(item), head_style) for item in headers]]
        table_data.extend([[Paragraph(str(item), cell_style) for item in row] for row in rows])
        table = styled_table(table_data, col_widths=widths, kind=kind, compact=True)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    story.append(Paragraph("如何阅读本报告", styles["h1"]))
    story.append(callout_box(
        "本报告用于把公开行情、财务、估值、资金、产品和新闻信息整理成研究框架。建议把结论理解为“需要继续观察的问题清单”，而不是对价格方向或交易动作的判断。",
        kind,
    ))
    story.append(Spacer(1, 0.12 * cm))

    if report_type == "comparison":
        reading_rows = [
            ["对比范围", "先确认标的是否处在相近市场、行业、指数或产品类型。", "综合得分只是相对证据排序，不代表配置结论。"],
            ["指标比较", "重点看估值、成长、盈利质量、现金流、规模、费用和流动性。", "跨行业、跨市场、跨币种指标不能简单横向等同。"],
            ["模型解读", "把模型文字当作阅读提示，回到原始数据验证分歧。", "模型解读不是交易判断，也不能替代个人风险约束。"],
        ]
    elif kind == "etf":
        reading_rows = [
            ["指数暴露", "先看跟踪指数、估值分位、行业权重和成分集中度。", "指数估值偏低不代表未来一定上涨。"],
            ["产品质量", "再看跟踪误差、费率、规模、成交额和折溢价。", "短期涨跌不能替代产品质量判断。"],
            ["观察触发器", "用于复盘估值、流动性和跟踪质量是否变化。", "触发器不是配置或交易指令。"],
        ]
    elif kind == "hk":
        reading_rows = [
            ["基本面与估值", "先看盈利质量、估值、业务分部和监管敏感度。", "低估值可能包含流动性折价或风险补偿。"],
            ["港股特有变量", "重点看南向资金、成交额、汇率、分红和回购。", "短期资金流不等于基本面变化。"],
            ["观察触发器", "用于复核估值、流动性和汇率假设。", "触发器不是买卖判断。"],
        ]
    else:
        reading_rows = [
            ["基本面质量", "先看ROE、增长、毛利率、现金流和负债。", "单一指标较好不代表整体质量稳定。"],
            ["估值与同行", "再看历史分位、同行位置和三情景价值。", "低估值可能来自基本面折价。"],
            ["观察触发器", "最后看趋势、成交、资金和反证条件。", "价格区间不是交易指令。"],
        ]

    story.append(_guide_table(
        ["阅读模块", "重点看什么", "容易误读的地方"],
        reading_rows,
        [3.2 * cm, 6.2 * cm, 6.6 * cm],
    ))
    story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph("研究假设可能失效的情形", styles["h1"]))
    story.append(Paragraph(
        "以下内容用于提醒读者：当关键数据、市场结构或外部条件发生变化时，前文分析需要重新复核。它不是风险预测，而是帮助建立复盘习惯。",
        styles["caption"],
    ))
    story.append(Spacer(1, 0.12 * cm))

    if report_type == "comparison":
        invalid_rows = [
            ["可比性下降", "样本业务、指数暴露或市场结构差异扩大", "先重审为什么选择这些标的进行比较。"],
            ["评分权重失真", "单一指标异常拉高或拉低综合结果", "拆开各维度观察，不只看总分。"],
            ["数据口径不一致", "市场、币种、财报周期、费用或规模口径不同", "统一口径后再做横向解读。"],
        ]
    elif kind == "etf":
        invalid_rows = [
            ["指数暴露假设变化", "指数估值、行业权重或成分集中度明显变化", "重新确认它是否仍代表预期资产暴露。"],
            ["产品质量走弱", "跟踪误差扩大、规模或份额持续萎缩、成交额下降", "复核跟踪质量、流动性和清盘风险。"],
            ["场内价格偏离", "折溢价显著扩大、盘中成交深度不足", "结合IOPV、成交额和申赎机制判断偏离是否短期。"],
        ]
    elif kind == "hk":
        invalid_rows = [
            ["流动性折价扩大", "成交额下降、换手不足、南向资金连续转弱", "复核估值折价是否来自流动性和风险偏好。"],
            ["汇率或监管假设变化", "人民币/港元波动、监管政策边际变化", "区分业务基本面变化和外部估值扰动。"],
            ["股东回报不及预期", "回购减少、派息政策变化、自由现金流承压", "复核分红和回购对估值支撑的可持续性。"],
        ]
    else:
        invalid_rows = [
            ["盈利假设被削弱", "收入或利润增速放缓、现金流跟不上利润、费用率抬升", "回到财报和经营现金流重新验证质量。"],
            ["估值锚失效", "行业估值中枢下移、利率或风险偏好变化、同行预期下修", "不要只看历史分位，重算相对同行和情景空间。"],
            ["行业或政策反转", "需求、价格、库存、监管或竞争格局明显变化", "把行业动态和公司财报交叉验证。"],
        ]

    story.append(_guide_table(
        ["失效情形", "可观察信号", "复核方式"],
        invalid_rows,
        [4.1 * cm, 6.0 * cm, 5.9 * cm],
    ))
    story.append(PageBreak())


def _default_cover_questions(kind):
    if kind == "etf":
        return ["指数估值与配置价值", "跟踪质量与流动性", "费率、溢价与再平衡风险"]
    if kind == "hk":
        return ["基本面与估值锚", "南向资金与流动性折价", "汇率、回购与监管敏感度"]
    return ["估值与安全边际", "基本面质量", "同行比较与风险暴露"]


def _cover_questions(questions, kind):
    theme = theme_for(kind)
    styles = build_styles(kind)
    question_style = ParagraphStyle(
        "CoverQuestion",
        parent=styles["body"],
        fontName=CN_FONT,
        fontSize=10.8,
        leading=15,
        textColor=colors.HexColor(theme["ink"]),
    )
    cells = []
    for idx, item in enumerate((questions or _default_cover_questions(kind))[:3], start=1):
        cells.append([
            Paragraph(f"<font color='{theme['accent_dark']}'>0{idx}</font>", styles["card_label"]),
            Spacer(1, 0.05 * cm),
            Paragraph(str(item), question_style),
        ])
    while len(cells) < 3:
        cells.append("")
    table = Table([cells], colWidths=[5.0 * cm, 5.0 * cm, 5.0 * cm], rowHeights=[1.55 * cm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(theme["panel"])),
        ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor(theme["line"])),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(theme["line"])),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.HexColor(theme["accent"])),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _cover_notes(notes, kind):
    theme = theme_for(kind)
    styles = build_styles(kind)
    label_style = ParagraphStyle(
        "CoverNoteLabel",
        parent=styles["card_label"],
        fontName=CN_FONT,
        fontSize=8.2,
        leading=11,
        textColor=colors.HexColor(theme["muted"]),
    )
    body_style = ParagraphStyle(
        "CoverNoteBody",
        parent=styles["body"],
        fontName=CN_FONT,
        fontSize=10.7,
        leading=16,
        textColor=colors.HexColor(theme["ink"]),
    )
    cells = []
    for item in (notes or [])[:3]:
        label, body = item if len(item) == 2 else (item[0], item[1])
        cells.append([
            Paragraph(str(label), label_style),
            Spacer(1, 0.1 * cm),
            Paragraph(str(body), body_style),
        ])
    if not cells:
        cells = [
            [Paragraph("核心结论", label_style), Paragraph("请结合后文估值、基本面、同行比较和风险章节阅读。", body_style)],
            [Paragraph("关注变量", label_style), Paragraph("估值分位、盈利质量、现金流、行业景气度和市场波动。", body_style)],
            [Paragraph("主要风险", label_style), Paragraph("业绩变化、流动性、政策变化和市场系统性风险。", body_style)],
        ]
    while len(cells) < 3:
        cells.append("")
    table = Table([cells], colWidths=[5.0 * cm, 5.0 * cm, 5.0 * cm], rowHeights=[3.85 * cm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor(theme["line"])),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(theme["line"])),
        ("TOPPADDING", (0, 0), (-1, -1), 13),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def add_cover(story, title, subtitle, meta_rows, kind="stock", highlights=None, bands=None, notes=None, questions=None):
    theme = theme_for(kind)
    styles = build_styles(kind)
    story.append(Spacer(1, 0.55 * cm))
    label = f"{theme['label']}  |  {datetime.now().strftime('%Y-%m-%d')}"
    story.append(Paragraph(label, styles["cover_label"]))
    story.append(Spacer(1, 0.16 * cm))
    story.append(Table([[""]], colWidths=[4.2 * cm], rowHeights=[0.07 * cm], hAlign="LEFT", style=[
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(theme["accent"])),
    ]))
    story.append(Spacer(1, 0.65 * cm))

    hero = [
        Paragraph(title, styles["cover_title"]),
        Paragraph(subtitle, styles["cover_subtitle"]),
        Spacer(1, 0.28 * cm),
        _cover_meta_strip(meta_rows, kind),
    ]
    story.extend(hero)
    story.append(Spacer(1, 1.15 * cm))

    story.append(Paragraph("本报告关注的问题", styles["h2"]))
    story.append(_cover_questions(questions, kind))
    story.append(Spacer(1, 0.75 * cm))
    story.append(_cover_notes(notes, kind))
    story.append(Spacer(1, 0.55 * cm))
    story.append(callout_box("本报告由公开行情、财务数据和规则化投研模型生成。结论用于研究复盘，不构成任何投资建议。", kind=kind))
    story.append(PageBreak())


def draw_report_footer(canvas, doc, kind="stock"):
    theme = theme_for(kind)
    canvas.saveState()
    width, _ = A4
    y = 1.15 * cm
    canvas.setStrokeColor(colors.HexColor(theme["line"]))
    canvas.setLineWidth(0.3)
    canvas.line(doc.leftMargin, y + 0.35 * cm, width - doc.rightMargin, y + 0.35 * cm)
    canvas.setFont(CN_FONT, 7.2)
    canvas.setFillColor(colors.HexColor(theme["subtle"]))
    canvas.drawString(doc.leftMargin, y, "仅供研究参考 | 请以公司公告和官方披露为准")
    canvas.drawRightString(width - doc.rightMargin, y, f"{doc.page}")
    canvas.restoreState()
