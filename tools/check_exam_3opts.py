import argparse
import csv
import sys
from pathlib import Path

# Pastikan root direktori proyek masuk ke sys.path agar 'core' bisa diimpor
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.scanner import scan_pdf_batch


def main():
    parser = argparse.ArgumentParser(
        description="Tool Pengecekan Lembar Jawaban Ujian 3 Opsi (OMR)."
    )
    parser.add_argument(
        "--pdf", "-p",
        default=str(ROOT_DIR / "tests" / "fixtures" / "answer sheet and result_exam 4.pdf"),
        help="Path ke file PDF lembar jawaban scan (default: tests/fixtures/answer sheet and result_exam 4.pdf)",
    )
    parser.add_argument(
        "--gt", "-g",
        default=str(ROOT_DIR / "tests" / "fixtures" / "ground_truth_3opsi.csv"),
        help="Path ke file CSV ground truth (default: tests/fixtures/ground_truth_3opsi.csv)",
    )
    parser.add_argument(
        "--questions", "-q",
        type=int,
        default=12,
        help="Jumlah soal yang dievaluasi (default: 12)",
    )
    parser.add_argument(
        "--sheet", "-s",
        type=int,
        default=None,
        help="Cek nomor lembar tertentu secara detail (1..N) (opsional)",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    gt_path = Path(args.gt)

    if not pdf_path.is_file():
        print(f"Error: File PDF '{pdf_path}' tidak ditemukan.")
        sys.exit(1)

    gt_data = {}
    if gt_path.is_file():
        with open(gt_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                halaman = int(row["halaman"])
                gt_data[halaman] = {
                    "set": row["set"],
                    "jumlah_soal": int(row["jumlah_soal"]),
                    "jumlah_salah": int(row["jumlah_salah"]),
                    "nilai_tulisan_tangan": int(row.get("nilai_tulisan_tangan", 0)),
                }

    print("=" * 70)
    print("TOOL PENGECEKAN EXAM 3 OPSI (OMR SCANNER)")
    print("=" * 70)
    print(f"File PDF  : {pdf_path.resolve()}")
    if gt_data:
        print(f"Data GT   : {gt_path.resolve()} ({len(gt_data)} lembar)")
    print(f"Total Soal: {args.questions} nomor")

    def progress_cb(pct, msg):
        print(f"[{int(pct * 100):3d}%] {msg}")

    print("\n1. Memindai lembar jawaban PDF...")
    batch = scan_pdf_batch(
        pdf_path,
        total_questions=args.questions,
        progress_callback=progress_cb,
    )

    total_sheets = batch.total_sheets
    print(f"\nTotal Lembar Berhasil Dipindai: {total_sheets}")

    # Ekstraksi jawaban per lembar
    sheet_answers = {}
    for sheet in batch.sheets:
        sheet_answers[sheet.sheet_index] = {
            q: sheet.answers[q].selected_option for q in range(1, args.questions + 1)
        }

    # Cari kunci jawaban referensi:
    # Set A S=0: Lembar 2
    # Set B S=0: Lembar 14
    key_a = sheet_answers.get(2)
    key_b = sheet_answers.get(14)

    print("\n2. Kunci Jawaban Referensi (Berdasarkan Lembar S=0):")
    if key_a:
        print(f"   - Set A: {key_a}")
    if key_b:
        print(f"   - Set B: {key_b}")

    print("\n3. Ringkasan Evaluasi Seluruh Lembar:")
    print("-" * 75)
    print(f"{'Hal':<4} | {'Set':<4} | {'Benar':<6} | {'Salah (OMR)':<11} | {'Salah (GT)':<10} | {'Status':<7} | {'Keterangan':<15}")
    print("-" * 75)

    all_matched = True
    mismatch_count = 0

    for sheet in batch.sheets:
        idx = sheet.sheet_index
        gt_info = gt_data.get(idx)
        current_set = gt_info["set"] if gt_info else (sheet.detected_set if sheet.detected_set != "?" else "A")
        ref_key = key_a if current_set == "A" else key_b

        if ref_key:
            wrong_list = [
                q for q in range(1, args.questions + 1)
                if sheet_answers[idx].get(q) != ref_key.get(q)
            ]
            actual_wrong = len(wrong_list)
            actual_correct = args.questions - actual_wrong
        else:
            actual_wrong = 0
            actual_correct = args.questions
            wrong_list = []

        if gt_info:
            expected_wrong = gt_info["jumlah_salah"]
            is_match = (actual_wrong == expected_wrong)
            match_status = "MATCH" if is_match else "MISMATCH"
            gt_wrong_str = str(expected_wrong)
            if not is_match:
                all_matched = False
                mismatch_count += 1
        else:
            match_status = "-"
            gt_wrong_str = "-"

        notes = []
        if sheet.needs_review:
            notes.append("Perlu Review")
        if wrong_list:
            notes.append(f"Salah di {wrong_list}")
        notes_str = "; ".join(notes) if notes else "Sempurna"

        print(f"{idx:<4} | {current_set:<4} | {actual_correct:<6} | {actual_wrong:<11} | {gt_wrong_str:<10} | {match_status:<7} | {notes_str}")

    print("-" * 75)
    if gt_data:
        if all_matched:
            print(f">> HASIL: SEMUA LEMBAR COCOK 100% ({total_sheets}/{total_sheets} MATCH)")
        else:
            print(f">> HASIL: TERDAPAT {mismatch_count} LEMBAR MISMATCH!")

    # Detail lembar spesifik jika diminta
    if args.sheet:
        target_sheet = next((s for s in batch.sheets if s.sheet_index == args.sheet), None)
        if target_sheet:
            print("\n" + "=" * 50)
            print(f"DETAIL LEMBAR KE-{args.sheet}")
            print("=" * 50)
            gt_info = gt_data.get(args.sheet)
            current_set = gt_info["set"] if gt_info else "A"
            ref_key = key_a if current_set == "A" else key_b
            print(f"Set Ujian       : {current_set}")
            print(f"Status Review   : {'PERLU REVIEW' if target_sheet.needs_review else 'OK'}")
            if target_sheet.warnings:
                print("Pesan Peringatan:")
                for w in target_sheet.warnings:
                    print(f"  - {w}")

            print("\nRincian Jawaban Soal:")
            for q in range(1, args.questions + 1):
                ans_obj = target_sheet.answers.get(q)
                terbaca = ans_obj.selected_option if ans_obj else "-"
                kunci = ref_key.get(q, "-") if ref_key else "-"
                status_jawaban = "BENAR" if terbaca == kunci else "SALAH"
                print(f"No {q:02d} | Kunci: {kunci} | Terbaca: {terbaca} | Status: {status_jawaban}")


if __name__ == "__main__":
    main()
