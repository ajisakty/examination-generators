from pathlib import Path
import pytest
import openpyxl

from core.excel_loader import load_and_validate_exam_excel, ExcelValidationError
from core.models import Exam


def create_minimal_workbook(
    config_rows=None,
    headers=None,
    question_rows=None,
    include_config=True,
    include_questions=True,
):
    """Helper untuk membuat openpyxl Workbook in-memory untuk tes."""
    wb = openpyxl.Workbook()
    # Sheet default
    ws_default = wb.active
    ws_default.title = "README"

    if include_config:
        ws_cfg = wb.create_sheet(title="Config")
        default_config = [
            ("Course Title", "AIRBUS A320 TRAINING"),
            ("Sub Course Title", "BASIC SYSTEMS"),
            ("Exam Name", "EXAMINATION 1"),
            ("Course Code", "TRN-A320-01"),
            ("Duration (minutes)", 60),
            ("Total Questions", len(question_rows) if question_rows else 1),
            ("Max Options per Question", 4),
            ("Total Score", 100),
            ("Pass Mark (%)", 75),
        ]
        rows = config_rows if config_rows is not None else default_config
        for r in rows:
            ws_cfg.append(list(r))

    if include_questions:
        ws_q = wb.create_sheet(title="Questions")
        default_headers = [
            "No", "ATA", "ATA Title", "Question",
            "Option A", "Option B", "Option C", "Option D",
            "Answer", "Level", "Question Code"
        ]
        h = headers if headers is not None else default_headers
        ws_q.append(h)

        if question_rows is not None:
            for q in question_rows:
                ws_q.append(list(q))
        else:
            ws_q.append([
                1, "21", "Air Conditioning", "Sample Question 1?",
                "Opt A", "Opt B", "Opt C", "Opt D", "A", 1, "QC-001"
            ])

    return wb


def test_load_sample_a_fixture():
    """Uji membaca file fixture asli Exam Sample A.xlsx."""
    sample_a_path = Path("tests/fixtures/Exam Sample A.xlsx")
    if not sample_a_path.is_file():
        pytest.skip("Fixture Exam Sample A.xlsx tidak ditemukan")

    exam, warnings = load_and_validate_exam_excel(sample_a_path, set_name="A")
    assert isinstance(exam, Exam)
    assert exam.set_name == "A"
    assert exam.config.course_code == "JCT-0220408A"
    assert exam.config.total_questions == 32
    assert len(exam.questions) == 32
    assert exam.questions[0].question_code == "1"
    assert exam.questions[0].ata == "21"
    assert exam.questions[0].correct_answer == "A"


def test_load_sample_b_fixture():
    """Uji membaca file fixture asli Exam Sample B.xlsx."""
    sample_b_path = Path("tests/fixtures/Exam Sample B.xlsx")
    if not sample_b_path.is_file():
        pytest.skip("Fixture Exam Sample B.xlsx tidak ditemukan")

    exam, warnings = load_and_validate_exam_excel(sample_b_path, set_name="B")
    assert exam.set_name == "B"
    assert len(exam.questions) == 32


def test_alphanumeric_ata(tmp_path):
    """Uji ATA alfanumerik (misalnya '36A')."""
    wb = create_minimal_workbook(
        question_rows=[
            [1, "36A", "Pneumatic", "Soal Pneumatic?", "A1", "B1", "C1", "D1", "B", 1, "QC-100"]
        ]
    )
    file_path = tmp_path / "ata_test.xlsx"
    wb.save(file_path)

    exam, _ = load_and_validate_exam_excel(file_path)
    assert len(exam.questions) == 1
    assert exam.questions[0].ata == "36A"


def test_missing_sheets(tmp_path):
    """Uji sheet Config atau Questions tidak ada."""
    wb = openpyxl.Workbook()
    file_path = tmp_path / "empty.xlsx"
    wb.save(file_path)

    with pytest.raises(ExcelValidationError) as exc_info:
        load_and_validate_exam_excel(file_path)

    errors = exc_info.value.errors
    assert any("Sheet wajib 'Config' tidak ditemukan" in e for e in errors)
    assert any("Sheet wajib 'Questions' tidak ditemukan" in e for e in errors)


