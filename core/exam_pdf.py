"""
Pembuat PDF soal ujian (Set A / B / R).

Tampilan mengikuti skrip asli (legacy/exam_pdf_original.py): halaman sampul + petunjuk +
tabel identitas, header, judul ATA, footer resmi, penghitungan halaman dua-tahap, dan font
TrueType (Carlito/Calibri). Perbedaan dengan skrip asli hanya:
  - sumber data = objek Exam (core.models), bukan membaca Excel langsung;
  - footer "MODEL" menampilkan huruf set (A/B/R);
  - lembar jawaban TIDAK dibuat (memakai form resmi yang dipindai).

Tidak ada print dan tidak ada tampilan GUI. Mendukung progress_callback.
"""
import io
from pathlib import Path
from typing import Callable, Optional
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

from .models import Exam

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
DEFAULT_LOGO = ASSETS_DIR / "logo.png"   # opsional: kalau ada, otomatis dipakai di header

# --------------------------------------------------------------------------
# Kalimat di halaman sampul (ubah di sini kalau redaksi harus berubah)
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
}

DEFAULT_ORGANIZATION = "GMF AA Learning Services"
DEFAULT_FORM_LABEL = "GMF Form No"

MARGIN_X = 18 * mm
MARGIN_TOP = 36 * mm
MARGIN_BOTTOM = 30 * mm


class ExamPdfError(Exception):
    """Masalah saat membuat PDF soal (misalnya font tidak ditemukan)."""


# --------------------------------------------------------------------------
# Font
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
    str(ASSETS_DIR / "fonts"),
    r"C:\Windows\Fonts",
    "/usr/share/fonts/truetype/crosextra",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/dejavu",
    "/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
]
_fonts_ready = False


def setup_fonts():
    """Daftarkan keluarga font TrueType Unicode sebagai ExamFont (perlu untuk tanda kutip melengkung, dll.)."""
    global _fonts_ready
    if _fonts_ready:
        return
    for _, files in _FONT_FAMILIES:
        for d in _FONT_DIRS:
            paths = [Path(d) / f for f in files]
            if all(p.is_file() for p in paths):
                names = ["ExamFont", "ExamFont-Bold", "ExamFont-Italic", "ExamFont-BoldItalic"]
                for n, p in zip(names, paths):
                    pdfmetrics.registerFont(TTFont(n, str(p)))
                registerFontFamily("ExamFont", normal=names[0], bold=names[1],
                                   italic=names[2], boldItalic=names[3])
                _fonts_ready = True
                return
    raise ExamPdfError("Font TrueType tidak ditemukan. Taruh file Carlito (Regular, Bold, Italic, "
                       "BoldItalic .ttf) di folder assets/fonts.")


# --------------------------------------------------------------------------
# Pembantu
# --------------------------------------------------------------------------
def fmt_num(x) -> str:
    """2.5 -> '2,5'; 3.3333 -> '3,33'; 100 -> '100' (koma desimal, seperti form asli)."""
    s = f"{float(x):.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def esc(s) -> str:
    """Escape karakter < > & supaya teks soal tidak dianggap penanda; baris baru -> <br/>."""
    return _xml_escape(str(s)).replace("\n", "<br/>")


def _cfg(exam: Exam) -> dict:
    c = exam.config
    return {
        "Course Title": c.title,
        "Sub Course Title": c.sub_course_title or c.course_name,
        "Exam Name": c.exam_name or c.course_name,
        "Course Code": c.course_code,
        "Duration (minutes)": c.duration_minutes,
        "Total Score": c.total_score,
        "Pass Mark (%)": c.pass_mark,
        "Prepared By": c.prepared_by,
        "Form No": c.form_no,
        "Issue": c.issue,
        "Year": c.year,
        "Model": exam.set_name,                       # huruf set: A / B / R
        "Organization": c.organization or DEFAULT_ORGANIZATION,
        "Form Label": c.form_label or DEFAULT_FORM_LABEL,
    }


class _Ctx:
    def __init__(self, exam: Exam, logo):
        self.exam = exam
        self.cfg = _cfg(exam)
        logo = Path(logo) if logo else DEFAULT_LOGO
        self.logo = str(logo) if logo.is_file() else None


def _fit_text(text, font, size, max_w, min_size=8):
    while size > min_size and stringWidth(text, font, size) > max_w:
        size -= 0.5
    return size


