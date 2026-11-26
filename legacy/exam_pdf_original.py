"""
exam_pdf.py - Generate an exam question paper and a blank answer sheet (PDF)
from the Excel template (sheets: Config, Questions).

Usage:
    python exam_pdf.py Exam_Template.xlsx --out output_folder [--logo logo.png]

Outputs (in the output folder):
    <ExamName>_<CourseCode>_Question_Paper.pdf
    <ExamName>_<CourseCode>_Answer_Sheet.pdf
The answer key (column "Answer") is never printed.
"""
import argparse
import io
import math
import os
import re
import sys
from dataclasses import dataclass

from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# Wording printed on the cover page (edit here if the wording must change)
# --------------------------------------------------------------------------
TEXT = {
    "title": "Written Examination Paper",
    "time": "The time allowed is {duration} minutes. There is no additional time allowance for reading the question paper.",
    "marks": "There is a maximum of {total_score} marks available; the pass mark is {pass_mark}%.",
    "sheets": "Your answers must be on the sheets which are supplied (Answer Sheet and Result Form). Additional loose sheets will not be accepted.",
    "comprises": ("It comprises {n} questions which require you to mark a cross (X) inside the box of the letter "
                  "({letters}) on the Answer Sheet to indicate which you judge to be the best answer. You must only "
                  "give one answer for each question and answers may not be altered. Each question is worth {marks} marks."),
    "pages": "Counting the pages you received, there must be {pages} pages in total of examination sheet.",
    "code": "Check that the course code printed on the answer sheet is {course_code}.",
    "return": "You must return the complete examination papers and answering sheet before leaving the classroom.",
    "cheat": ("Any trainee found during an examination to be cheating or in possession of material pertaining to the "
              "examination subject other than the examination papers and associated authorized documentation shall be "
              "<b>disqualified from the training</b> and may not take any training for at least 12 months after the "
              "date on the incident, (Refer.to : PM Sec. 2.8)"),
    "id_header": "Fill in the column below and write your personal identification",
    "answer_title": "Answer Sheet",
    "answer_rule": ("Mark ONE answer for each question with a cross (X) inside the box. "
                    "Use a black or dark blue ballpoint pen. Answers may not be altered."),
}

DEFAULT_ORGANIZATION = "GMF AA Learning Services"
DEFAULT_FORM_LABEL = "GMF Form No"

MARGIN_X = 18 * mm
MARGIN_TOP = 36 * mm
MARGIN_BOTTOM = 30 * mm


