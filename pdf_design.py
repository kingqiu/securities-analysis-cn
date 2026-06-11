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
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle


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
    table = Table(data, colWidths=col_widths, repeatRows=1)
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
