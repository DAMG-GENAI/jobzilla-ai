"""
PDF Utilities

Convert resume Markdown into a professional PDF matching the reference format:
- Font: Times New Roman, 11pt body
- Right-aligned dates
- Tabbed skills section
- Underlined section headers
- Compact 1-page layout
"""

import re
from io import BytesIO

from fpdf import FPDF


class ResumePDF(FPDF):
    LM = 15  # left margin
    RM = 15  # right margin
    TM = 12  # top margin
    PW = 210  # A4 width mm

    def __init__(self):
        super().__init__()
        self.set_margins(self.LM, self.TM, self.RM)
        self.set_auto_page_break(True, margin=12)
        self._name_rendered = False

    def _s(self, text: str) -> str:
        """Safely encode text for PDF output."""
        # Replace unicode bullets and dashes
        text = text.replace("\u2022", "-")
        text = text.replace("\u2013", "-")
        text = text.replace("\u2014", "-")
        text = text.replace("\u2018", "'")
        text = text.replace("\u2019", "'")
        text = text.replace("\u201c", '"')
        text = text.replace("\u201d", '"')
        text = text.replace("\u2026", "...")
        text = text.replace("\u00a0", " ")
        return text.encode("latin-1", errors="replace").decode("latin-1")

    @property
    def ew(self) -> float:
        """Effective width."""
        return self.PW - self.LM - self.RM

    # ── Renderers ──────────────────────────────────────────────────────

    def name_block(self, name: str):
        """Render the candidate name centered and bold at the top."""
        name = name.strip()
        if not name:
            return
        self.set_font("Times", "B", 16)
        self.set_text_color(0, 0, 0)
        self.cell(self.ew, 8, self._s(name), ln=True, align="C")
        self._name_rendered = True

    def contact_block(self, line: str):
        self.set_font("Times", "", 10)
        self.set_text_color(40, 40, 40)
        self.cell(self.ew, 5, self._s(line), ln=True, align="C")

    def section_header(self, title: str):
        self.ln(3)
        self.set_font("Times", "B", 12)
        self.set_text_color(0, 0, 0)
        self.cell(self.ew, 6, self._s(title), ln=True)
        y = self.get_y()
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.4)
        self.line(self.LM, y, self.PW - self.RM, y)
        self.ln(1.5)

    def line_with_right_date(
        self, left: str, right: str, bold: bool = True, italic: bool = False
    ):
        """Render left text with right-aligned date on the same line."""
        style = ""
        if bold and italic:
            style = "BI"
        elif bold:
            style = "B"
        elif italic:
            style = "I"

        self.set_font("Times", style, 11)
        self.set_text_color(0, 0, 0)

        # Measure date width
        date_w = self.get_string_width(self._s(right)) + 2
        left_w = self.ew - date_w

        self.cell(left_w, 5, self._s(left), ln=False)
        self.set_font("Times", "", 11)
        self.cell(date_w, 5, self._s(right), ln=True, align="R")

    def sub_line(
        self, text: str, bold: bool = False, italic: bool = False, indent: float = 0
    ):
        style = ""
        if bold and italic:
            style = "BI"
        elif bold:
            style = "B"
        elif italic:
            style = "I"
        self.set_font("Times", style, 11)
        self.set_text_color(0, 0, 0)
        self.set_x(self.LM + indent)
        self.multi_cell(self.ew - indent, 5, self._s(text))

    def bullet_point(self, text: str):
        self.set_font("Times", "", 11)
        self.set_text_color(0, 0, 0)
        bullet_indent = 4
        # Use a simple hyphen as bullet to avoid encoding issues
        bullet_char = "-  "
        self.set_x(self.LM + bullet_indent)
        self.multi_cell(self.ew - bullet_indent, 5, self._s(bullet_char + text))

    def skill_row(self, category: str, values: str):
        """Render a skills row with bold category label and values."""
        cat_w = 38  # fixed width for category column
        self.set_font("Times", "B", 11)
        self.set_text_color(0, 0, 0)
        self.set_x(self.LM)
        self.cell(cat_w, 5, self._s(category + ":"), ln=False)
        self.set_font("Times", "", 11)
        self.multi_cell(self.ew - cat_w, 5, self._s(values))


# ── Markdown stripping helpers ─────────────────────────────────────────


def _strip_all(text: str) -> str:
    """Remove all Markdown formatting."""
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text)  # bold+italic
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # bold
    text = re.sub(
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text
    )  # italic (single *)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    return text.strip()


def _has_bold(text: str) -> bool:
    return "**" in text


def _has_italic(text: str) -> bool:
    # Has single * but not double **
    single_stars = re.findall(r"(?<!\*)\*(?!\*)", text)
    return len(single_stars) >= 2


# ── Main converter ─────────────────────────────────────────────────────


def markdown_to_pdf(md_text: str) -> bytes:
    """Convert resume markdown to PDF bytes."""
    pdf = ResumePDF()
    pdf.add_page()

    lines = md_text.splitlines()
    i = 0
    in_header_block = True  # Track if we're still in the name/contact area

    while i < len(lines):
        raw = lines[i].rstrip()
        i += 1

        if not raw.strip():
            continue

        stripped = raw.strip()

        # ── Horizontal rules ──
        if re.match(r"^[-*_]{3,}$", stripped):
            continue

        # ── H1 — Name ──
        if raw.startswith("# "):
            name = _strip_all(raw[2:])
            pdf.name_block(name)
            continue

        # ── H2 — Section Header ──
        if raw.startswith("## "):
            in_header_block = False
            title = _strip_all(raw[3:])
            # Skip "Assumptions Made" section
            if "assumption" in title.lower():
                while i < len(lines) and not lines[i].startswith("## "):
                    i += 1
                continue
            pdf.section_header(title)
            continue

        # ── H3 — Sub heading ──
        if raw.startswith("### "):
            pdf.sub_line(_strip_all(raw[4:]), bold=True)
            continue

        # ── Contact lines (before first section header) ──
        if in_header_block and not raw.startswith("#"):
            # Lines between name and first ## are contact info
            if "|||RIGHT|||" not in raw and "|||TAB|||" not in raw:
                clean = _strip_all(stripped)
                if clean:
                    pdf.contact_block(clean)
                continue

        # ── Lines with |||RIGHT||| marker — left text with right-aligned date ──
        if "|||RIGHT|||" in raw:
            parts = raw.split("|||RIGHT|||")
            left = _strip_all(parts[0])
            right = _strip_all(parts[1]) if len(parts) > 1 else ""
            is_bold = _has_bold(parts[0])
            is_italic = _has_italic(parts[0]) and not _has_bold(parts[0])
            pdf.line_with_right_date(left, right, bold=is_bold, italic=is_italic)
            continue

        # ── Lines with |||TAB||| marker — skills table row ──
        if "|||TAB|||" in raw:
            parts = raw.split("|||TAB|||")
            cat = _strip_all(parts[0])
            vals = _strip_all(parts[1]) if len(parts) > 1 else ""
            pdf.skill_row(cat, vals)
            continue

        # ── Bullet points ──
        if re.match(r"^[-*]\s+", stripped):
            text = _strip_all(re.sub(r"^[-*]\s+", "", stripped))
            pdf.bullet_point(text)
            continue

        # ── Table separator rows ──
        if re.match(r"^\|[-:| ]+\|$", stripped):
            continue

        # ── Regular text (degree lines, coursework, etc.) ──
        clean = _strip_all(stripped)
        if clean:
            is_bold = _has_bold(stripped)
            is_italic = _has_italic(stripped)
            pdf.sub_line(clean, bold=is_bold, italic=is_italic)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