class ExamError(Exception):
    """Raised when the Excel file has problems the examiner must fix."""


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
_FONT_FAMILIES = [
    ("Carlito", ["Carlito-Regular.ttf", "Carlito-Bold.ttf", "Carlito-Italic.ttf", "Carlito-BoldItalic.ttf"]),
    ("Calibri", ["calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"]),
    ("Arial", ["arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"]),
    ("Liberation", ["LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf",
                    "LiberationSans-Italic.ttf", "LiberationSans-BoldItalic.ttf"]),
    ("DejaVu", ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf"]),
]
_FONT_DIRS = [
    os.path.join(BASE_DIR, "fonts"),
    r"C:\Windows\Fonts",
    "/usr/share/fonts/truetype/crosextra",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/dejavu",
    "/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
]
_fonts_ready = False


def setup_fonts():
    """Register a Unicode TrueType family as ExamFont (needed for symbols such as curly quotes)."""
    global _fonts_ready
    if _fonts_ready:
        return
    for _, files in _FONT_FAMILIES:
        for d in _FONT_DIRS:
            paths = [os.path.join(d, f) for f in files]
            if all(os.path.isfile(p) for p in paths):
                names = ["ExamFont", "ExamFont-Bold", "ExamFont-Italic", "ExamFont-BoldItalic"]
                for n, p in zip(names, paths):
                    pdfmetrics.registerFont(TTFont(n, p))
                registerFontFamily("ExamFont", normal=names[0], bold=names[1], italic=names[2], boldItalic=names[3])
                _fonts_ready = True
                return
    raise ExamError("No usable TrueType font found. Put Carlito or Liberation Sans .ttf files "
                    "(regular, bold, italic, bold-italic) in the 'fonts' folder next to the program.")


# --------------------------------------------------------------------------
# Reading the Excel template
# --------------------------------------------------------------------------
@dataclass
class Question:
    no: int
    row: int
    ata: str
    ata_title: str
    text: str
    options: list
    answer: str


@dataclass
class Exam:
    cfg: dict
    questions: list
    warnings: list

    @property
    def n(self):
        return len(self.questions)

    @property
    def max_options(self):
        return max(len(q.options) for q in self.questions)

    @property
    def marks_per_question(self):
        return self.cfg["Total Score"] / self.n


def _text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _ata(v):
    s = _text(v)
    if s.isdigit():
        s = s.zfill(2)
    return s


def _num(v, name, errors):
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except ValueError:
        errors.append(f"Config: '{name}' must be a number (found '{v}').")
        return None


def fmt_num(x):
    """2.5 -> '2,5'; 3.3333 -> '3,33'; 100 -> '100' (comma decimal, as on the original form)."""
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def load_exam(path):
    try:
        wb = load_workbook(path, data_only=True)
    except Exception as e:
        raise ExamError(f"Cannot open Excel file: {e}")
    for name in ("Config", "Questions"):
        if name not in wb.sheetnames:
            raise ExamError(f"Sheet '{name}' not found. Use the provided template.")
    errors, warnings = [], []

    # ---- Config
    ws = wb["Config"]
    raw = {}
    ata_table = {}
    for r in range(2, ws.max_row + 1):
        k = _text(ws.cell(r, 1).value)
        if k:
            raw[k] = ws.cell(r, 2).value
        code = _ata(ws.cell(r, 5).value)
        if code:
            ata_table[code] = _text(ws.cell(r, 6).value)
    required = ["Course Title", "Sub Course Title", "Exam Name", "Course Code", "Duration (minutes)",
                "Total Score", "Pass Mark (%)", "Prepared By", "Form No", "Issue", "Year", "Model"]
    cfg = {}
    for k in required:
        if _text(raw.get(k)) == "":
            errors.append(f"Config: '{k}' is empty.")
        cfg[k] = _text(raw.get(k))
    cfg["Duration (minutes)"] = _num(raw.get("Duration (minutes)"), "Duration (minutes)", errors)
    cfg["Total Score"] = _num(raw.get("Total Score"), "Total Score", errors)
    cfg["Pass Mark (%)"] = _num(raw.get("Pass Mark (%)"), "Pass Mark (%)", errors)
    mo = _num(raw.get("Max Options per Question"), "Max Options per Question", errors) or 4
    cfg["Max Options per Question"] = int(mo)
    if cfg["Max Options per Question"] not in (2, 3, 4):
        errors.append("Config: 'Max Options per Question' must be 2, 3 or 4.")
    if cfg["Duration (minutes)"] is not None and cfg["Duration (minutes)"] <= 0:
        errors.append("Config: 'Duration (minutes)' must be greater than 0.")
    if cfg["Total Score"] is not None and cfg["Total Score"] <= 0:
        errors.append("Config: 'Total Score' must be greater than 0.")
    cfg["Organization"] = _text(raw.get("Organization")) or DEFAULT_ORGANIZATION
    cfg["Form Label"] = _text(raw.get("Form Label")) or DEFAULT_FORM_LABEL

    # ---- Questions
    ws = wb["Questions"]
    headers = {_text(ws.cell(1, c).value).lower(): c for c in range(1, ws.max_column + 1)}
    need = ["ata", "question", "option a", "option b", "option c", "option d", "answer"]
    missing = [h for h in need if h not in headers]
    if missing:
        raise ExamError("Questions: column(s) not found in row 1: " + ", ".join(missing))
    letters = "ABCD"
    questions = []
    for r in range(2, ws.max_row + 1):
        qtext = _text(ws.cell(r, headers["question"]).value)
        opts_raw = [_text(ws.cell(r, headers[f"option {l.lower()}"]).value) for l in letters]
        ata = _ata(ws.cell(r, headers["ata"]).value)
        ans = _text(ws.cell(r, headers["answer"]).value).upper()
        if not qtext:
            if any(opts_raw) or ans:
                errors.append(f"Questions row {r}: options/answer filled but the Question text is empty.")
            continue
        # options must be A.. contiguous
        n_opt = 0
        while n_opt < 4 and opts_raw[n_opt]:
            n_opt += 1
        if any(opts_raw[n_opt:]):
            errors.append(f"Questions row {r}: gap in options (fill Option A, B, C, D in order without skipping).")
            continue
        if n_opt < 2:
            errors.append(f"Questions row {r}: at least 2 options are required.")
            continue
        if n_opt > cfg["Max Options per Question"]:
            errors.append(f"Questions row {r}: has {n_opt} options but Config 'Max Options per Question' is "
                          f"{cfg['Max Options per Question']}.")
        if not ata:
            errors.append(f"Questions row {r}: ATA is empty.")
        elif ata not in ata_table:
            errors.append(f"Questions row {r}: ATA '{ata}' is not in the ATA table (Config columns E-F).")
        if ans and ans not in letters[:n_opt]:
            errors.append(f"Questions row {r}: Answer '{ans}' is not one of the available options "
                          f"({', '.join(letters[:n_opt])}).")
        questions.append(Question(0, r, ata, ata_table.get(ata, ""), qtext, opts_raw[:n_opt], ans))

    if not questions and not errors:
        errors.append("Questions: no questions found.")
    if errors:
        raise ExamError("\n".join(errors))

    no_key = [q.row for q in questions if not q.answer]
    if no_key:
        warnings.append(f"{len(no_key)} question(s) have no answer key (rows: "
                        f"{', '.join(map(str, no_key[:10]))}{'...' if len(no_key) > 10 else ''}). "
                        "This does not affect the PDFs.")

    # group by ATA (numeric order), keep the examiner's order inside each ATA
    def ata_key(q):
        return (0, int(q.ata)) if q.ata.isdigit() else (1, q.ata)
    questions.sort(key=ata_key)
    for i, q in enumerate(questions, start=1):
        q.no = i
    return Exam(cfg, questions, warnings)


# --------------------------------------------------------------------------
# Page furniture: header box + footer table on every page
# --------------------------------------------------------------------------
class Ctx:
    def __init__(self, exam, logo):
        self.exam = exam
        self.logo = logo if logo and os.path.isfile(logo) else None


def _fit_text(c, text, font, size, max_w, min_size=8):
    while size > min_size and stringWidth(text, font, size) > max_w:
        size -= 0.5
    return size


def draw_header_footer(c, ctx, page_no, total):
    cfg = ctx.exam.cfg
    W, H = A4
    x0, x1 = MARGIN_X, W - MARGIN_X
    w = x1 - x0
    # ---- header box
    h_top, h_h = H - 12 * mm, 17 * mm
    y0 = h_top - h_h
    c.setLineWidth(0.8)
    c.setStrokeColor(colors.black)
    c.rect(x0, y0, w, h_h)
    if ctx.logo:
        logo_w = 54 * mm
        c.line(x0 + logo_w, y0, x0 + logo_w, h_top)
        from reportlab.lib.utils import ImageReader
        img = ImageReader(ctx.logo)
        iw, ih = img.getSize()
        box_w, box_h = logo_w - 8 * mm, h_h - 5 * mm
        s = min(box_w / iw, box_h / ih)
        c.drawImage(img, x0 + (logo_w - iw * s) / 2, y0 + (h_h - ih * s) / 2, iw * s, ih * s, mask="auto")
        tx0 = x0 + logo_w
    else:
        tx0 = x0
    title = cfg["Course Title"]
    tw = x1 - tx0 - 8 * mm
    size = _fit_text(c, title, "ExamFont-Bold", 13, tw)
    c.setFont("ExamFont-Bold", size)
    cx = (tx0 + x1) / 2
    if stringWidth(title, "ExamFont-Bold", size) <= tw:
        c.drawCentredString(cx, y0 + h_h / 2 - size * 0.35, title)
    else:  # still too long at the minimum size: split in two lines
        words, line1 = title.split(), ""
        for wd in words:
            if stringWidth((line1 + " " + wd).strip(), "ExamFont-Bold", size) <= tw:
                line1 = (line1 + " " + wd).strip()
            else:
                break
        line2 = title[len(line1):].strip()
        c.drawCentredString(cx, y0 + h_h / 2 + 1.5, line1)
        c.drawCentredString(cx, y0 + h_h / 2 - size - 0.5, line2)

    # ---- footer table
    fy = 12 * mm
    row1_h, row2_h = 7 * mm, 6 * mm
    fr_top = fy + row2_h + row1_h
    ratios = [0.27, 0.23, 0.24, 0.26]
    xs = [x0]
    for r_ in ratios:
        xs.append(xs[-1] + w * r_)
    c.setLineWidth(0.6)
    c.rect(x0, fr_top - row1_h, w, row1_h)
    for xv in xs[1:-1]:
        c.line(xv, fr_top - row1_h, xv, fr_top)
    c.setFont("ExamFont", 9)
    ty = fr_top - row1_h + 2.3 * mm
    c.drawString(xs[0] + 3 * mm, ty, cfg["Organization"])
    c.drawString(xs[1] + 3 * mm, ty, f"Issue:{cfg['Issue']}")
    c.drawCentredString((xs[2] + xs[3]) / 2, ty, cfg["Year"])
    c.drawRightString(xs[4] - 3 * mm, ty, f"Page {page_no} of {total}")
    ty2 = fy + 1.8 * mm
    c.drawString(x0 + 1 * mm, ty2, f"{cfg['Form Label']}: {cfg['Form No']}")
    c.drawCentredString(x0 + w / 2, ty2, f"MODEL: {cfg['Model']}")
    c.drawRightString(x1, ty2, f"Prepare by: {cfg['Prepared By']}")


def numbered_canvas(ctx):
    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st)
                draw_header_footer(self, ctx, self._pageNumber, total)
                super().showPage()
            super().save()
    return NumberedCanvas


