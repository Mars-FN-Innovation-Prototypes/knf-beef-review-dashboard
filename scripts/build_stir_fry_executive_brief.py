"""Build the stakeholder-facing stir-fry executive one-pager from current analysis data."""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "stir_fry_analysis.json"
LOGO_PATH = ROOT / "brand" / "logo-combined.png"
OUTPUT_PATH = ROOT / "downloads" / "KNF_Stir_Fry_Executive_One_Pager_2026-08-27.pdf"

MARS_BLUE = HexColor("#0000A0")
WATER = HexColor("#19738D")
PEA = HexColor("#62BB46")
RICE = HexColor("#FFF3E8")
CHARCOAL = HexColor("#3C3C3C")
ORANGE = HexColor("#EB6916")
CORN = HexColor("#FFD131")
LIGHT_BLUE = HexColor("#E9F2F5")
LIGHT_GRAY = HexColor("#F4F4F2")
MID_GRAY = HexColor("#767676")


def pstyle(name: str, size: float, leading: float, color=CHARCOAL, bold=False, **kwargs):
    return ParagraphStyle(
        name,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size,
        leading=leading,
        textColor=color,
        alignment=TA_LEFT,
        spaceAfter=0,
        spaceBefore=0,
        **kwargs,
    )


BODY = pstyle("Body", 7.5, 9.5)
BODY_SMALL = pstyle("BodySmall", 6.8, 8.5)
SECTION = pstyle("Section", 8.4, 10.2, MARS_BLUE, bold=True)
KICKER = pstyle("Kicker", 7.1, 8.5, ORANGE, bold=True)
TITLE = pstyle("Title", 18, 19.5, MARS_BLUE, bold=True)
SUBTITLE = pstyle("Subtitle", 8.1, 10.2, WATER)
WHITE_SMALL = pstyle("WhiteSmall", 7, 8.4, white)
CARD_VALUE = pstyle("CardValue", 14, 15, MARS_BLUE, bold=True)
CARD_LABEL = pstyle("CardLabel", 6.4, 7.4, CHARCOAL, bold=True)
CARD_NOTE = pstyle("CardNote", 5.9, 7, MID_GRAY)
CALLOUT = pstyle("Callout", 8.2, 10.2, CHARCOAL)


def draw_paragraph(c, text, style, x, y_top, width, height=200):
    paragraph = Paragraph(text, style)
    _, rendered_height = paragraph.wrap(width, height)
    paragraph.drawOn(c, x, y_top - rendered_height)
    return y_top - rendered_height


def draw_section_heading(c, text, x, y, width):
    c.setFillColor(MARS_BLUE)
    c.rect(x, y - 8, 3, 8, stroke=0, fill=1)
    draw_paragraph(c, text, SECTION, x + 7, y + 1, width - 7)
    return y - 13


def draw_bullet(c, text, x, y, width, style=BODY, color=PEA):
    c.setFillColor(color)
    c.circle(x + 2.5, y - 4.5, 1.6, stroke=0, fill=1)
    return draw_paragraph(c, text, style, x + 9, y, width - 9)


def pct(value):
    return f"{value * 100:.1f}%"


