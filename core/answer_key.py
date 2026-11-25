"""
Modul pembuatan dan verifikasi Excel Kunci Jawaban.
Memiliki 4 sheet: Meta, Set A, Set B, Bank.
Memiliki hash SHA-256 untuk mendeteksi pengeditan manual.
Validasi lintas-set memastikan teks, opsi, dan kunci konsisten antar set.
"""

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from .models import AnswerKeyMetadata, Exam, Question


def calculate_key_hash(
    course_code: str,
    questions_a: List[Question],
    questions_b: List[Question],
    seed: Optional[int] = None,
) -> str:
    """
    Menghitung hash SHA-256 dari kunci jawaban Set A dan Set B secara deterministik.
    """
    hasher = hashlib.sha256()
    hasher.update(str(course_code).strip().encode("utf-8"))
    hasher.update(str(seed if seed is not None else "").encode("utf-8"))

    # Urutkan berdasarkan question_code agar deterministik
    sorted_a = sorted(questions_a, key=lambda q: str(q.question_code).strip())
    for q in sorted_a:
        item_str = f"{q.question_code}|{q.ata}|{q.correct_answer}|{q.order_number}"
        hasher.update(item_str.encode("utf-8"))

    sorted_b = sorted(questions_b, key=lambda q: str(q.question_code).strip())
    for q in sorted_b:
        item_str = f"{q.question_code}|{q.ata}|{q.correct_answer}|{q.order_number}"
        hasher.update(item_str.encode("utf-8"))

    return hasher.hexdigest()


def validate_cross_set_integrity(exam_a: Exam, exam_b: Exam) -> List[str]:
    """
    Validasi lintas-set: Question Code yang sama harus memiliki teks soal, opsi, dan kunci yang sama.
    Jika berbeda, laporkan error per Question Code dalam Bahasa Indonesia.
    """
    errors: List[str] = []
    dict_a: Dict[str, Question] = {str(q.question_code).strip(): q for q in exam_a.questions}
    dict_b: Dict[str, Question] = {str(q.question_code).strip(): q for q in exam_b.questions}

    all_codes = sorted(list(set(dict_a.keys()) | set(dict_b.keys())))

    for code in all_codes:
        if code not in dict_a:
            errors.append(f"Question Code '{code}': Ditemukan di Set B (No. {dict_b[code].order_number}) tetapi tidak ada di Set A.")
            continue
        if code not in dict_b:
            errors.append(f"Question Code '{code}': Ditemukan di Set A (No. {dict_a[code].order_number}) tetapi tidak ada di Set B.")
            continue

        qa = dict_a[code]
        qb = dict_b[code]

        if str(qa.correct_answer).strip().upper() != str(qb.correct_answer).strip().upper():
            errors.append(
                f"Question Code '{code}': Kunci jawaban berbeda antara Set A ('{qa.correct_answer}', No. {qa.order_number}) "
                f"dan Set B ('{qb.correct_answer}', No. {qb.order_number})."
            )

        if str(qa.question_text).strip() != str(qb.question_text).strip():
            errors.append(
                f"Question Code '{code}': Teks soal berbeda antara Set A (No. {qa.order_number}) dan Set B (No. {qb.order_number})."
            )

        if qa.options != qb.options:
            errors.append(
                f"Question Code '{code}': Pilihan opsi jawaban berbeda antara Set A (No. {qa.order_number}) dan Set B (No. {qb.order_number})."
            )

    return errors