def new_doc(target, ctx, title):
    cfg = ctx.exam.cfg
    doc = BaseDocTemplate(target, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X,
                          topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOTTOM,
                          title=title, author=cfg["Prepared By"], subject=cfg["Course Code"])
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
    return doc


def styles():
    base = ParagraphStyle("base", fontName="ExamFont", fontSize=11, leading=14)
    return {
        "base": base,
        "cover_title": ParagraphStyle("ct", parent=base, fontName="ExamFont-Bold", fontSize=19, leading=25,
                                      alignment=TA_CENTER),
        "center": ParagraphStyle("c", parent=base, alignment=TA_CENTER),
        "para": ParagraphStyle("p", parent=base, alignment=TA_JUSTIFY, spaceAfter=11),
        "tight": ParagraphStyle("t", parent=base, alignment=TA_JUSTIFY, spaceAfter=2),
        "q": ParagraphStyle("q", parent=base, leftIndent=20, bulletIndent=0, spaceAfter=5),
        "opt": ParagraphStyle("o", parent=base, leftIndent=40, bulletIndent=20, leading=14, spaceAfter=1.5),
        "note": ParagraphStyle("n", parent=base, fontName="ExamFont-Italic", fontSize=10, alignment=TA_CENTER),
    }


def esc(s):
    from xml.sax.saxutils import escape
    return escape(s).replace("\n", "<br/>")


