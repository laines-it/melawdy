import re
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT = "LiberationSerif"
FONT_BOLD = "LiberationSerif-Bold"

_fonts_ready = False
# Строка-заголовок раздела: «1. ПРЕДМЕТ СОГЛАШЕНИЯ», «11. РЕКВИЗИТЫ И ПОДПИСИ СТОРОН»
_HEADING = re.compile(r"^\d+\.\s+[А-ЯЁA-Z0-9 ,.\-–—«»()]+$")


def _register_fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    pdfmetrics.registerFont(TTFont(FONT, str(FONT_DIR / "LiberationSerif-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "LiberationSerif-Bold.ttf")))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)
    _fonts_ready = True


def _to_markup(block: str) -> str:
    lines = []
    for line in block.split("\n"):
        line = escape(line)
        line = re.sub(r" {2,}", lambda m: "&nbsp;" * len(m.group(0)), line)
        line = re.sub(r"^ ", "&nbsp;", line)
        lines.append(line)
    return "<br/>".join(lines)


def text_to_pdf(text: str) -> bytes:
    _register_fonts()
    body = ParagraphStyle("body", fontName=FONT, fontSize=11.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=7)
    heading = ParagraphStyle("heading", parent=body, fontName=FONT_BOLD, alignment=0, spaceBefore=8, spaceAfter=7)
    title = ParagraphStyle("title", parent=body, fontName=FONT_BOLD, fontSize=14, leading=18,
                           alignment=TA_CENTER, spaceAfter=12)

    story = []
    blocks = [b.strip("\n") for b in (text or "").split("\n\n")]
    blocks = [b for b in blocks if b.strip()]
    for index, block in enumerate(blocks):
        first_line = block.split("\n", 1)[0].strip()
        if index == 0 and "\n" not in block and first_line.isupper():
            style = title
        elif "\n" not in block and _HEADING.match(first_line) and first_line.upper() == first_line:
            style = heading
        else:
            style = body
        story.append(Paragraph(_to_markup(block), style))
        if style is title:
            story.append(Spacer(1, 4))

    buf = BytesIO()
    SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=30 * mm, rightMargin=15 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
        title="Документ", author="Законпозитор",
    ).build(story)
    return buf.getvalue()