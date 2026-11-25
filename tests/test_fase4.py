from pathlib import Path
import pytest
from core.excel_loader import load_and_validate_exam_excel
from core.scanner import scan_pdf_batch, scan_single_sheet
from core.models import ScannerBatchResult, SheetScanResult


@pytest.fixture
def exam_keys_a():
    sample_a_path = Path("tests/fixtures/Exam Sample A.xlsx")
    exam, _ = load_and_validate_exam_excel(sample_a_path, set_name="A")
    return {q.order_number: q.correct_answer for q in exam.questions}


@pytest.fixture
def exam_keys_b():
    sample_b_path = Path("tests/fixtures/Exam Sample B.xlsx")
    exam, _ = load_and_validate_exam_excel(sample_b_path, set_name="B")
    return {q.order_number: q.correct_answer for q in exam.questions}


def test_scan_exam_a_ground_truth(exam_keys_a, tmp_path):
    """
    Uji ground truth 3 lembar Exam A sesuai PLAN.md Bagian 8:
    - A1: Benar 28/32, Salah di nomor 5, 7, 10, 11
    - A2: Benar 29/32, Salah di nomor 10, 11, 25
    - A3: Benar 29/32, Salah di nomor 7, 10, 11
    """
    pdf_path = Path("tests/fixtures/exam A_261124_123544.pdf")
    if not pdf_path.is_file():
        pytest.skip("Fixture exam A tidak ditemukan")

    review_dir = tmp_path / "review_a"
    batch_res = scan_pdf_batch(
        pdf_path=pdf_path,
        total_questions=32,
        expected_set="A",
        review_output_dir=review_dir,
    )

    assert isinstance(batch_res, ScannerBatchResult)
    assert batch_res.total_sheets == 3

    # Evaluasi lembar A1
    sheet_a1 = batch_res.sheets[0]
    wrong_a1 = [q for q in range(1, 33) if sheet_a1.answers[q].selected_option != exam_keys_a[q]]
    correct_a1 = 32 - len(wrong_a1)
    assert correct_a1 == 28, f"A1 expected 28/32 correct, got {correct_a1}"
    assert wrong_a1 == [5, 7, 10, 11], f"A1 wrong numbers mismatch: {wrong_a1}"

    # Evaluasi lembar A2
    sheet_a2 = batch_res.sheets[1]
    wrong_a2 = [q for q in range(1, 33) if sheet_a2.answers[q].selected_option != exam_keys_a[q]]
    correct_a2 = 32 - len(wrong_a2)
    assert correct_a2 == 29, f"A2 expected 29/32 correct, got {correct_a2}"
    assert wrong_a2 == [10, 11, 25], f"A2 wrong numbers mismatch: {wrong_a2}"

    # Evaluasi lembar A3
    sheet_a3 = batch_res.sheets[2]
    wrong_a3 = [q for q in range(1, 33) if sheet_a3.answers[q].selected_option != exam_keys_a[q]]
    correct_a3 = 32 - len(wrong_a3)
    assert correct_a3 == 29, f"A3 expected 29/32 correct, got {correct_a3}"
    assert wrong_a3 == [7, 10, 11], f"A3 wrong numbers mismatch: {wrong_a3}"


def test_scan_exam_b_ground_truth(exam_keys_b, tmp_path):
    """
    Uji ground truth 3 lembar Exam B sesuai PLAN.md Bagian 8:
    - B1: Benar 31/32, Salah di nomor 16 (dan ada peringatan bekas hapusan di exam code A)
    - B2: Benar 31/32, Salah di nomor 16
    - B3: Benar 30/32, Salah di nomor 16, 32
    """
    pdf_path = Path("tests/fixtures/exam B_261124_123524.pdf")
    if not pdf_path.is_file():
        pytest.skip("Fixture exam B tidak ditemukan")

    review_dir = tmp_path / "review_b"
    batch_res = scan_pdf_batch(
        pdf_path=pdf_path,
        total_questions=32,
        expected_set="B",
        review_output_dir=review_dir,
    )

    assert batch_res.total_sheets == 3

    # Evaluasi lembar B1
    sheet_b1 = batch_res.sheets[0]
    wrong_b1 = [q for q in range(1, 33) if sheet_b1.answers[q].selected_option != exam_keys_b[q]]
    correct_b1 = 32 - len(wrong_b1)
    assert correct_b1 == 31, f"B1 expected 31/32 correct, got {correct_b1}"
    assert wrong_b1 == [16], f"B1 wrong numbers mismatch: {wrong_b1}"

    # Verifikasi kasus uji peringatan bekas hapusan tipis di exam code A pada B1
    assert any("bekas tanda tipis/terhapus di kotak kode exam A" in w for w in sheet_b1.warnings)

    # Evaluasi lembar B2
    sheet_b2 = batch_res.sheets[1]
    wrong_b2 = [q for q in range(1, 33) if sheet_b2.answers[q].selected_option != exam_keys_b[q]]
    correct_b2 = 32 - len(wrong_b2)
    assert correct_b2 == 31, f"B2 expected 31/32 correct, got {correct_b2}"
    assert wrong_b2 == [16], f"B2 wrong numbers mismatch: {wrong_b2}"

    # Evaluasi lembar B3
    sheet_b3 = batch_res.sheets[2]
    wrong_b3 = [q for q in range(1, 33) if sheet_b3.answers[q].selected_option != exam_keys_b[q]]
    correct_b3 = 32 - len(wrong_b3)
    assert correct_b3 == 30, f"B3 expected 30/32 correct, got {correct_b3}"
    assert wrong_b3 == [16, 32], f"B3 wrong numbers mismatch: {wrong_b3}"


def test_scanner_progress_callback():
    """Uji fungsi scanner menerima dan memanggil progress_callback secara proporsional."""
    pdf_path = Path("tests/fixtures/exam A_261124_123544.pdf")
    if not pdf_path.is_file():
        pytest.skip("Fixture exam A tidak ditemukan")

    progress_log = []

    def callback(pct, msg):
        progress_log.append((pct, msg))

    scan_pdf_batch(
        pdf_path=pdf_path,
        total_questions=32,
        progress_callback=callback,
    )

    assert len(progress_log) >= 3
    assert progress_log[0][0] <= 0.1
    assert progress_log[-1][0] == 1.0