def identity_table(width):
    data = [[TEXT["id_header"], "", ""], ["NAME", ":", ""], ["ID. NUMBER", ":", ""], ["SIGNATURE", ":", ""]]
    t = Table(data, colWidths=[52 * mm, 8 * mm, width - 60 * mm],
              rowHeights=[8 * mm, 10 * mm, 10 * mm, 17 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "ExamFont"), ("FONTSIZE", (0, 0), (-1, -1), 10.5),
        ("SPAN", (0, 0), (-1, 0)), ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9D9D9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 1), (0, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("LINEBELOW", (0, 0), (-1, -2), 0.8, colors.black),
    ]))
    return t


# --------------------------------------------------------------------------
# Question paper
# --------------------------------------------------------------------------
def _question_story(exam, total_pages):
    cfg, st = exam.cfg, styles()
    letters = ", ".join("ABCD"[:exam.max_options])
    fmt = dict(duration=fmt_num(cfg["Duration (minutes)"]), total_score=fmt_num(cfg["Total Score"]),
               pass_mark=fmt_num(cfg["Pass Mark (%)"]), n=exam.n, letters=letters,
               marks=fmt_num(exam.marks_per_question), pages=total_pages, course_code=cfg["Course Code"])
    width = A4[0] - 2 * MARGIN_X
    s = [Spacer(1, 10 * mm),
         Paragraph(esc(TEXT["title"]), st["cover_title"]),
         Paragraph(esc(cfg["Sub Course Title"]), st["cover_title"]),
         Paragraph(esc(cfg["Exam Name"]), st["cover_title"]),
         Spacer(1, 12 * mm),
         Paragraph(f"Course Code: {esc(cfg['Course Code'])}", st["center"]),
         Spacer(1, 10 * mm),
         Paragraph(esc(TEXT["time"].format(**fmt)), st["para"]),
         Paragraph(esc(TEXT["marks"].format(**fmt)), st["para"]),
         Paragraph(esc(TEXT["sheets"].format(**fmt)), st["para"]),
         Paragraph(esc(TEXT["comprises"].format(**fmt)), st["para"]),
         Paragraph(esc(TEXT["pages"].format(**fmt)), st["tight"]),
         Paragraph(esc(TEXT["code"].format(**fmt)), st["tight"]),
         Paragraph(esc(TEXT["return"].format(**fmt)), st["para"]),
         Spacer(1, 2 * mm),
         Paragraph(TEXT["cheat"], st["para"]),
         Spacer(1, 12 * mm),
         identity_table(width),
         PageBreak()]

    prev_ata = None
    for q in exam.questions:
        block = [Paragraph(esc(q.text), st["q"], bulletText=f"{q.no}.")]
        for letter, opt in zip("ABCD", q.options):
            block.append(Paragraph(esc(opt), st["opt"], bulletText=f"{letter}."))
        block.append(Spacer(1, 9))
        if q.ata != prev_ata:
            h = Table([[Paragraph(f"<b>ATA {esc(q.ata)}</b> &#8211; {esc(q.ata_title)}", st["base"])]],
                      colWidths=[width])
            h.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EDEDED")),
                                   ("LINEBELOW", (0, 0), (-1, -1), 0.8, colors.black),
                                   ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
            block = [h, Spacer(1, 6)] + block
            prev_ata = q.ata
        s.append(KeepTogether(block))
    return s