def test_missing_config_fields(tmp_path):
    """Uji validasi jika Course Title atau Course Code kosong di sheet Config."""
    cfg = [
        ("Course Title", ""),
        ("Course Code", ""),
        ("Duration (minutes)", -10),
        ("Max Options per Question", 5),
    ]
    wb = create_minimal_workbook(config_rows=cfg)
    file_path = tmp_path / "bad_config.xlsx"
    wb.save(file_path)

    with pytest.raises(ExcelValidationError) as exc_info:
        load_and_validate_exam_excel(file_path)

    errors = exc_info.value.errors
    assert any("Course Title" in e for e in errors)
    assert any("Course Code" in e for e in errors)
    assert any("Duration" in e for e in errors)
    assert any("Max Options" in e for e in errors)


def test_question_code_empty_and_duplicate(tmp_path):
    """Uji Question Code kosong dan duplikat dilaporkan dengan nomor baris."""
    q_rows = [
        [1, "21", "Title", "Soal 1", "A", "B", "C", "D", "A", 1, "QC-DUPLICATE"],
        [2, "21", "Title", "Soal 2", "A", "B", "C", "D", "B", 1, ""],  # Kosong
        [3, "21", "Title", "Soal 3", "A", "B", "C", "D", "C", 1, "QC-DUPLICATE"],  # Duplikat
    ]
    wb = create_minimal_workbook(question_rows=q_rows)
    file_path = tmp_path / "bad_qcodes.xlsx"
    wb.save(file_path)

    with pytest.raises(ExcelValidationError) as exc_info:
        load_and_validate_exam_excel(file_path)

    errors = exc_info.value.errors
    assert any("Question Code wajib terisi" in e and "baris 3" in e for e in errors)
    assert any("duplikat dengan baris 2" in e and "baris 4" in e for e in errors)


def test_invalid_answers_and_missing_options(tmp_path):
    """Uji kunci jawaban salah ('X') dan opsi A kosong."""
    q_rows = [
        [1, "21", "Title", "Soal 1", "", "B", "C", "D", "X", 1, "QC-01"],
    ]
    wb = create_minimal_workbook(question_rows=q_rows)
    file_path = tmp_path / "bad_answers.xlsx"
    wb.save(file_path)

    with pytest.raises(ExcelValidationError) as exc_info:
        load_and_validate_exam_excel(file_path)

    errors = exc_info.value.errors
    assert any("Option A" in e and "wajib diisi" in e for e in errors)
    assert any("Kunci jawaban 'X' tidak valid" in e for e in errors)


def test_three_options_mode(tmp_path):
    """Uji konfigurasi ujian 3 opsi."""
    cfg = [
        ("Course Title", "AIRBUS A320 3-OPSI"),
        ("Course Code", "TRN-03"),
        ("Max Options per Question", 3),
    ]
    q_rows = [
        [1, "21", "Title", "Soal 1", "A", "B", "C", None, "C", 1, "QC-01"],
    ]
    wb = create_minimal_workbook(config_rows=cfg, question_rows=q_rows)
    file_path = tmp_path / "three_opts.xlsx"
    wb.save(file_path)

    exam, warnings = load_and_validate_exam_excel(file_path)
    assert exam.config.num_options == 3
    assert len(exam.questions[0].options) == 3
    assert exam.questions[0].correct_answer == "C"

    # Jika kunci 'D' pada ujian 3 opsi -> harus error
    q_rows_bad = [
        [1, "21", "Title", "Soal 1", "A", "B", "C", None, "D", 1, "QC-01"],
    ]
    wb_bad = create_minimal_workbook(config_rows=cfg, question_rows=q_rows_bad)
    file_path_bad = tmp_path / "three_opts_bad_key.xlsx"
    wb_bad.save(file_path_bad)

    with pytest.raises(ExcelValidationError) as exc_info:
        load_and_validate_exam_excel(file_path_bad)
    assert any("Kunci jawaban 'D' tidak valid" in e for e in exc_info.value.errors)


def test_max_questions_exceeded(tmp_path):
    """Uji jumlah soal melebihi batas 100."""
    q_rows = [
        [i, "21", "Title", f"Soal {i}", "A", "B", "C", "D", "A", 1, f"QC-{i:03d}"]
        for i in range(1, 102)
    ]
    wb = create_minimal_workbook(question_rows=q_rows)
    file_path = tmp_path / "over_100.xlsx"
    wb.save(file_path)

    with pytest.raises(ExcelValidationError) as exc_info:
        load_and_validate_exam_excel(file_path)

    errors = exc_info.value.errors
    assert any("melebihi batas maksimal 100 soal" in e for e in errors)
