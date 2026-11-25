from pathlib import Path
import pytest
from core.models import (
    Exam,
    ExamConfig,
    Question,
    QuestionAnswerResult,
    SheetScanResult,
)
from core.analyzer import calculate_sheet_score, analyze_exam_results
from core.report_pdf import generate_analysis_report_pdf
from core.excel_loader import load_and_validate_exam_excel
from core.scanner import scan_pdf_batch


def test_calculate_sheet_score_floor_rounding():
    """
    Uji kalkulasi skor per lembar:
    - Pembulatan ke bawah (floor) ke integer terdekat.
    - 28 / 32 = 87.5% -> skor 87.
    - 23 / 32 = 71.875% -> skor 71.
    - 24 / 32 = 75.0% -> skor 75 (sama dengan pass_mark 75 -> is_passed = True).
    """
    keys = {i: "A" for i in range(1, 33)}

    # Lembar 28 benar
    answers_28 = {
        i: QuestionAnswerResult(
            question_number=i,
            selected_option="A" if i <= 28 else "B",
            status="jelas",
            needs_review=False,
        )
        for i in range(1, 33)
    }
    sheet_28 = SheetScanResult(sheet_index=1, detected_set="A", answers=answers_28)
    res_28 = calculate_sheet_score(sheet_28, keys, total_questions=32, pass_mark=75.0)

    assert res_28.correct_count == 28
    assert res_28.score == 87  # 87.5 dibulatkan ke bawah menjadi 87
    assert res_28.is_passed is True
    assert res_28.wrong_questions == [29, 30, 31, 32]

    # Lembar 23 benar (71.875% -> 71, gagal)
    answers_23 = {
        i: QuestionAnswerResult(
            question_number=i,
            selected_option="A" if i <= 23 else "B",
            status="jelas",
            needs_review=False,
        )
        for i in range(1, 33)
    }
    sheet_23 = SheetScanResult(sheet_index=2, detected_set="A", answers=answers_23)
    res_23 = calculate_sheet_score(sheet_23, keys, total_questions=32, pass_mark=75.0)

    assert res_23.correct_count == 23
    assert res_23.score == 71
    assert res_23.is_passed is False

    # Lembar 24 benar (75.0% -> 75, pas lulus)
    answers_24 = {
        i: QuestionAnswerResult(
            question_number=i,
            selected_option="A" if i <= 24 else "B",
            status="jelas",
            needs_review=False,
        )
        for i in range(1, 33)
    }
    sheet_24 = SheetScanResult(sheet_index=3, detected_set="A", answers=answers_24)
    res_24 = calculate_sheet_score(sheet_24, keys, total_questions=32, pass_mark=75.0)

    assert res_24.correct_count == 24
    assert res_24.score == 75
    assert res_24.is_passed is True


def test_highlight_rate_exact_boundaries():
    """
    Uji aturan PLAN.md:
    Highlight: rate > 90% (terlalu mudah) dan < 50% (terlalu sulit / periksa soal).
    Tepat 90% dan 50% TIDAK ditandai.
    """
    config = ExamConfig(
        title="Uji Highlight",
        course_name="Highlight Test",
        course_code="TST-001",
        duration_minutes=60,
        total_questions=5,
        num_options=4,
        pass_mark=75.0,
    )

    # Buat 5 butir soal
    # Q1: 10 peserta, 10 benar = 100% -> TERLALU_MUDAH
    # Q2: 10 peserta, 9 benar = 90% -> None (tepat 90% TIDAK ditandai)
    # Q3: 10 peserta, 7 benar = 70% -> None
    # Q4: 10 peserta, 5 benar = 50% -> None (tepat 50% TIDAK ditandai)
    # Q5: 10 peserta, 4 benar = 40% -> TERLALU_SULIT
    questions = [
        Question(question_code=f"QC-{i}", ata="21", question_text=f"Soal {i}", options=["A", "B", "C", "D"], correct_answer="A", order_number=i)
        for i in range(1, 6)
    ]
    exam_a = Exam(config=config, set_name="A", questions=questions)
    exam_b = Exam(config=config, set_name="B", questions=questions)

    # Buat 10 lembar jawaban Set A
    sheets_a = []
    for s_idx in range(1, 11):
        ans = {}
        # Q1: semua benar
        ans[1] = QuestionAnswerResult(question_number=1, selected_option="A", status="jelas", needs_review=False)
        # Q2: peserta 1..9 benar (90%)
        ans[2] = QuestionAnswerResult(question_number=2, selected_option="A" if s_idx <= 9 else "B", status="jelas", needs_review=False)
        # Q3: peserta 1..7 benar (70%)
        ans[3] = QuestionAnswerResult(question_number=3, selected_option="A" if s_idx <= 7 else "B", status="jelas", needs_review=False)
        # Q4: peserta 1..5 benar (50%)
        ans[4] = QuestionAnswerResult(question_number=4, selected_option="A" if s_idx <= 5 else "B", status="jelas", needs_review=False)
        # Q5: peserta 1..4 benar (40%)
        ans[5] = QuestionAnswerResult(question_number=5, selected_option="A" if s_idx <= 4 else "B", status="jelas", needs_review=False)

        sheets_a.append(SheetScanResult(sheet_index=s_idx, detected_set="A", answers=ans))

    report = analyze_exam_results(exam_a, exam_b, sheets_a=sheets_a, sheets_b=[])

    analyses = {q.question_code: q for q in report.question_analyses}
    assert analyses["QC-1"].total_rate == 100.0
    assert analyses["QC-1"].highlight_status == "TERLALU_MUDAH"

    assert analyses["QC-2"].total_rate == 90.0
    assert analyses["QC-2"].highlight_status is None  # Tepat 90% tidak ditandai

    assert analyses["QC-3"].total_rate == 70.0
    assert analyses["QC-3"].highlight_status is None

    assert analyses["QC-4"].total_rate == 50.0
    assert analyses["QC-4"].highlight_status is None  # Tepat 50% tidak ditandai

    assert analyses["QC-5"].total_rate == 40.0
    assert analyses["QC-5"].highlight_status == "TERLALU_SULIT"

    # Hanya QC-1 dan QC-5 yang masuk daftar highlighted_questions
    assert [q.question_code for q in report.highlighted_questions] == ["QC-1", "QC-5"]


