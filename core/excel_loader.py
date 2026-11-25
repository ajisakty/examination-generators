"""
Modul pembacaan dan validasi template Excel ujian.
Backend murni tanpa print dan GUI.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import openpyxl

from .models import Exam, ExamConfig, Question


class ExcelValidationError(Exception):
    """Exception yang membawa daftar pesan kesalahan validasi dalam Bahasa Indonesia."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        message = "\n".join(errors)
        super().__init__(message)


def load_and_validate_exam_excel(
    file_path: str | Path,
    set_name: str = "A"
) -> Tuple[Exam, List[str]]:
    """
    Membaca dan memvalidasi file Excel template ujian (sheet Config dan Questions).
    
    Returns:
        Tuple[Exam, List[str]]: Objek Exam dan daftar peringatan (warnings) jika ada.
        
    Raises:
        ExcelValidationError: Jika ditemukan satu atau lebih kesalahan validasi.
        FileNotFoundError: Jika file tidak ditemukan.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File Excel tidak ditemukan: {path}")

    try:
        wb = openpyxl.load_workbook(path, data_only=True)
    except Exception as e:
        raise ExcelValidationError([f"Gagal membuka file Excel '{path.name}': {str(e)}"])

    errors: List[str] = []
    warnings: List[str] = []

    # 1. Validasi Sheet wajib
    for required_sheet in ["Config", "Questions"]:
        if required_sheet not in wb.sheetnames:
            errors.append(f"Sheet wajib '{required_sheet}' tidak ditemukan pada file.")

    if errors:
        wb.close()
        raise ExcelValidationError(errors)

    ws_config = wb["Config"]
    ws_questions = wb["Questions"]

    # 2. Baca Config (Key-Value)
    config_dict: Dict[str, Any] = {}
    for row_idx, row in enumerate(ws_config.iter_rows(values_only=True), start=1):
        if not row or row[0] is None:
            continue
        key_raw = str(row[0]).strip()
        val_raw = row[1] if len(row) > 1 else None
        if key_raw:
            config_dict[key_raw] = val_raw

    # Validasi Config fields
    course_title = str(config_dict.get("Course Title") or "").strip()
    if not course_title:
        errors.append("Sheet Config, baris 'Course Title': Judul ujian tidak boleh kosong.")

    course_code = str(config_dict.get("Course Code") or "").strip()
    if not course_code:
        errors.append("Sheet Config, baris 'Course Code': Course Code tidak boleh kosong.")

    exam_name = str(config_dict.get("Exam Name") or "").strip()
    sub_title = str(config_dict.get("Sub Course Title") or "").strip()
    course_name = exam_name if exam_name else sub_title

    # Duration
    raw_duration = config_dict.get("Duration (minutes)")
    duration_minutes = 60
    if raw_duration is not None:
        try:
            duration_minutes = int(raw_duration)
            if duration_minutes <= 0:
                errors.append(f"Sheet Config, baris 'Duration (minutes)': Durasi harus > 0 (diberikan: {raw_duration}).")
        except (ValueError, TypeError):
            errors.append(f"Sheet Config, baris 'Duration (minutes)': Nilai '{raw_duration}' bukan angka integer valid.")

    # Max Options
    raw_max_options = config_dict.get("Max Options per Question")
    num_options = 4
    if raw_max_options is not None:
        try:
            num_options = int(raw_max_options)
            if num_options not in (3, 4):
                errors.append(f"Sheet Config, baris 'Max Options per Question': Jumlah opsi harus 3 atau 4 (diberikan: {raw_max_options}).")
        except (ValueError, TypeError):
            errors.append(f"Sheet Config, baris 'Max Options per Question': Nilai '{raw_max_options}' bukan angka integer valid.")

    # Total Score & Pass Mark
    total_score = 100.0
    raw_score = config_dict.get("Total Score")
    if raw_score is not None:
        try:
            total_score = float(raw_score)
        except (ValueError, TypeError):
            errors.append(f"Sheet Config, baris 'Total Score': Nilai '{raw_score}' bukan angka valid.")

    pass_mark = 75.0
    raw_pass = config_dict.get("Pass Mark (%)")
    if raw_pass is not None:
        try:
            pass_mark = float(raw_pass)
        except (ValueError, TypeError):
            errors.append(f"Sheet Config, baris 'Pass Mark (%)': Nilai '{raw_pass}' bukan angka valid.")

    # 3. Baca dan Validasi Sheet Questions
    header_row = None
    header_idx = None
    for idx, row in enumerate(ws_questions.iter_rows(values_only=True), start=1):
        if row and any(cell is not None for cell in row):
            # Mencari baris header (harus ada 'Question' atau 'No')
            str_row = [str(c).strip().lower() if c is not None else "" for c in row]
            if "question" in str_row and ("no" in str_row or "ata" in str_row):
                header_row = [str(c).strip() if c is not None else "" for c in row]
                header_idx = idx
                break

    if header_row is None:
        errors.append("Sheet Questions: Baris header tabel soal tidak ditemukan (wajib memiliki kolom 'No', 'Question', dll).")
        wb.close()
        raise ExcelValidationError(errors)

    # Identifikasi indeks kolom
    header_map: Dict[str, int] = {}
    for col_idx, col_name in enumerate(header_row):
        norm = col_name.lower().strip()
        header_map[norm] = col_idx

    col_no = header_map.get("no")
    col_ata = header_map.get("ata")
    col_ata_title = header_map.get("ata title")
    col_question = header_map.get("question")
    col_opt_a = header_map.get("option a")
    col_opt_b = header_map.get("option b")
    col_opt_c = header_map.get("option c")
    col_opt_d = header_map.get("option d")
    col_answer = header_map.get("answer")
    col_level = header_map.get("level")

    # Kolom Question Code: utamakan 'question code', fallback ke 'course code' pada sheet Questions
    col_q_code = header_map.get("question code")
    if col_q_code is None:
        col_q_code = header_map.get("course code")

    if col_q_code is None:
        errors.append("Sheet Questions: Kolom 'Question Code' tidak ditemukan.")
    if col_ata is None:
        errors.append("Sheet Questions: Kolom 'ATA' tidak ditemukan.")
    if col_question is None:
        errors.append("Sheet Questions: Kolom 'Question' tidak ditemukan.")
    if col_opt_a is None or col_opt_b is None or col_opt_c is None:
        errors.append("Sheet Questions: Kolom pilihan 'Option A', 'Option B', dan 'Option C' wajib ada.")
    if col_answer is None:
        errors.append("Sheet Questions: Kolom 'Answer' tidak ditemukan.")

    if errors:
        wb.close()
        raise ExcelValidationError(errors)

    questions: List[Question] = []
    seen_q_codes: Dict[str, int] = {}  # code -> row_number

    valid_answers_4 = {"A", "B", "C", "D"}
    valid_answers_3 = {"A", "B", "C"}

    for row_num, row in enumerate(
        ws_questions.iter_rows(min_row=header_idx + 1, values_only=True),
        start=header_idx + 1,
    ):
        # Lewati baris kosong
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        # Question text
        q_text_raw = row[col_question] if col_question < len(row) else None
        q_text = str(q_text_raw).strip() if q_text_raw is not None else ""
        if not q_text:
            errors.append(f"Sheet Questions, baris {row_num}, kolom 'Question': Teks soal tidak boleh kosong.")

        # Question Code
        q_code_raw = row[col_q_code] if col_q_code < len(row) else None
        q_code = str(q_code_raw).strip() if q_code_raw is not None else ""
        if not q_code:
            errors.append(f"Sheet Questions, baris {row_num}, kolom 'Question Code': Question Code wajib terisi.")
        else:
            if q_code in seen_q_codes:
                prev_row = seen_q_codes[q_code]
                errors.append(
                    f"Sheet Questions, baris {row_num}, kolom 'Question Code': "
                    f"Question Code '{q_code}' duplikat dengan baris {prev_row} (harus unik)."
                )
            else:
                seen_q_codes[q_code] = row_num

        # ATA
        ata_raw = row[col_ata] if col_ata < len(row) else None
        ata = str(ata_raw).strip() if ata_raw is not None else ""
        if not ata:
            errors.append(f"Sheet Questions, baris {row_num}, kolom 'ATA': Kode ATA wajib terisi.")

        # Options
        opt_a = str(row[col_opt_a]).strip() if col_opt_a < len(row) and row[col_opt_a] is not None else ""
        opt_b = str(row[col_opt_b]).strip() if col_opt_b < len(row) and row[col_opt_b] is not None else ""
        opt_c = str(row[col_opt_c]).strip() if col_opt_c < len(row) and row[col_opt_c] is not None else ""
        opt_d = (
            str(row[col_opt_d]).strip()
            if col_opt_d is not None and col_opt_d < len(row) and row[col_opt_d] is not None
            else ""
        )

        options: List[str] = []
        if opt_a:
            options.append(opt_a)
        else:
            errors.append(f"Sheet Questions, baris {row_num}, kolom 'Option A': Opsi A wajib diisi.")

        if opt_b:
            options.append(opt_b)
        else:
            errors.append(f"Sheet Questions, baris {row_num}, kolom 'Option B': Opsi B wajib diisi.")

        if opt_c:
            options.append(opt_c)
        else:
            errors.append(f"Sheet Questions, baris {row_num}, kolom 'Option C': Opsi C wajib diisi.")

        if num_options == 4:
            if opt_d:
                options.append(opt_d)
            else:
                errors.append(f"Sheet Questions, baris {row_num}, kolom 'Option D': Opsi D wajib diisi untuk format ujian 4 opsi.")
        else:
            # 3 opsi
            if opt_d:
                warnings.append(
                    f"Sheet Questions, baris {row_num}: Opsi D berisi teks '{opt_d}', tetapi konfigurasi ujian adalah 3 opsi."
                )

        # Answer
        ans_raw = row[col_answer] if col_answer < len(row) else None
        ans = str(ans_raw).strip().upper() if ans_raw is not None else ""
        valid_answers = valid_answers_4 if num_options == 4 else valid_answers_3

        if not ans:
            errors.append(f"Sheet Questions, baris {row_num}, kolom 'Answer': Kunci jawaban wajib diisi.")
        elif ans not in valid_answers:
            errors.append(
                f"Sheet Questions, baris {row_num}, kolom 'Answer': Kunci jawaban '{ans}' tidak valid. "
                f"Hanya boleh salah satu dari {sorted(list(valid_answers))}."
            )

        # No / Order number
        no_val = None
        if col_no is not None and col_no < len(row) and row[col_no] is not None:
            try:
                no_val = int(row[col_no])
            except (ValueError, TypeError):
                no_val = len(questions) + 1
        else:
            no_val = len(questions) + 1

        ata_title = (
            str(row[col_ata_title]).strip()
            if col_ata_title is not None and col_ata_title < len(row) and row[col_ata_title] is not None
            else ""
        )

        level_val = None
        if col_level is not None and col_level < len(row) and row[col_level] is not None:
            try:
                level_val = int(row[col_level])
            except (ValueError, TypeError):
                level_val = None

        q_item = Question(
            question_code=q_code,
            ata=ata,
            question_text=q_text,
            options=options,
            correct_answer=ans,
            order_number=no_val,
            ata_title=ata_title,
            level=level_val,
        )
        questions.append(q_item)

    # 4. Validasi jumlah soal
    actual_q_count = len(questions)
    if actual_q_count == 0:
        errors.append("Sheet Questions: Tidak ada soal yang ditemukan pada file Excel.")
    elif actual_q_count > 100:
        errors.append(f"Sheet Questions: Jumlah soal adalah {actual_q_count}, melebihi batas maksimal 100 soal.")

    # Sinkronisasi dengan Total Questions pada Config jika ada
    cfg_total_q = config_dict.get("Total Questions")
    if cfg_total_q is not None:
        try:
            cfg_total_int = int(cfg_total_q)
            if cfg_total_int != actual_q_count:
                warnings.append(
                    f"Sheet Config 'Total Questions' ({cfg_total_int}) berbeda dengan jumlah baris soal aktual ({actual_q_count}). "
                    f"Sistem akan menggunakan jumlah soal aktual ({actual_q_count})."
                )
        except (ValueError, TypeError):
            pass

    wb.close()

    if errors:
        raise ExcelValidationError(errors)

    # Buat objek Exam
    exam_config = ExamConfig(
        title=course_title,
        course_name=course_name,
        course_code=course_code,
        duration_minutes=duration_minutes,
        total_questions=actual_q_count,
        num_options=num_options,
        total_score=total_score,
        pass_mark=pass_mark,
        prepared_by=str(config_dict.get("Prepared By") or "").strip(),
        form_no=str(config_dict.get("Form No") or "").strip(),
        issue=int(config_dict.get("Issue") or 1) if str(config_dict.get("Issue") or "").isdigit() else 1,
        year=int(config_dict.get("Year") or 2026) if str(config_dict.get("Year") or "").isdigit() else 2026,
        model=str(config_dict.get("Model") or "").strip(),
    )

    exam = Exam(
        config=exam_config,
        set_name=set_name,
        questions=questions,
    )

    return exam, warnings