def generate_answer_key_excel(
    exam_a: Exam,
    exam_b: Exam,
    output_path: str | Path,
    seed: Optional[int] = None,
) -> Path:
    """
    Membuat file Excel Kunci Jawaban dengan 4 sheet: Meta, Set A, Set B, Bank.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Validasi lintas-set terlebih dahulu
    cross_errors = validate_cross_set_integrity(exam_a, exam_b)
    if cross_errors:
        raise ValueError("\n".join(cross_errors))

    content_hash = calculate_key_hash(
        course_code=exam_a.config.course_code,
        questions_a=exam_a.questions,
        questions_b=exam_b.questions,
        seed=seed,
    )

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    wb = openpyxl.Workbook()
    # Sheet 1: Meta
    ws_meta = wb.active
    ws_meta.title = "Meta"
    ws_meta.views.sheetView[0].showGridLines = True

    meta_rows = [
        ("Key", "Value"),
        ("Schema Version", "1.0"),
        ("Exam Name", exam_a.config.course_name),
        ("Course Title", exam_a.config.title),
        ("Course Code", exam_a.config.course_code),
        ("Total Questions", exam_a.config.total_questions),
        ("Total Options", exam_a.config.num_options),
        ("Total Score", exam_a.config.total_score),
        ("Pass Mark (%)", exam_a.config.pass_mark),
        ("Created Date", now_str),
        ("Random Seed", seed if seed is not None else ""),
        ("Content Hash", content_hash),
    ]

    for r in meta_rows:
        ws_meta.append(list(r))

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")

    for col in (1, 2):
        cell = ws_meta.cell(row=1, column=col)
        cell.font = header_font
        cell.fill = header_fill

    # Helper format sheet set
    def write_set_sheet(sheet_title: str, questions: List[Question]):
        ws = wb.create_sheet(title=sheet_title)
        ws.views.sheetView[0].showGridLines = True
        ws.append(["No", "Question Code", "ATA", "Key"])
        for col in range(1, 5):
            c = ws.cell(row=1, column=col)
            c.font = header_font
            c.fill = header_fill
            c.alignment = Alignment(horizontal="center")

        for q in questions:
            ws.append([q.order_number, q.question_code, q.ata, q.correct_answer])
            # Center alignment untuk No, ATA, Key
            r_idx = ws.max_row
            ws.cell(row=r_idx, column=1).alignment = Alignment(horizontal="center")
            ws.cell(row=r_idx, column=3).alignment = Alignment(horizontal="center")
            ws.cell(row=r_idx, column=4).alignment = Alignment(horizontal="center")

    # Sheet 2: Set A
    write_set_sheet("Set A", exam_a.questions)

    # Sheet 3: Set B
    write_set_sheet("Set B", exam_b.questions)

    # Sheet 4: Bank
    ws_bank = wb.create_sheet(title="Bank")
    ws_bank.views.sheetView[0].showGridLines = True
    ws_bank.append(["Question Code", "ATA", "Question Text"])
    for col in range(1, 4):
        c = ws_bank.cell(row=1, column=col)
        c.font = header_font
        c.fill = header_fill

    # Urutkan bank soal berdasarkan question_code unik
    seen_bank = set()
    for q in exam_a.questions:
        if q.question_code not in seen_bank:
            ws_bank.append([q.question_code, q.ata, q.question_text])
            seen_bank.add(q.question_code)

    wb.save(out_file)
    wb.close()
    return out_file


def load_and_verify_answer_key(file_path: str | Path) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]], List[str]]:
    """
    Membaca kembali file Excel Kunci Jawaban dan memverifikasi integritas hash.
    
    Returns:
        Tuple[meta_dict, sets_dict, warnings_or_errors]
        - meta_dict: isi sheet Meta
        - sets_dict: {"A": {question_code: key, ...}, "B": {question_code: key, ...}}
        - warnings_or_errors: daftar error jika hash tidak cocok atau sheet tidak lengkap.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File Excel kunci tidak ditemukan: {path}")

    wb = openpyxl.load_workbook(path, data_only=True)
    required_sheets = ["Meta", "Set A", "Set B", "Bank"]
    messages: List[str] = []

    for s in required_sheets:
        if s not in wb.sheetnames:
            messages.append(f"Sheet wajib '{s}' tidak ditemukan pada Excel kunci jawaban.")

    if messages:
        wb.close()
        return {}, {}, messages

    # Baca Meta
    meta: Dict[str, Any] = {}
    ws_meta = wb["Meta"]
    for row in ws_meta.iter_rows(values_only=True):
        if row and row[0] is not None:
            meta[str(row[0]).strip()] = row[1] if len(row) > 1 else None

    stored_hash = str(meta.get("Content Hash") or "").strip()
    raw_seed = meta.get("Random Seed")
    seed = int(raw_seed) if raw_seed is not None and str(raw_seed).strip().isdigit() else None
    course_code = str(meta.get("Course Code") or "").strip()

    # Baca Set A
    set_a_dict: Dict[str, str] = {}
    q_list_a: List[Question] = []
    ws_a = wb["Set A"]
    for row in ws_a.iter_rows(min_row=2, values_only=True):
        if row and row[0] is not None:
            no, q_code, ata, key = row[0], str(row[1]).strip(), str(row[2]).strip(), str(row[3]).strip().upper()
            set_a_dict[q_code] = key
            q_list_a.append(Question(question_code=q_code, ata=ata, question_text="", options=[], correct_answer=key, order_number=int(no)))

    # Baca Set B
    set_b_dict: Dict[str, str] = {}
    q_list_b: List[Question] = []
    ws_b = wb["Set B"]
    for row in ws_b.iter_rows(min_row=2, values_only=True):
        if row and row[0] is not None:
            no, q_code, ata, key = row[0], str(row[1]).strip(), str(row[2]).strip(), str(row[3]).strip().upper()
            set_b_dict[q_code] = key
            q_list_b.append(Question(question_code=q_code, ata=ata, question_text="", options=[], correct_answer=key, order_number=int(no)))

    wb.close()

    # Hitung ulang hash
    computed_hash = calculate_key_hash(course_code, q_list_a, q_list_b, seed=seed)
    if stored_hash and computed_hash != stored_hash:
        messages.append(
            "Peringatan Integritas: Hash kunci jawaban tidak cocok! "
            "File Excel kunci kemungkinan telah diedit secara manual setelah dibuat."
        )

    sets = {"A": set_a_dict, "B": set_b_dict}
    return meta, sets, messages