def test_guard_unresolved_needs_review():
    """
    Memastikan analyze_exam_results menolak memproses jika masih ada
    lembar jawaban yang berstatus needs_review.
    """
    config = ExamConfig(
        title="Uji Guard",
        course_name="Guard Test",
        course_code="TST-002",
        duration_minutes=30,
        total_questions=1,
        num_options=4,
    )
    questions = [
        Question(question_code="QC-1", ata="21", question_text="Soal 1", options=["A", "B", "C", "D"], correct_answer="A", order_number=1)
    ]
    exam = Exam(config=config, set_name="A", questions=questions)

    # Lembar dengan needs_review = True
    sheet_ambiguous = SheetScanResult(
        sheet_index=1,
        detected_set="A",
        answers={1: QuestionAnswerResult(question_number=1, selected_option="A", status="ganda", needs_review=True)},
        needs_review=True,
    )

    with pytest.raises(ValueError, match="perlu review"):
        analyze_exam_results(exam, exam, sheets_a=[sheet_ambiguous], sheets_b=[])


def test_full_analysis_and_pdf_generation(tmp_path):
    """
    Uji integrasi menyeluruh:
    - Memuat fixture Exam Sample A dan B
    - Memindai PDF fixture scan Exam A (3 lembar) dan Exam B (3 lembar)
    - Menjalankan analyze_exam_results
    - Menghasilkan laporan PDF dengan generate_analysis_report_pdf
    - Memvalidasi isi laporan dan keberadaan file PDF
    """
    sample_a_path = Path("tests/fixtures/Exam Sample A.xlsx")
    sample_b_path = Path("tests/fixtures/Exam Sample B.xlsx")
    pdf_a_path = Path("tests/fixtures/exam A_261124_123544.pdf")
    pdf_b_path = Path("tests/fixtures/exam B_261124_123524.pdf")

    if not (pdf_a_path.is_file() and pdf_b_path.is_file()):
        pytest.skip("Fixture PDF scan tidak ditemukan")

    exam_a, _ = load_and_validate_exam_excel(sample_a_path, set_name="A")
    exam_b, _ = load_and_validate_exam_excel(sample_b_path, set_name="B")

    batch_a = scan_pdf_batch(pdf_a_path, total_questions=32, expected_set="A")
    batch_b = scan_pdf_batch(pdf_b_path, total_questions=32, expected_set="B")

    assert batch_a.total_sheets == 3
    assert batch_b.total_sheets == 3

    # Analisis hasil ujian
    report = analyze_exam_results(exam_a, exam_b, sheets_a=batch_a.sheets, sheets_b=batch_b.sheets)

    # Verifikasi ringkasan
    assert report.summary.total_sheets_a == 3
    assert report.summary.total_sheets_b == 3
    assert report.summary.total_sheets == 6
    assert len(report.sheet_scores) == 6
    assert len(report.question_analyses) == 32

    # Skor A1 (28/32 = 87), A2 (29/32 = 90), A3 (29/32 = 90) -> Rata-rata A ~ 89.0
    # Skor B1 (31/32 = 96), B2 (31/32 = 96), B3 (30/32 = 93) -> Rata-rata B ~ 95.0
    assert report.summary.passed_count == 6
    assert report.summary.pass_percentage == 100.0

    # Buat file PDF laporan
    out_pdf = tmp_path / "Laporan_Analisis_Hasil_Ujian.pdf"
    progress_log = []

    def p_cb(pct, msg):
        progress_log.append((pct, msg))

    res_path = generate_analysis_report_pdf(report, out_pdf, progress_callback=p_cb)

    assert res_path.is_file()
    assert res_path.stat().st_size > 5000  # File PDF terbentuk dan memiliki isi
    assert len(progress_log) >= 4
    assert progress_log[-1][0] == 1.0