def main():
    analysis = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    overall = analysis["overall"]
    grocery = analysis["cohorts"]["grocery"]["all_written"]
    costco = analysis["cohorts"]["costco_only"]["all_written"]
    value = analysis["value_for_money"]
    source_rows = {row["source"]: row for row in value["by_source"]}

    width, height = letter
    margin = 43
    content_width = width - (margin * 2)
    c = canvas.Canvas(str(OUTPUT_PATH), pagesize=letter)
    c.setTitle("Kevin's Natural Foods Stir-Fry Portfolio Review Analysis")
    c.setAuthor("Mars Food & Nutrition")
    c.setSubject("Executive summary of launch-to-current stir-fry review analysis")
    c.setFillColor(white)
    c.rect(0, 0, width, height, stroke=0, fill=1)

    # Masthead and brand banner.
    c.setFillColor(MID_GRAY)
    c.setFont("Helvetica-Bold", 6.6)
    c.drawString(margin, height - 28, "EXECUTIVE BRIEF  |  STIR-FRY PORTFOLIO SIGNAL")
    c.setFillColor(MARS_BLUE)
    c.rect(0, height - 83, width, 43, stroke=0, fill=1)
    if LOGO_PATH.exists():
        logo = ImageReader(str(LOGO_PATH))
        c.drawImage(logo, width - margin - 178, height - 78, width=178, height=33, preserveAspectRatio=True, anchor="c", mask="auto")

    y = height - 100
    y = draw_paragraph(c, "TODAY, WE'RE LEARNING FROM THE LAUNCH", KICKER, margin, y, content_width)
    y -= 3
    y = draw_paragraph(c, "Kevin's Natural Foods Stir-Fry<br/>Portfolio Review Analysis", TITLE, margin, y, content_width)
    y -= 4
    y = draw_paragraph(
        c,
        "Launch-to-current evidence across 13 products and nine assessed retail channels",
        SUBTITLE,
        margin,
        y,
        content_width,
    )
    y -= 11

    # Bottom-line callout.
    callout_h = 53
    c.setFillColor(RICE)
    c.roundRect(margin, y - callout_h, content_width, callout_h, 5, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.rect(margin, y - callout_h, 5, callout_h, stroke=0, fill=1)
    draw_paragraph(c, "BOTTOM LINE", KICKER, margin + 14, y - 10, content_width - 28)
    draw_paragraph(
        c,
        "Expanded evidence sharpens rather than changes the story: <b>grocery kits carry most value tension</b>, led by serving-size and protein-quantity complaints. Thrive materially increases recent written volume but is mostly incentive-disclosed, so owned-site and non-incentive cuts remain essential.",
        CALLOUT,
        margin + 14,
        y - 24,
        content_width - 28,
    )
    y -= callout_h + 12

    # Four KPI cards.
    gap = 7
    card_w = (content_width - gap * 3) / 4
    card_h = 58
    cards = [
        (f"{grocery['average_rating']:.2f} vs {costco['average_rating']:.2f}", "AVG. WRITTEN RATING", "Grocery vs Costco-only"),
        (f"{pct(grocery['low_star_share'])} vs {pct(costco['low_star_share'])}", "1–2 STAR SHARE", "Grocery vs Costco-only"),
        (f"{value['overall']['low_value_n']} of {overall['n']}", "LOW-VALUE REVIEWS", f"{pct(value['overall']['low_value_share'])} all-time"),
        (str(overall["n"]), "UNIQUE WRITTEN REVIEWS", f"{overall['rated_n']} rated · 5 sources"),
    ]
    for i, (value_text, label, note) in enumerate(cards):
        x = margin + i * (card_w + gap)
        c.setFillColor(LIGHT_GRAY if i % 2 == 0 else LIGHT_BLUE)
        c.roundRect(x, y - card_h, card_w, card_h, 4, stroke=0, fill=1)
        draw_paragraph(c, value_text, CARD_VALUE, x + 9, y - 10, card_w - 18)
        draw_paragraph(c, label, CARD_LABEL, x + 9, y - 30, card_w - 18)
        draw_paragraph(c, note, CARD_NOTE, x + 9, y - 44, card_w - 18)
    y -= card_h + 13

    # Two-column evidence body.
    col_gap = 20
    col_w = (content_width - col_gap) / 2
    left_x = margin
    right_x = margin + col_w + col_gap
    left_y = y
    right_y = y

    left_y = draw_section_heading(c, "Business objective", left_x, left_y, col_w)
    left_y = draw_paragraph(
        c,
        "Establish a launch-to-current consumer read across the 13 specified products, identify product and channel experience gaps, and isolate where formulation, pack, price, or communication follow-up can create the most value. Grocery and Costco-only cohorts remain separate.",
        BODY,
        left_x,
        left_y,
        col_w,
    )
    left_y -= 11
    left_y = draw_section_heading(c, "What the evidence shows", left_x, left_y, col_w)

    product_lines = [
        ("Honey Garlic Chicken kit", "57 reviews · 3.14 avg · 39% 1–2 star · 19 low value"),
        ("General Tso's Chicken kit", "24 reviews · 2.54 avg · 58% 1–2 star · 9 low value"),
        ("Chicken Fajitas", "91 reviews · 3.82 avg · 22% 1–2 star · 17 low value"),
    ]
    for name, detail in product_lines:
        left_y = draw_bullet(c, f"<b>{name}</b><br/><font color='#767676'>{detail}</font>", left_x, left_y, col_w)
        left_y -= 5

    categories = {row["category"]: row["n"] for row in value["by_category"]}
    left_y = draw_bullet(
        c,
        f"<b>Low-value anatomy:</b> {categories['serving_size']} serving-size, {categories['protein_quantity']} protein-quantity, {categories['explicit_price_value']} explicit price/value, and {categories['vegetable_quantity']} vegetable-quantity mentions. Reviews may carry multiple tags.",
        left_x,
        left_y,
        col_w,
        BODY_SMALL,
        ORANGE,
    )
    left_y -= 5
    left_y = draw_bullet(
        c,
        f"<b>Portfolio split:</b> grocery is {grocery['average_rating']:.2f} with {pct(grocery['low_star_share'])} low-star share versus Costco-only at {costco['average_rating']:.2f} and {pct(costco['low_star_share'])}.",
        left_x,
        left_y,
        col_w,
        BODY_SMALL,
    )
    left_y -= 5
    thrive = source_rows["Thrive Market"]
    left_y = draw_bullet(
        c,
        f"<b>Source sensitivity:</b> Thrive adds {thrive['n']} comments; {thrive['disclosed_incentive_n']} disclose Thrive Cash. Excluding all disclosed incentives, low-value share is {pct(value['excluding_disclosed_incentives']['low_value_share'])} versus {pct(value['overall']['low_value_share'])} overall.",
        left_x,
        left_y,
        col_w,
        BODY_SMALL,
        CORN,
    )

    right_y = draw_section_heading(c, "Four provocations", right_x, right_y, col_w)
    provocations = [
        "<b>The 2.5-serving promise may create an expectation gap.</b> Grocery produces 51 of 56 low-value reviews; protein and portion complaints frequently co-occur with price language.",
        "<b>Recent owned-site sentiment deserves a quality review.</b> Grocery first-party averages 2.75 in the recent window (n=12) versus 4.71 earlier (n=7).",
        "<b>Source mix can mask the strongest signal.</b> Thrive is the largest written-review source but is heavily incentive-disclosed, so its 4.36 average should not be treated as like-for-like with other channels.",
        "<b>Convenience remains the portfolio's equity.</b> Preparation and convenience are mentioned in 153 of 331 reviews; improvement should protect the fast-meal proposition.",
    ]
    for i, item in enumerate(provocations, start=1):
        c.setFillColor(MARS_BLUE)
        c.circle(right_x + 7, right_y - 6, 6, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawCentredString(right_x + 7, right_y - 8.2, str(i))
        right_y = draw_paragraph(c, item, BODY_SMALL, right_x + 19, right_y, col_w - 19)
        right_y -= 7

    # Actions band.
    y = min(left_y, right_y) - 10
    y = draw_section_heading(c, "Immediate next moves", margin, y, content_width)
    action_gap = 9
    action_w = (content_width - action_gap * 2) / 3
    actions = [
        ("1", "Prioritize the issue set", "Lead with Honey Garlic, General Tso's, and Chicken Fajitas—the largest combination of negative and value-related signal."),
        ("2", "Audit the value equation", "Review fill weight, protein-to-vegetable architecture, serving claim, and price/value communication together."),
        ("3", "Connect the evidence", "Triangulate review signals with consumer care, lot data, promotions, price, and distribution before causal conclusions."),
    ]
    action_top = y
    for i, (number, heading, copy) in enumerate(actions):
        x = margin + i * (action_w + action_gap)
        c.setFillColor(LIGHT_BLUE)
        c.roundRect(x, action_top - 49, action_w, 49, 4, stroke=0, fill=1)
        c.setFillColor(WATER)
        c.circle(x + 14, action_top - 15, 8, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(x + 14, action_top - 17.5, number)
        draw_paragraph(c, heading, CARD_LABEL, x + 27, action_top - 10, action_w - 35)
        draw_paragraph(c, copy, BODY_SMALL, x + 9, action_top - 27, action_w - 18)
    y = action_top - 59

    # Evidence guardrail and destination.
    c.setStrokeColor(HexColor("#D5D5D0"))
    c.line(margin, y, width - margin, y)
    y -= 10
    draw_paragraph(c, "EVIDENCE GUARDRAIL", CARD_LABEL, margin, y, 95)
    draw_paragraph(
        c,
        "369 raw written rows were reconciled to 331 dated reviews after removing 33 cross-source cross-posts and five same-source repeats. One Thrive comment is retained as unrated. Aggregate channel ratings remain separate from unique written-review counts.",
        BODY_SMALL,
        margin + 98,
        y + 1,
        content_width - 98,
    )

    c.setFillColor(MARS_BLUE)
    c.rect(0, 0, width, 34, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 6.7)
    c.drawString(margin, 20, "EXPLORE THE INTERACTIVE DASHBOARD")
    url = "https://mars-fn-innovation-prototypes.github.io/knf-beef-review-dashboard/stir-fry.html"
    c.setFont("Helvetica", 6.5)
    c.drawRightString(width - margin, 20, url)
    c.linkURL(url, (width - margin - stringWidth(url, "Helvetica", 6.5), 15, width - margin, 27), relative=0)
    c.setFont("Helvetica", 5.8)
    c.drawString(margin, 7, "Point-in-time public review analysis · Data through August 27, 2026")

    c.showPage()
    c.save()
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
