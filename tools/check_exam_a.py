import sys
from pathlib import Path

# Pastikan root direktori proyek masuk ke sys.path agar 'core' bisa diimpor
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.excel_loader import load_and_validate_exam_excel
from core.scanner import scan_pdf_batch

# Path file target
excel_path = Path("tests/fixtures/Exam Sample A.xlsx")
pdf_path = Path("tests/fixtures/exam A_261124_123544.pdf")

if not excel_path.is_file() or not pdf_path.is_file():
    print("Error: File fixture tidak ditemukan di tests/fixtures/")
    exit(1)

# 1. Baca kunci jawaban dari Excel
exam, _ = load_and_validate_exam_excel(excel_path, set_name="A")
keys = {q.order_number: q.correct_answer for q in exam.questions}

# 2. Pindai PDF lembar jawaban
print("Sedang memindai PDF lembar jawaban...")
batch = scan_pdf_batch(pdf_path, total_questions=32, expected_set="A")

print(f"\nTotal Lembar Dipindai: {batch.total_sheets}\n" + "=" * 45)

# 3. Tampilkan hasil per lembar
for sheet in batch.sheets:
    print(f"\n--- LEMBAR {sheet.sheet_index} ---")
    correct = 0
    wrong_list = []
    
    for q_no in range(1, 33):
        ans = sheet.answers.get(q_no)
        selected = ans.selected_option if ans else None
        k = keys[q_no]
        is_correct = (selected == k)
        
        if is_correct:
            correct += 1
            status_str = "BENAR"
        else:
            wrong_list.append((q_no, selected, k))
            status_str = "SALAH"
            
        print(f"No {q_no:02d} | Kunci: {k} | Terbaca: {selected or '-'} | {status_str}")
    
    score = int((correct / 32) * 100)
    print(f"\n>> Ringkasan Lembar {sheet.sheet_index}:")
    print(f"   Benar : {correct} / 32")
    print(f"   Salah : {len(wrong_list)} / 32")
    print(f"   Skor  : {score}")
    print(f"   Nomor yang Salah: {[w[0] for w in wrong_list]}")
    for w in wrong_list:
        print(f"     - Soal No {w[0]}: Kunci '{w[2]}', terbaca '{w[1]}'")
    print("-" * 45)
