import argparse
import sys
from pathlib import Path
import cv2
import numpy as np
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
import pypdfium2 as pdfium

# Pastikan root direktori proyek masuk ke sys.path agar 'core' bisa diimpor
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.excel_loader import load_and_validate_exam_excel
from core.scanner import scan_pdf_batch
from core.scanner_align import align_form_page


# Koordinat baris digit 0-9 dan kolom Date / ID Number (kolom kanan)
ROW_DIGITS = [451, 481, 511, 540, 569, 599, 628, 658, 688, 717]
DATE_COLS = [462, 489, 517, 546, 574, 602]
ID_NUMBER_COLS = [911, 939, 967, 995, 1023, 1051]  # Kolom kanan atas (ID Number peserta)


def read_digits_from_image(gray_img: np.ndarray, cols: list[int], y_rows: list[int]) -> str:
    """Membaca rangkaian digit dari grid bulatan angka OMR."""
    res = []
    for c in cols:
        vals = [float(255.0 - np.mean(gray_img[y-6:y+7, c-6:c+7])) for y in y_rows]
        top = int(np.argmax(vals))
        res.append(str(top) if vals[top] >= 10.0 else "?")
    return "".join(res)


def main():
    parser = argparse.ArgumentParser(
        description="Tool Pengecekan Lembar Jawaban Ujian 4 Opsi (Exam A) dan Export XLSX."
    )
    parser.add_argument(
        "--excel", "-e",
        default=str(ROOT_DIR / "tests" / "fixtures" / "Exam Sample A.xlsx"),
        help="Path ke file Excel bank soal (default: tests/fixtures/Exam Sample A.xlsx)",
    )
    parser.add_argument(
        "--pdf", "-p",
        default=str(ROOT_DIR / "tests" / "fixtures" / "exam A_261124_123544.pdf"),
        help="Path ke file PDF lembar jawaban (default: tests/fixtures/exam A_261124_123544.pdf)",
    )
    parser.add_argument(
        "--output", "-o",
        default=str(ROOT_DIR / "output" / "check_exam_a_results.xlsx"),
        help="Path file output Excel .xlsx (default: output/check_exam_a_results.xlsx)",
    )
    args = parser.parse_args()

    excel_path = Path(args.excel)
    pdf_path = Path(args.pdf)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not excel_path.is_file() or not pdf_path.is_file():
        print("Error: File input tidak ditemukan.")
        sys.exit(1)

    # 1. Baca kunci jawaban dan Course Code dari Excel
    exam, _ = load_and_validate_exam_excel(excel_path, set_name="A")
    keys = {q.order_number: q.correct_answer for q in exam.questions}
    question_codes = {q.order_number: q.question_code for q in exam.questions}
    course_code = exam.config.course_code
    total_q = len(exam.questions)

    # 2. Pindai PDF lembar jawaban
    print("=" * 80)
    print("TOOL PENGECEKAN EXAM 4 OPSI (EXAM A)")
    print("=" * 80)
    print(f"File PDF   : {pdf_path.resolve()}")
    print(f"File Excel : {excel_path.resolve()}")
    print(f"Course Code: {course_code}")
    print(f"Total Soal : {total_q} butir")

    print("\nMemindai PDF lembar jawaban...")
    batch = scan_pdf_batch(pdf_path, total_questions=total_q, expected_set="A")
    doc = pdfium.PdfDocument(pdf_path)

    # 3. Ekstraksi data baris tabel
    results = []
    print("\n" + "=" * 105)
    header_title = f"{'ID':<8} || {'Tanggal':<8} || {'Course Code':<13} || {'Exam':<4} || "
    q_preview = f"Q1-Q{total_q} (1/0)"
    header_title += f"{q_preview:<35} || {'Nilai':<7}"
    print(header_title)
    print("=" * 105)

    for idx, sheet in enumerate(batch.sheets):
        # Baca ID (dari grid kolom kanan) & Tanggal dari gambar
        pil_img = doc[idx].render(scale=2.0).to_pil()
        bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        warped, _ = align_form_page(bgr)
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

        trainee_id = read_digits_from_image(gray, ID_NUMBER_COLS, ROW_DIGITS)
        exam_date = read_digits_from_image(gray, DATE_COLS, ROW_DIGITS)
        exam_code = sheet.detected_set if sheet.detected_set != "?" else "A"

        q_scores = []
        correct_count = 0
        for q_no in range(1, total_q + 1):
            ans_obj = sheet.answers.get(q_no)
            selected = ans_obj.selected_option if ans_obj else None
            is_correct = 1 if (selected == keys.get(q_no)) else 0
            if is_correct:
                correct_count += 1
            q_scores.append(is_correct)

        score_val = (correct_count / total_q) * 100.0
        score_str = f"{score_val:.2f}"

        q_str_preview = "".join(str(s) for s in q_scores[:32])
        if total_q > 32:
            q_str_preview += "..."

        print(f"{trainee_id:<8} || {exam_date:<8} || {course_code:<13} || {exam_code:<4} || {q_str_preview:<35} || {score_str:>7}")

        results.append({
            "id": trainee_id,
            "date": exam_date,
            "course_code": course_code,
            "exam_code": exam_code,
            "q_scores": q_scores,
            "score": score_val,
        })

    print("=" * 105)

    # 4. Simpan ke Excel (.xlsx) dengan header 2 baris (digabung vertikal di Kolom A-D dan Nilai)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hasil Pengecekan Exam A"

    total_cols = 4 + total_q + 1  # A-D (4) + Soal (total_q) + Nilai (1)

    # Susun Baris 1: Kolom Soal berisi Question Code
    row1 = ["ID", "Tanggal", "Course Code", "Exam Code"]
    for q in range(1, total_q + 1):
        row1.append(question_codes.get(q, q))
    row1.append("Nilai")
    ws.append(row1)

    # Susun Baris 2: Kolom Soal berisi Q1, Q2, ..., Qn
    row2 = ["", "", "", ""]
    for q in range(1, total_q + 1):
        row2.append(f"Q{q}")
    row2.append("")
    ws.append(row2)

    # Format styling header
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    # Terapkan styling ke seluruh cell baris 1 & 2
    for r in (1, 2):
        for c in range(1, total_cols + 1):
            cell = ws.cell(row=r, column=c)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border

    # Gabung (merge) kolom A, B, C, D dan kolom Nilai (baris 1 & 2)
    ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=1)  # ID
    ws.merge_cells(start_row=1, start_column=2, end_row=2, end_column=2)  # Tanggal
    ws.merge_cells(start_row=1, start_column=3, end_row=2, end_column=3)  # Course Code
    ws.merge_cells(start_row=1, start_column=4, end_row=2, end_column=4)  # Exam Code
    ws.merge_cells(start_row=1, start_column=total_cols, end_row=2, end_column=total_cols)  # Nilai

    # Isi data baris (mulai baris 3)
    for r_idx, res in enumerate(results, start=3):
        row_vals = [
            res["id"],
            res["date"],
            res["course_code"],
            res["exam_code"],
        ]
        row_vals.extend(res["q_scores"])
        row_vals.append(round(res["score"], 2))
        ws.append(row_vals)

        # Styling baris data
        for c_idx in range(1, total_cols + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center", vertical="center")
            if c_idx == total_cols:
                cell.number_format = "0.00"

    # Sesuaikan lebar kolom
    for col in ws.columns:
        col_letter = col[0].column_letter
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 6)

    wb.save(output_path)
    print(f"\n>> Hasil berhasil diekspor ke file Excel: {output_path.resolve()}\n")


if __name__ == "__main__":
    main()
