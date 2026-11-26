import argparse
import sys
from pathlib import Path

# Pastikan root direktori proyek masuk ke sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.excel_loader import load_and_validate_exam_excel
from core.shuffler import create_set_b
from core.exam_pdf import generate_exam_pdf
from core.answer_key import generate_answer_key_excel


def main():
    parser = argparse.ArgumentParser(
        description="Tool Pembuat Naskah Soal Ujian (PDF) & Kunci Jawaban (Excel) menggunakan template terbaru."
    )
    parser.add_argument(
        "--input", "-i",
        default=str(ROOT_DIR / "tests" / "fixtures" / "Exam Sample A.xlsx"),
        help="Path ke file Excel bank soal (default: tests/fixtures/Exam Sample A.xlsx)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=str(ROOT_DIR / "output"),
        help="Direktori penyimpanan hasil generate (default: output/)",
    )
    parser.add_argument(
        "--set", "-s",
        choices=["A", "B", "ALL"],
        default="ALL",
        help="Set soal yang ingin dibuat: A, B, atau ALL (A + B + Kunci) (default: ALL)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed untuk pengacakan Set B (opsional, default: acak otomatis)",
    )
    args = parser.parse_args()

    excel_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not excel_path.is_file():
        print(f"Error: File input '{excel_path}' tidak ditemukan!")
        sys.exit(1)

    print("=" * 60)
    print("EXAM GENERATOR TOOL — TEMPLATE RESMI")
    print("=" * 60)
    print(f"1. Membaca file Excel: {excel_path.resolve()}")
    exam_a, warnings = load_and_validate_exam_excel(excel_path, set_name="A")

    if warnings:
        print(f"   Catatan/Peringatan ({len(warnings)}):")
        for w in warnings:
            print(f"   - {w}")

    cfg = exam_a.config
    print(f"\n2. Metadata Ujian:")
    print(f"   - Judul        : {cfg.title}")
    print(f"   - Sub-Judul    : {cfg.course_name}")
    print(f"   - Course Code  : {cfg.course_code}")
    print(f"   - Jumlah Soal  : {len(exam_a.questions)} butir")
    print(f"   - Durasi       : {cfg.duration_minutes} menit")
    print(f"   - Pass Mark    : {cfg.pass_mark}%")
    print(f"   - Form Footer  : {cfg.form_no} | Issue: {cfg.issue} | Year: {cfg.year}")

    def progress_cb(pct, msg):
        print(f"   [{int(pct * 100):3d}%] {msg}")

    print("\n3. Memproses pembuatan dokumen:")

    # Generate Set A
    if args.set in ["A", "ALL"]:
        out_pdf_a = output_dir / f"Exam_{cfg.course_code}_Set_A.pdf"
        print(f"\n>> Menghasilkan PDF Set A -> {out_pdf_a.name}")
        generate_exam_pdf(exam_a, out_pdf_a, progress_callback=progress_cb)
        print(f"   Ukuran: {out_pdf_a.stat().st_size:,} bytes")

    # Generate Set B
    exam_b = None
    seed_used = None
    if args.set in ["B", "ALL"]:
        exam_b, seed_used, shuffle_warns = create_set_b(exam_a, seed=args.seed)
        out_pdf_b = output_dir / f"Exam_{cfg.course_code}_Set_B.pdf"
        print(f"\n>> Menghasilkan PDF Set B (Seed: {seed_used}) -> {out_pdf_b.name}")
        generate_exam_pdf(exam_b, out_pdf_b, progress_callback=progress_cb)
        print(f"   Ukuran: {out_pdf_b.stat().st_size:,} bytes")

    # Generate Kunci Jawaban Excel jika ALL
    if args.set == "ALL" and exam_b:
        out_key = output_dir / f"Kunci_Jawaban_{cfg.course_code}.xlsx"
        print(f"\n>> Menghasilkan Excel Kunci Jawaban (4-Sheet + Hash) -> {out_key.name}")
        generate_answer_key_excel(exam_a, exam_b, out_key, seed=seed_used)
        print(f"   Ukuran: {out_key.stat().st_size:,} bytes")

    print("\n" + "=" * 60)
    print("SELESAI! Seluruh file berhasil disimpan di:")
    print(f"-> {output_dir.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
