"""
Modul pembuat PDF Laporan Analisis Ujian (Fase 5).
Menghasilkan dokumen PDF laporan ringkasan ujian, tabel analisis butir soal berwarna,
dan daftar butir soal ter-highlight (terlalu mudah / terlalu sulit).
Sesuai aturan: Tidak menampilkan nama atau ID peserta.
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
    HRFlowable,
)
from reportlab.pdfgen import canvas

from .models import ExamAnalysisReport, QuestionAnalysisResult


class ReportNumberedCanvas(canvas.Canvas):
    """
    Canvas dua-tahap (two-pass) untuk laporan analisis,
    menghitung total halaman dinamis dan menggambar footer halaman.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

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
        self.setStrokeColor(colors.HexColor("#CCCCCC"))
        self.setLineWidth(0.5)

        width, height = A4
        margin_x = 1.5 * cm
        footer_y = 1.0 * cm

        # Garis horizontal footer
        self.line(margin_x, footer_y + 12, width - margin_x, footer_y + 12)

        # Teks footer (kiri: identifikasi laporan, kanan: nomor halaman)
        self.setFillColor(colors.HexColor("#555555"))
        left_text = "Exam Generator — Laporan Analisis Ujian & Performa Butir Soal"
        self.drawString(margin_x, footer_y, left_text)

        page_str = f"Halaman {self._pageNumber} dari {page_count}"
        self.drawRightString(width - margin_x, footer_y, page_str)
        self.restoreState()


