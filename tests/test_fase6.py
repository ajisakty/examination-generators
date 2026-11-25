import time
from pathlib import Path
import pypdfium2 as pdfium
import pytest

from core.excel_loader import load_and_validate_exam_excel
from core.shuffler import create_set_b
from core.exam_pdf import generate_exam_pdf
from core.answer_key import generate_answer_key_excel, load_and_verify_answer_key
from core.scanner import scan_pdf_batch
from core.analyzer import analyze_exam_results
from core.report_pdf import generate_analysis_report_pdf


def test_end_to_end_flow(tmp_path):
    """
    Uji Alur Lengkap End-to-End (Fitur 1 lalu Fitur 2):
    1. Fitur 1:
       - Membaca dan memvalidasi Excel bank soal (Set A)
       - Mengacak urutan soal per ATA untuk menghasilkan Set B (dengan seed)
       - Menghasilkan file PDF naskah soal Set A dan Set B
       - Menghasilkan file Excel Kunci Jawaban 4-sheet lengkap dengan hash
       - Memverifikasi ulang integritas Excel Kunci Jawaban
    2. Fitur 2:
       - Memindai lembar jawaban ujian Set A dan Set B
       - Menganalisis hasil ujian (skor per lembar, rate per Question Code, highlight)
       - Menghasilkan file PDF Laporan Analisis Ujian
    """
    sample_a_path = Path("tests/fixtures/Exam Sample A.xlsx")
    sample_b_path = Path("tests/fixtures/Exam Sample B.xlsx")
    pdf_a_fixture = Path("tests/fixtures/exam A_261124_123544.pdf")
    pdf_b_fixture = Path("tests/fixtures/exam B_261124_123524.pdf")

    if not (sample_a_path.is_file() and sample_b_path.is_file() and pdf_a_fixture.is_file() and pdf_b_fixture.is_file()):
        pytest.skip("Fixture untuk uji alur lengkap tidak lengkap")

    # --- FITUR 1: PEMBUATAN SOAL & KUNCI JAWABAN ---
    # 1. Baca Set A
    exam_a, warnings_a = load_and_validate_exam_excel(sample_a_path, set_name="A")
    assert exam_a.config.total_questions == 32

    # 2. Acak untuk Set B
    exam_b, seed_used, warnings_b = create_set_b(exam_a, seed=12345)
    assert len(exam_b.questions) == 32
    assert seed_used == 12345

    # 3. Generate PDF Soal Set A dan Set B
    pdf_a_out = tmp_path / "Exam_A.pdf"
    pdf_b_out = tmp_path / "Exam_B.pdf"
    generate_exam_pdf(exam_a, pdf_a_out)
    generate_exam_pdf(exam_b, pdf_b_out)

    assert pdf_a_out.is_file() and pdf_a_out.stat().st_size > 1000
    assert pdf_b_out.is_file() and pdf_b_out.stat().st_size > 1000

    # 4. Generate Excel Kunci Jawaban
    key_excel_out = tmp_path / "Kunci_Jawaban.xlsx"
    out_key_path = generate_answer_key_excel(exam_a, exam_b, key_excel_out, seed=seed_used)
    assert out_key_path.is_file()

    # 5. Baca dan verifikasi ulang Excel Kunci Jawaban
    meta, sets_dict, key_warnings = load_and_verify_answer_key(key_excel_out)
    assert len(key_warnings) == 0
    assert len(sets_dict["A"]) == 32
    assert len(sets_dict["B"]) == 32
    assert meta.get("Total Questions") == 32

    # --- FITUR 2: PEMINDAIAN LEMBAR JAWABAN & ANALISIS ---
    # Muat Exam B resmi untuk pemindaian fixture lembar jawaban B
    exam_b_fixture, _ = load_and_validate_exam_excel(sample_b_path, set_name="B")

    # 6. Pindai batch lembar jawaban Set A dan Set B
    batch_a = scan_pdf_batch(pdf_a_fixture, total_questions=32, expected_set="A")
    batch_b = scan_pdf_batch(pdf_b_fixture, total_questions=32, expected_set="B")
    assert batch_a.total_sheets == 3
    assert batch_b.total_sheets == 3

    # 7. Analisis hasil ujian
    report = analyze_exam_results(exam_a, exam_b_fixture, sheets_a=batch_a.sheets, sheets_b=batch_b.sheets)
    assert report.summary.total_sheets == 6
    assert report.summary.passed_count == 6
    assert report.summary.pass_mark == 75.0
    assert len(report.question_analyses) == 32

    # 8. Cetak Laporan PDF
    report_pdf_out = tmp_path / "Laporan_Analisis_E2E.pdf"
    generate_analysis_report_pdf(report, report_pdf_out)

    assert report_pdf_out.is_file()
    assert report_pdf_out.stat().st_size > 5000


def test_benchmark_100_sheets(tmp_path):
    """
    Uji Skala & Benchmark:
    Menggandakan lembar uji hingga 100 halaman, menjalankan pemindaian OMR,
    dan mencatat waktu eksekusi total serta performa rata-rata per lembar.
    """
    pdf_fixture = Path("tests/fixtures/exam A_261124_123544.pdf")
    if not pdf_fixture.is_file():
        pytest.skip("Fixture scan tidak ditemukan untuk benchmark")

    # Buat PDF 100 halaman dengan pypdfium2
    src_doc = pdfium.PdfDocument(pdf_fixture)
    total_src_pages = len(src_doc)
    doc_100 = pdfium.PdfDocument.new()

    page_indices = [i % total_src_pages for i in range(100)]
    doc_100.import_pages(src_doc, page_indices)

    pdf_100_path = tmp_path / "benchmark_100_sheets.pdf"
    doc_100.save(pdf_100_path)
    assert len(doc_100) == 100

    # Catat progres dan waktu
    progress_calls = 0

    def progress_tracker(pct, msg):
        nonlocal progress_calls
        progress_calls += 1

    start_time = time.perf_counter()
    batch_result = scan_pdf_batch(
        pdf_path=pdf_100_path,
        total_questions=32,
        expected_set="A",
        progress_callback=progress_tracker,
    )
    elapsed_seconds = time.perf_counter() - start_time
    avg_per_sheet = elapsed_seconds / 100.0

    print(
        f"\n[BENCHMARK] Pemindaian 100 lembar selesai dalam {elapsed_seconds:.2f} detik "
        f"({avg_per_sheet:.3f} detik/lembar)."
    )

    assert batch_result.total_sheets == 100
    assert progress_calls > 10
    # Waktu pemrosesan 100 lembar harus wajar di lingkungan desktop (di bawah 120 detik)
    assert elapsed_seconds < 120.0
