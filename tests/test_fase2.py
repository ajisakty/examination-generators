import copy
from pathlib import Path
import pytest
import openpyxl
import pypdfium2 as pdfium

from core.excel_loader import load_and_validate_exam_excel
from core.shuffler import create_set_b
from core.answer_key import (
    generate_answer_key_excel,
    load_and_verify_answer_key,
    validate_cross_set_integrity,
    calculate_key_hash,
)
from core.exam_pdf import generate_exam_pdf
from core.models import Exam, ExamConfig, Question


@pytest.fixture
def sample_exam_a():
    sample_a_path = Path("tests/fixtures/Exam Sample A.xlsx")
    exam, _ = load_and_validate_exam_excel(sample_a_path, set_name="A")
    return exam


def test_shuffler_determinism(sample_exam_a):
    """Seed yang sama harus menghasilkan urutan soal Set B yang persis sama."""
    exam_b1, seed1, _ = create_set_b(sample_exam_a, seed=12345)
    exam_b2, seed2, _ = create_set_b(sample_exam_a, seed=12345)

    assert seed1 == seed2 == 12345
    assert len(exam_b1.questions) == len(exam_b2.questions) == 32

    codes_b1 = [q.question_code for q in exam_b1.questions]
    codes_b2 = [q.question_code for q in exam_b2.questions]
    assert codes_b1 == codes_b2


def test_shuffler_preserves_ata_and_questions(sample_exam_a):
    """
    Set B harus:
    1. Memiliki setiap Question Code tepat satu kali.
    2. Menjaga urutan kelompok ATA tetap sama dengan Set A.
    3. Mengacak urutan soal di dalam tiap ATA (urutan nomor soal berbeda dari Set A).
    4. Opsi jawaban (A-D) tidak berubah.
    """
    exam_b, seed, _ = create_set_b(sample_exam_a, seed=99999)

    codes_a = [q.question_code for q in sample_exam_a.questions]
    codes_b = [q.question_code for q in exam_b.questions]

    # Keunikan dan kelengkapan
    assert sorted(codes_a) == sorted(codes_b)
    assert len(set(codes_b)) == len(codes_b)

    # Urutan soal secara keseluruhan harus berbeda dari A
    assert codes_a != codes_b

    # Verifikasi urutan ATA
    atas_a = [q.ata for q in sample_exam_a.questions]
    atas_b = [q.ata for q in exam_b.questions]
    assert atas_a == atas_b, "Urutan kemunculan kelompok ATA harus identik antara A dan B"

    # Verifikasi opsi jawaban tidak diacak
    dict_a = {q.question_code: q for q in sample_exam_a.questions}
    dict_b = {q.question_code: q for q in exam_b.questions}
    for code, qa in dict_a.items():
        qb = dict_b[code]
        assert qa.options == qb.options
        assert qa.correct_answer == qb.correct_answer


def test_shuffler_similarity_warning(sample_exam_a):
    """Jika urutan tidak berubah atau sangat mirip, sistem mengeluarkan warning."""
    # Buat mini exam dengan ATA masing-masing hanya 1 soal (sehingga tidak bisa diacak)
    mini_exam = Exam(
        config=sample_exam_a.config,
        set_name="A",
        questions=sample_exam_a.questions[:1],  # hanya 1 soal
    )
    # Untuk 1 soal, total_multi_questions = 0 -> tidak ada warning kemiripan semu
    _, _, warnings = create_set_b(mini_exam, seed=123)
    assert len(warnings) == 0