# --------------------------------------------------------------------------
# Header dan footer (digambar di setiap halaman)
# --------------------------------------------------------------------------
def _draw_header_footer(c, ctx: _Ctx, page_no: int, total: int):
    cfg = ctx.cfg
    W, H = A4
    x0, x1 = MARGIN_X, W - MARGIN_X
    w = x1 - x0
    # ---- kotak header
    h_top, h_h = H - 12 * mm, 17 * mm
    y0 = h_top - h_h
    c.setLineWidth(0.8)
    c.setStrokeColor(colors.black)
    c.rect(x0, y0, w, h_h)
    if ctx.logo:
        logo_w = 54 * mm
        c.line(x0 + logo_w, y0, x0 + logo_w, h_top)
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
    size = _fit_text(title, "ExamFont-Bold", 13, tw)
    c.setFont("ExamFont-Bold", size)
    cx = (tx0 + x1) / 2
    if stringWidth(title, "ExamFont-Bold", size) <= tw:
        c.drawCentredString(cx, y0 + h_h / 2 - size * 0.35, title)
    else:  # masih terlalu panjang pada ukuran minimum: pecah jadi dua baris
        words, line1 = title.split(), ""
        for wd in words:
            if stringWidth((line1 + " " + wd).strip(), "ExamFont-Bold", size) <= tw:
                line1 = (line1 + " " + wd).strip()
            else:
                break
        line2 = title[len(line1):].strip()
        c.drawCentredString(cx, y0 + h_h / 2 + 1.5, line1)
        c.drawCentredString(cx, y0 + h_h / 2 - size - 0.5, line2)

    # ---- tabel footer
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
    c.drawString(xs[0] + 3 * mm, ty, str(cfg["Organization"]))
    c.drawString(xs[1] + 3 * mm, ty, f"Issue:{cfg['Issue']}")
    c.drawCentredString((xs[2] + xs[3]) / 2, ty, str(cfg["Year"]))
    c.drawRightString(xs[4] - 3 * mm, ty, f"Page {page_no} of {total}")
    ty2 = fy + 1.8 * mm
    c.drawString(x0 + 1 * mm, ty2, f"{cfg['Form Label']}: {cfg['Form No']}")
    c.drawCentredString(x0 + w / 2, ty2, f"MODEL: {cfg['Model']}")
    c.drawRightString(x1, ty2, f"Prepare by: {cfg['Prepared By']}")


def _numbered_canvas(ctx: _Ctx):
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
                _draw_header_footer(self, ctx, self._pageNumber, total)
                super().showPage()
            super().save()
    return NumberedCanvas


def _new_doc(target, ctx: _Ctx, title: str):
    cfg = ctx.cfg
    doc = BaseDocTemplate(target, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X,
                          topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOTTOM,
                          title=title, author=str(cfg["Prepared By"]), subject=str(cfg["Course Code"]))
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
    return doc


def _styles():
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
    }


def _identity_table(width):
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
# Isi dokumen
# --------------------------------------------------------------------------
def _story(exam: Exam, total_pages: int):
    cfg, st = _cfg(exam), _styles()
    questions = exam.questions
    n = len(questions)
    max_opts = max((len(q.options) for q in questions), default=exam.config.num_options)
    marks = (float(cfg["Total Score"]) / n) if n else 0.0
    fmt = dict(duration=fmt_num(cfg["Duration (minutes)"]), total_score=fmt_num(cfg["Total Score"]),
               pass_mark=fmt_num(cfg["Pass Mark (%)"]), n=n, letters=", ".join("ABCD"[:max_opts]),
               marks=fmt_num(marks), pages=total_pages, course_code=cfg["Course Code"])
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
         _identity_table(width),
         PageBreak()]

    prev_ata = None
    for idx, q in enumerate(questions, start=1):
        number = q.order_number if q.order_number else idx
        block = [Paragraph(esc(q.question_text), st["q"], bulletText=f"{number}.")]
        for letter, opt in zip("ABCD", q.options):
            block.append(Paragraph(esc(opt), st["opt"], bulletText=f"{letter}."))
        block.append(Spacer(1, 9))
        if q.ata != prev_ata:
            title = f"<b>ATA {esc(q.ata)}</b>"
            if q.ata_title:
                title += f" &#8211; {esc(q.ata_title)}"
            h = Table([[Paragraph(title, st["base"])]], colWidths=[width])
            h.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EDEDED")),
                                   ("LINEBELOW", (0, 0), (-1, -1), 0.8, colors.black),
                                   ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
            block = [h, Spacer(1, 6)] + block
            prev_ata = q.ata
        s.append(KeepTogether(block))
    return s


def generate_exam_pdf(
    exam: Exam,
    output_path,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    logo=None,
) -> Path:
    """
    Membuat PDF lembar soal ujian.

    Args:
        exam: objek Exam (konfigurasi + daftar soal + set_name).
        output_path: lokasi file PDF keluaran.
        progress_callback: fungsi (persen 0.0-1.0, pesan) untuk menampilkan progres.
        logo: path gambar logo (opsional). Kalau kosong dan assets/logo.png ada, itu yang dipakai.

    Returns:
        Path file PDF yang dibuat.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    def report(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)

    report(0.1, "Menyiapkan font dan tata letak...")
    setup_fonts()
    ctx = _Ctx(exam, logo)
    cfg = ctx.cfg
    title = f"{cfg['Sub Course Title']} - {cfg['Exam Name']} (Set {exam.set_name})"

    # Tahap 1: hitung jumlah halaman supaya sampul bisa menulis "harus ada N halaman"
    report(0.3, "Menghitung jumlah halaman...")
    doc = _new_doc(io.BytesIO(), ctx, title)
    doc.build(_story(exam, 0), canvasmaker=_numbered_canvas(ctx))
    total = doc.page

    # Tahap 2: file sebenarnya
    report(0.6, "Membuat file PDF...")
    doc = _new_doc(str(out_file), ctx, title)
    doc.build(_story(exam, total), canvasmaker=_numbered_canvas(ctx))
    if doc.page != total:
        raise ExamPdfError("Kesalahan internal: jumlah halaman berubah antar tahap.")

    report(1.0, "Selesai.")
    return out_file