def build_question_paper(exam, out_path, logo=None):
    setup_fonts()
    ctx = Ctx(exam, logo)
    title = f"{exam.cfg['Sub Course Title']} - {exam.cfg['Exam Name']}"
    # pass 1: count the pages so the cover can say "there must be N pages"
    buf = io.BytesIO()
    doc = new_doc(buf, ctx, title)
    doc.build(_question_story(exam, 0), canvasmaker=numbered_canvas(ctx))
    total = doc.page
    # pass 2: real file
    doc = new_doc(out_path, ctx, title)
    doc.build(_question_story(exam, total), canvasmaker=numbered_canvas(ctx))
    if doc.page != total:
        raise ExamError("Internal error: page count changed between passes.")
    return total


# --------------------------------------------------------------------------
# Answer sheet (square boxes to be marked with a cross)
# --------------------------------------------------------------------------
class AnswerGrid(Flowable):
    PITCH = 8.5 * mm
    BOX = 6 * mm
    GAP = 3 * mm
    NUM_W = 11 * mm
    HEAD_H = 9 * mm

    def __init__(self, items, max_opt):
        super().__init__()
        self.items, self.max_opt = items, max_opt
        n = len(items)
        self.cols = 3 if n > 24 else (2 if n > 12 else 1)
        self.rows = math.ceil(n / self.cols)

    def wrap(self, aw, ah):
        self.w = aw
        self.h = self.HEAD_H + self.rows * self.PITCH
        return aw, self.h

    def draw(self):
        c = self.canv
        colw = self.w / self.cols
        block_w = self.NUM_W + self.max_opt * self.BOX + (self.max_opt - 1) * self.GAP
        for ci in range(self.cols):
            xs = ci * colw + (colw - block_w) / 2
            c.setFillColor(colors.black)
            c.setFont("ExamFont-Bold", 11)
            for k in range(self.max_opt):
                bx = xs + self.NUM_W + k * (self.BOX + self.GAP)
                c.drawCentredString(bx + self.BOX / 2, self.h - self.HEAD_H + 3 * mm, "ABCD"[k])
            for r in range(self.rows):
                idx = ci * self.rows + r
                if idx >= len(self.items):
                    break
                no, n_opt = self.items[idx]
                yc = self.h - self.HEAD_H - (r + 0.5) * self.PITCH
                c.setFont("ExamFont", 11)
                c.drawRightString(xs + self.NUM_W - 3 * mm, yc - 1.4 * mm, str(no))
                c.setLineWidth(0.9)
                c.setStrokeColor(colors.black)
                for k in range(n_opt):
                    bx = xs + self.NUM_W + k * (self.BOX + self.GAP)
                    c.rect(bx, yc - self.BOX / 2, self.BOX, self.BOX, stroke=1, fill=0)
                if (r + 1) % 5 == 0 and r < self.rows - 1:
                    c.setLineWidth(0.3)
                    c.setStrokeColor(colors.HexColor("#BBBBBB"))
                    y = yc - self.PITCH / 2
                    c.line(xs, y, xs + block_w, y)


