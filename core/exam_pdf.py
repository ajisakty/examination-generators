"""
Modul pembuat PDF soal ujian resmi (Set A / Set B).
Menggunakan ReportLab (Flowables, DocTemplate, PageTemplate) tanpa GUI atau print.
Mendukung progress_callback.
"""

from pathlib import Path
from typing import Callable, List, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    PageBreak,
)
from reportlab.pdfgen import canvas

from .models import Exam, Question


class NumberedCanvas(canvas.Canvas):
    """
    Canvas kustom dua-tahap (two-pass) untuk menghitung total halaman otomatis
    dan menggambar footer resmi (Form No, Issue, Year, Model, dan Halaman X of Y).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.exam_model = "A"
        self.prepared_by = ""
        self.form_no = "U-065 R0"
        self.issue = 1
        self.year = 2026

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setStrokeColor(colors.black)
        self.setLineWidth(0.5)

        width, height = A4
        margin_x = 1.5 * cm
        footer_y = 1.0 * cm

        # Garis horizontal footer
        self.line(margin_x, footer_y + 12, width - margin_x, footer_y + 12)

        # Informasi kiri footer
        left_text = f"Form: {self.form_no} | Issue: {self.issue} | Year: {self.year}"
        if self.prepared_by:
            left_text = f"{left_text} | Prep: {self.prepared_by}"
        self.drawString(margin_x, footer_y, left_text)

        # Informasi kanan: MODEL A/B dan Halaman X of Y
        center_text = f"MODEL: {self.exam_model}"
        self.drawCentredString(width / 2.0, footer_y, center_text)

        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(width - margin_x, footer_y, page_str)

        self.restoreState()


def generate_exam_pdf(
    exam: Exam,
    output_path: str | Path,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Path:
    """
    Membuat file PDF lembar soal ujian.
    
    Args:
        exam: Objek Exam yang berisi konfigurasi dan daftar soal.
        output_path: Lokasi file output PDF.
        progress_callback: Callback progres (persen: 0.0 - 1.0, pesan: str).
    
    Returns:
        Path dari file PDF yang berhasil dibuat.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(0.1, "Menyiapkan tata letak dokumen PDF...")

    doc = SimpleDocTemplate(
        str(out_file),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.8 * cm,
    )

    styles = getSampleStyleSheet()

    # Kustomisasi gaya teks
    title_style = ParagraphStyle(
        "ExamTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        alignment=1,  # Center
    )
    subtitle_style = ParagraphStyle(
        "ExamSubTitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=1,  # Center
    )
    meta_style = ParagraphStyle(
        "ExamMeta",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
    )
    ata_header_style = ParagraphStyle(
        "ATAHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.whitesmoke,
    )
    q_num_style = ParagraphStyle(
        "QuestionNumber",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
    )
    q_text_style = ParagraphStyle(
        "QuestionText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
    )
    opt_label_style = ParagraphStyle(
        "OptionLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
    )
    opt_text_style = ParagraphStyle(
        "OptionText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
    )

    story = []

    # 1. Header Kotak Dokumen
    # Kolom kiri: Judul Pelatihan & Ujian, Kolom kanan: Info Kode & Waktu
    col_w1 = 12.0 * cm
    col_w2 = 6.0 * cm

    title_para = Paragraph(f"<b>{exam.config.title.upper()}</b>", title_style)
    sub_title_para = Paragraph(exam.config.course_name.upper(), subtitle_style)

    right_info = (
        f"<b>Course Code:</b> {exam.config.course_code}<br/>"
        f"<b>SET:</b> {exam.set_name.upper()}<br/>"
        f"<b>Duration:</b> {exam.config.duration_minutes} Minutes<br/>"
        f"<b>Total Questions:</b> {exam.config.total_questions}<br/>"
        f"<b>Pass Mark:</b> {exam.config.pass_mark}%"
    )
    meta_para = Paragraph(right_info, meta_style)

    header_table_data = [
        [[title_para, Spacer(1, 0.2 * cm), sub_title_para], meta_para]
    ]

    header_table = Table(header_table_data, colWidths=[col_w1, col_w2])
    header_table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 0.4 * cm))

    if progress_callback:
        progress_callback(0.3, "Menyusun butir-butir soal...")

    # 2. Butir-butir Soal Dikelompokkan per ATA
    current_ata = None
    option_letters = ["A", "B", "C", "D"]

    total_q = len(exam.questions)
    for idx, q in enumerate(exam.questions):
        # Tampilkan pita header ATA jika berganti ATA
        if q.ata != current_ata:
            current_ata = q.ata
            ata_label = f"ATA CHAPTER {current_ata}"
            if q.ata_title:
                ata_label = f"{ata_label} — {q.ata_title.upper()}"

            ata_p = Paragraph(f"<b>{ata_label}</b>", ata_header_style)
            ata_table = Table([[ata_p]], colWidths=[18.0 * cm])
            ata_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1F497D")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ])
            )
            story.append(Spacer(1, 0.2 * cm))
            story.append(ata_table)
            story.append(Spacer(1, 0.2 * cm))

        # Tabel untuk satu butir soal
        num_str = f"{q.order_number}."
        num_p = Paragraph(num_str, q_num_style)
        text_p = Paragraph(q.question_text, q_text_style)

        q_table_data = [[num_p, text_p]]

        # Opsi jawaban
        for opt_idx, opt_text in enumerate(q.options):
            let = option_letters[opt_idx] if opt_idx < len(option_letters) else f"{opt_idx+1}"
            let_p = Paragraph(f"{let}.", opt_label_style)
            opt_p = Paragraph(opt_text, opt_text_style)
            q_table_data.append([let_p, opt_p])

        q_table = Table(q_table_data, colWidths=[0.8 * cm, 17.2 * cm])
        q_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ])
        )

        # Pastikan satu nomor soal tidak terpotong halaman secara canggung
        story.append(KeepTogether(q_table))
        story.append(Spacer(1, 0.25 * cm))

        if progress_callback and idx % 10 == 0:
            pct = 0.3 + 0.5 * (idx / total_q)
            progress_callback(pct, f"Menyusun soal {idx+1}/{total_q}...")

    if progress_callback:
        progress_callback(0.85, "Menulis dokumen PDF...")

    # Siapkan Canvas kustom
    def canvas_maker(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.exam_model = exam.set_name.upper()
        c.prepared_by = exam.config.prepared_by
        c.form_no = exam.config.form_no if exam.config.form_no else "U-065 R0"
        c.issue = exam.config.issue
        c.year = exam.config.year
        return c

    doc.build(story, canvasmaker=canvas_maker)

    if progress_callback:
        progress_callback(1.0, f"Selesai membuat PDF Set {exam.set_name}.")

    return out_file