def test_answer_key_generation_and_reading(tmp_path, sample_exam_a):
    """Uji pembuatan file Excel Kunci Jawaban 4 sheet dan pembacaan integritasnya."""
    exam_b, seed, _ = create_set_b(sample_exam_a, seed=54321)
    out_key_path = tmp_path / "Answer_Key_Test.xlsx"

    # Buat file kunci
    res_path = generate_answer_key_excel(sample_exam_a, exam_b, out_key_path, seed=seed)
    assert res_path.is_file()

    # Periksa 4 sheet ada
    wb = openpyxl.load_workbook(res_path, data_only=True)
    assert set(wb.sheetnames) == {"Meta", "Set A", "Set B", "Bank"}
    wb.close()

    # Baca kembali dan verifikasi hash
    meta, sets, errors = load_and_verify_answer_key(res_path)
    assert len(errors) == 0, f"Error tak terduga: {errors}"
    assert meta["Course Code"] == sample_exam_a.config.course_code
    assert meta["Random Seed"] == seed
    assert len(sets["A"]) == 32
    assert len(sets["B"]) == 32

    # Jawaban kunci per question code harus sama persis antara set A dan set B
    for q_code, key_a in sets["A"].items():
        assert sets["B"][q_code] == key_a


def test_answer_key_tamper_detection(tmp_path, sample_exam_a):
    """Jika file kunci diedit manual, sistem harus mendeteksi peringatan pelanggaran hash."""
    exam_b, seed, _ = create_set_b(sample_exam_a, seed=11111)
    out_key_path = tmp_path / "Answer_Key_Tampered.xlsx"
    generate_answer_key_excel(sample_exam_a, exam_b, out_key_path, seed=seed)

    # Edit manual kunci pada Set A
    wb = openpyxl.load_workbook(out_key_path)
    ws_a = wb["Set A"]
    orig_key = ws_a.cell(row=2, column=4).value
    ws_a.cell(row=2, column=4, value="B" if orig_key != "B" else "C")
    wb.save(out_key_path)
    wb.close()

    # Verifikasi peringatan integritas muncul
    meta, sets, errors = load_and_verify_answer_key(out_key_path)
    assert any("Peringatan Integritas: Hash kunci jawaban tidak cocok" in e for e in errors)


def test_cross_set_validation_fixtures():
    """
    Sesuai PLAN.md Bagian 8:
    Exam Sample A dan Exam Sample B sengaja memiliki kunci berbeda untuk Question Code 10 dan 11.
    Validasi lintas-set harus mendeteksi dan melaporkan kedua kode tersebut.
    """
    path_a = Path("tests/fixtures/Exam Sample A.xlsx")
    path_b = Path("tests/fixtures/Exam Sample B.xlsx")
    if not (path_a.is_file() and path_b.is_file()):
        pytest.skip("Fixture A atau B tidak ditemukan")

    exam_a, _ = load_and_validate_exam_excel(path_a, set_name="A")
    exam_b, _ = load_and_validate_exam_excel(path_b, set_name="B")

    errors = validate_cross_set_integrity(exam_a, exam_b)
    assert len(errors) >= 2
    # Harus ada error untuk Question Code 10 dan 11
    assert any("Question Code '10'" in e and "Kunci jawaban berbeda" in e for e in errors)
    assert any("Question Code '11'" in e and "Kunci jawaban berbeda" in e for e in errors)


def test_generate_exam_pdf_creation(tmp_path, sample_exam_a):
    """Uji pembuatan file PDF soal Set A dan Set B."""
    exam_b, seed, _ = create_set_b(sample_exam_a, seed=77777)

    pdf_a_path = tmp_path / "Exam_A.pdf"
    pdf_b_path = tmp_path / "Exam_B.pdf"

    progress_log = []

    def progress_tracker(pct, msg):
        progress_log.append((pct, msg))

    # Hasilkan PDF Set A
    res_a = generate_exam_pdf(sample_exam_a, pdf_a_path, progress_callback=progress_tracker)
    assert res_a.is_file()
    assert res_a.stat().st_size > 5000
    assert len(progress_log) > 0

    # Periksa PDF Set A dengan pdfium
    doc_a = pdfium.PdfDocument(res_a)
    assert len(doc_a) >= 1

    # Hasilkan PDF Set B
    res_b = generate_exam_pdf(exam_b, pdf_b_path)
    assert res_b.is_file()
    assert res_b.stat().st_size > 5000

    doc_b = pdfium.PdfDocument(res_b)
    assert len(doc_b) >= 1