def generate_analysis_report_pdf(
    report: ExamAnalysisReport,
    output_pdf_path: str | Path,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Path:
    """
    Membuat file PDF Laporan Analisis Ujian resmi.

    Args:
        report: Objek ExamAnalysisReport berisi seluruh metrik dan analisis soal.
        output_pdf_path: Path tujuan file PDF yang akan dibuat.
        progress_callback: Callback progres opsional (persen: 0.0 - 1.0, pesan: str).

    Returns:
        Path: Path absolut file PDF yang dihasilkan.
    """
    out_path = Path(output_pdf_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(0.1, "Menyiapkan tata letak laporan PDF...")

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.8 * cm,
    )

    styles = getSampleStyleSheet()

    # Kustomisasi Typography Styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#1A2530"),
        alignment=1,  # Center
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#4A5568"),
        alignment=1,
        spaceAfter=12,
    )

    h2_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=10,
        spaceAfter=6,
    )

    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#2D3748"),
    )

    cell_bold_style = ParagraphStyle(
        "TableCellBold",
        parent=cell_style,
        fontName="Helvetica-Bold",
    )

    story = []

    # 1. Judul Laporan
    story.append(Paragraph("LAPORAN ANALISIS HASIL UJIAN", title_style))
    course_info = f"{report.config.title} — {report.config.course_name} (Course Code: {report.config.course_code})"
    story.append(Paragraph(course_info, subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=10))

    if progress_callback:
        progress_callback(0.25, "Membuat tabel ringkasan statistik...")

    # 2. Ringkasan Statistik
    story.append(Paragraph("1. RINGKASAN STATISTIK UJIAN", h2_style))

    summary = report.summary
    summary_data = [
        [
            Paragraph("<b>Total Peserta</b>", cell_style),
            Paragraph(f"{summary.total_sheets} peserta (Set A: {summary.total_sheets_a}, Set B: {summary.total_sheets_b})", cell_style),
            Paragraph("<b>Standar Kelulusan (Pass Mark)</b>", cell_style),
            Paragraph(f"{summary.pass_mark}%", cell_style),
        ],
        [
            Paragraph("<b>Jumlah Lulus</b>", cell_style),
            Paragraph(f"{summary.passed_count} peserta ({summary.pass_percentage}%)", cell_style),
            Paragraph("<b>Jumlah Tidak Lulus</b>", cell_style),
            Paragraph(f"{summary.failed_count} peserta ({round(100.0 - summary.pass_percentage, 2)}%)", cell_style),
        ],
        [
            Paragraph("<b>Rata-rata Skor Total</b>", cell_style),
            Paragraph(f"<b>{summary.average_score_total}</b> (A: {summary.average_score_a}, B: {summary.average_score_b})", cell_style),
            Paragraph("<b>Rentang Nilai</b>", cell_style),
            Paragraph(f"Tertinggi: {summary.highest_score} | Terendah: {summary.lowest_score}", cell_style),
        ],
    ]

    summary_table = Table(summary_data, colWidths=[3.8 * cm, 5.0 * cm, 4.2 * cm, 5.0 * cm])
    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(summary_table)
    story.append(Spacer(1, 10))

    if progress_callback:
        progress_callback(0.45, "Menyusun tabel analisis butir soal...")

    # 3. Tabel Analisis Butir Soal
    story.append(Paragraph("2. ANALISIS TINGKAT KEBERHASILAN PER BUTIR SOAL", h2_style))
    keterangan_style = ParagraphStyle(
        "Keterangan", parent=styles["Normal"], fontName="Helvetica-Oblique", fontSize=7.5, leading=9, textColor=colors.HexColor("#64748B"), spaceAfter=6
    )
    story.append(
        Paragraph(
            "* Keterangan Highlight: Hijau = Tingkat keberhasilan >90% (Terlalu Mudah); "
            "Merah muda = Tingkat keberhasilan <50% (Terlalu Sulit / Periksa Soal). Tepat 90% dan 50% tidak ditandai.",
            keterangan_style,
        )
    )

    headers = [
        Paragraph("<b>No A</b>", cell_bold_style),
        Paragraph("<b>No B</b>", cell_bold_style),
        Paragraph("<b>Question Code</b>", cell_bold_style),
        Paragraph("<b>ATA</b>", cell_bold_style),
        Paragraph("<b>Kunci</b>", cell_bold_style),
        Paragraph("<b>Rate A</b>", cell_bold_style),
        Paragraph("<b>Rate B</b>", cell_bold_style),
        Paragraph("<b>Gabungan</b>", cell_bold_style),
        Paragraph("<b>Status</b>", cell_bold_style),
    ]

    analysis_rows = [headers]
    row_bg_styles = []

    for idx, q_res in enumerate(report.question_analyses, start=1):
        rate_a_str = f"{q_res.rate_a}%" if q_res.rate_a is not None else "-"
        rate_b_str = f"{q_res.rate_b}%" if q_res.rate_b is not None else "-"
        rate_tot_str = f"{q_res.total_rate}%"

        status_label = "-"
        if q_res.highlight_status == "TERLALU_MUDAH":
            status_label = "Terlalu Mudah"
            row_bg_styles.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#D4EDDA")))
        elif q_res.highlight_status == "TERLALU_SULIT":
            status_label = "Periksa Soal"
            row_bg_styles.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#F8D7DA")))
        elif idx % 2 == 0:
            row_bg_styles.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#F9FAFB")))

        row = [
            Paragraph(str(q_res.order_number_a or "-"), cell_style),
            Paragraph(str(q_res.order_number_b or "-"), cell_style),
            Paragraph(q_res.question_code, cell_bold_style),
            Paragraph(q_res.ata, cell_style),
            Paragraph(q_res.correct_answer, cell_bold_style),
            Paragraph(rate_a_str, cell_style),
            Paragraph(rate_b_str, cell_style),
            Paragraph(rate_tot_str, cell_bold_style),
            Paragraph(status_label, cell_style),
        ]
        analysis_rows.append(row)

    col_widths = [1.2 * cm, 1.2 * cm, 3.5 * cm, 1.5 * cm, 1.2 * cm, 2.0 * cm, 2.0 * cm, 2.4 * cm, 3.0 * cm]
    analysis_table = Table(analysis_rows, colWidths=col_widths, repeatRows=1)
    
    t_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ] + row_bg_styles

    analysis_table.setStyle(TableStyle(t_style))
    story.append(analysis_table)
    story.append(Spacer(1, 14))

    if progress_callback:
        progress_callback(0.7, "Menyusun butir soal yang di-highlight...")

    # 4. Detail Butir Soal Ter-highlight
    story.append(PageBreak())
    story.append(Paragraph("3. DAFTAR BUTIR SOAL PERLU EVALUASI KHUSUS", h2_style))

    if not report.highlighted_questions:
        story.append(
            Paragraph(
                "Tidak ada butir soal yang masuk kriteria highlight. Seluruh soal memiliki tingkat keberhasilan normal (antara 50% hingga 90%).",
                cell_style,
            )
        )
    else:
        story.append(
            Paragraph(
                f"Ditemukan {len(report.highlighted_questions)} butir soal yang membutuhkan evaluasi penyusun "
                f"(tingkat keberhasilan di atas 90% atau di bawah 50%):",
                cell_style,
            )
        )
        story.append(Spacer(1, 8))

        q_body_style = ParagraphStyle(
            "QBody", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#1F2937")
        )

        for q_hi in report.highlighted_questions:
            is_easy = q_hi.highlight_status == "TERLALU_MUDAH"
            badge_color = "#15803D" if is_easy else "#B91C1C"
            badge_bg = "#DCFCE7" if is_easy else "#FEE2E2"
            status_text = "TERLALU MUDAH (>90%)" if is_easy else "TERLALU SULIT (<50% — PERIKSA SOAL)"

            header_text = (
                f"<b>Question Code: {q_hi.question_code}</b> | ATA: {q_hi.ata} | "
                f"No. A: {q_hi.order_number_a or '-'} | No. B: {q_hi.order_number_b or '-'} | "
                f"Kunci: <b>{q_hi.correct_answer}</b> | Tingkat Benar: <b>{q_hi.total_rate}%</b> "
                f"(A: {q_hi.rate_a or 0}%, B: {q_hi.rate_b or 0}%)"
            )

            box_content = [
                [Paragraph(f"<font color='{badge_color}'><b>[{status_text}]</b></font> {header_text}", cell_style)],
                [Paragraph(q_hi.question_text, q_body_style)],
            ]

            card_table = Table(box_content, colWidths=[18.0 * cm])
            card_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(badge_bg)),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FFFFFF")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ])
            )

            story.append(KeepTogether([card_table, Spacer(1, 8)]))

    if progress_callback:
        progress_callback(0.9, "Menyusun file PDF akhir...")

    doc.build(story, canvasmaker=ReportNumberedCanvas)

    if progress_callback:
        progress_callback(1.0, f"Selesai membuat laporan PDF: {out_path.name}")

    return out_path