def build_answer_sheet(exam, out_path, logo=None):
    setup_fonts()
    cfg, st = exam.cfg, styles()
    ctx = Ctx(exam, logo)
    width = A4[0] - 2 * MARGIN_X
    story = [Spacer(1, 4 * mm),
             Paragraph(esc(TEXT["answer_title"]).upper(), st["cover_title"]),
             Paragraph(f"<b>{esc(cfg['Sub Course Title'])}</b>", st["center"]),
             Paragraph(f"{esc(cfg['Exam Name'])} &nbsp;|&nbsp; Course Code: {esc(cfg['Course Code'])} "
                       f"&nbsp;|&nbsp; MODEL: {esc(cfg['Model'])}", st["center"]),
             Spacer(1, 6 * mm),
             identity_table(width),
             Spacer(1, 5 * mm),
             Paragraph(esc(TEXT["answer_rule"]), st["note"]),
             Spacer(1, 5 * mm)]
    items = [(q.no, len(q.options)) for q in exam.questions]
    # page 1 shares space with the title/identity block, later pages are full-height grids
    first_cap, next_cap = 42, 60
    parts, pos = [items[:first_cap]], first_cap
    while pos < len(items):
        parts.append(items[pos:pos + next_cap])
        pos += next_cap
    for i, part in enumerate(parts):
        if i:
            story.append(PageBreak())
        story.append(AnswerGrid(part, max(n for _, n in part)))
    doc = new_doc(out_path, ctx, f"{TEXT['answer_title']} - {cfg['Exam Name']}")
    doc.build(story, canvasmaker=numbered_canvas(ctx))
    return doc.page


# --------------------------------------------------------------------------
def safe_name(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "exam"


def generate(xlsx_path, out_dir, logo=None):
    """Create both PDFs. Returns (list_of_files, list_of_warnings). Raises ExamError on bad input."""
    if logo is None:
        default_logo = os.path.join(BASE_DIR, "logo.png")
        logo = default_logo if os.path.isfile(default_logo) else None
    exam = load_exam(xlsx_path)
    os.makedirs(out_dir, exist_ok=True)
    stem = f"{safe_name(exam.cfg['Exam Name'])}_{safe_name(exam.cfg['Course Code'])}"
    qp = os.path.join(out_dir, f"{stem}_Question_Paper.pdf")
    ap = os.path.join(out_dir, f"{stem}_Answer_Sheet.pdf")
    build_question_paper(exam, qp, logo)
    build_answer_sheet(exam, ap, logo)
    return [qp, ap], exam.warnings


def main():
    ap = argparse.ArgumentParser(description="Generate exam question paper + answer sheet PDFs from Excel.")
    ap.add_argument("xlsx")
    ap.add_argument("--out", default="output")
    ap.add_argument("--logo", default=None)
    a = ap.parse_args()
    try:
        files, warns = generate(a.xlsx, a.out, a.logo)
    except ExamError as e:
        print("Cannot generate PDF:\n" + str(e))
        sys.exit(1)
    for w in warns:
        print("Warning:", w)
    for f in files:
        print("Created:", f)


if __name__ == "__main__":
    main()
