# Exam Generator — Backend Engine (`core/`)

Aplikasi desktop offline untuk pembuatan naskah ujian tertulis dan analisis hasil lembar jawaban (OMR) berbasis Python 3.15.

---

## 1. Arsitektur & Gambaran Umum

Proyek ini terdiri dari dua fitur utama yang terhubung melalui file **Excel Kunci Jawaban**:

```
[Bank Soal Excel] 
        │
        ▼ (Fitur 1)
┌─────────────────────────────────────────┐
│ • Exam A PDF (Urutan asli per ATA)      │
│ • Exam B PDF (Diacak di dalam tiap ATA) │
│ • Excel Kunci Jawaban (4-Sheet + Hash)  │
└─────────────────────────────────────────┘
        │
        ▼ (Fitur 2)
┌─────────────────────────────────────────┐
│ • Pemindaian OMR Lembar Jawaban (PDF)   │
│ • Penilaian Skor (Floor Rounding)       │
│ • Analisis Butir Soal & Highlight       │
│ • Laporan Analisis Ujian (PDF)          │
└─────────────────────────────────────────┘
```

Seluruh logika inti berada pada package `core/` tanpa ketergantungan pada GUI atau pencetakan langsung (`print`). Modul ini siap dihubungkan ke GUI (seperti `customtkinter`) di tahap pengembangan selanjutnya.

---

## 2. Struktur Modul `core/`

| Modul | Deskripsi |
|---|---|
| `core/models.py` | Definisi struktur data dataclass (`Exam`, `Question`, `ExamConfig`, `SheetScanResult`, `ExamAnalysisReport`, dll.). |
| `core/excel_loader.py` | Pembacaan dan validasi lengkap format Excel bank soal (Config, Questions). |
| `core/shuffler.py` | Pengacakan soal Set B per ATA secara deterministik menggunakan random seed. |
| `core/exam_pdf.py` | Generator PDF soal (Set A / B / R): sampul + petunjuk + tabel identitas, header, judul ATA, dan footer resmi. Tampilan mengikuti `legacy/exam_pdf_original.py`. |
| `core/answer_key.py` | Pembuat dan pembaca Excel Kunci Jawaban 4-sheet (`Meta`, `Set A`, `Set B`, `Bank`) beserta deteksi manipulasi via SHA-256 hash. |
| `core/scanner_align.py` | Pendeteksi 4 penanda sudut hitam dan penanda orientasi untuk meluruskan halaman scan (perspective warp). |
| `core/form_profile.py` | Definisi tata letak koordinat kanonikal kisi form (3 opsi vs 4 opsi) dan deteksi otomatis varian form. |
| `core/scanner.py` | Mesin OMR utama dengan ambang batas adaptif per lembar, evaluasi status jawaban (`jelas`, `kosong`, `ganda`, `samar`), deteksi exam code, serta crop gambar untuk jawaban yang `perlu_review`. |
| `core/analyzer.py` | Mesin kalkulasi skor lembar jawaban (dibulatkan ke bawah) dan analisis persentase keberhasilan per Question Code (Set A, Set B, Gabungan) beserta penandaan highlight. |
| `core/report_pdf.py` | Generator PDF Laporan Analisis Ujian resmi dengan ringkasan statistik, tabel analisis berwarna, dan daftar evaluasi butir soal (tanpa nama/ID peserta). |

---

## 3. Panduan Penggunaan API

### A. Fitur 1: Membuat Naskah Soal & Kunci Jawaban

```python
from pathlib import Path
from core import (
    load_and_validate_exam_excel,
    create_set_b,
    generate_exam_pdf,
    generate_answer_key_excel,
)

# 1. Baca dan validasi file Excel bank soal
excel_path = Path("bank_soal.xlsx")
exam_a, warnings = load_and_validate_exam_excel(excel_path, set_name="A")

# 2. Hasilkan Set B (diacak di dalam tiap ATA)
exam_b, seed_used, warnings_b = create_set_b(exam_a, seed=42)

# 3. Cetak PDF naskah soal Set A dan Set B
generate_exam_pdf(exam_a, "Naskah_Exam_A.pdf")
generate_exam_pdf(exam_b, "Naskah_Exam_B.pdf")

# 4. Buat file Excel Kunci Jawaban (rahasia)
key_file_path = generate_answer_key_excel(exam_a, exam_b, "Kunci_Jawaban.xlsx", seed=seed_used)
```

---

### B. Fitur 2: Memindai Lembar Jawaban & Menganalisis Hasil

```python
from pathlib import Path
from core import (
    scan_pdf_batch,
    analyze_exam_results,
    generate_analysis_report_pdf,
)

# 1. Pindai batch file PDF scan lembar jawaban
batch_a = scan_pdf_batch("scan_jawaban_set_a.pdf", total_questions=32, expected_set="A")
batch_b = scan_pdf_batch("scan_jawaban_set_b.pdf", total_questions=32, expected_set="B")

# Catatan: Jika ada lembar yang berstatus 'needs_review', selesaikan verifikasi
# sebelum menjalankan analisis.

# 2. Analisis skor dan performa soal
report = analyze_exam_results(
    exam_a=exam_a,
    exam_b=exam_b,
    sheets_a=batch_a.sheets,
    sheets_b=batch_b.sheets,
)

# 3. Cetak PDF Laporan Analisis Ujian
generate_analysis_report_pdf(report, "Laporan_Analisis_Ujian.pdf")
```

---

## 4. Aturan Bisnis & Prinsip Penting

1. **Ambang Adaptif per Lembar**: Scanner OMR tidak menggunakan threshold hitam absolut, melainkan mengukur latar kertas setiap halaman untuk mengatasi perbedaan tingkat kecerahan scan.
2. **Prinsip Anti-Tebak**: Jika tanda jawaban ambigu atau samar, sistem menandai `needs_review = True` dan menyimpan potongan gambarnya. Sistem tidak boleh menebak diam-diam.
3. **Pembulatan Skor**: Skor dihitung dengan $\lfloor (\text{benar} / \text{total}) \times 100 \rfloor$ (dibulatkan ke bawah ke bilangan bulat terdekat).
4. **Highlight Butir Soal**:
   - `> 90.0%`: *Terlalu Mudah* (ditandai latar hijau muda).
   - `< 50.0%`: *Terlalu Sulit / Periksa Soal* (ditandai latar merah muda).
   - Nilai tepat $90.0\%$ dan $50.0\%$ **tidak** ditandai.
5. **Privasi Laporan**: Laporan PDF hasil analisis tidak memuat nama atau ID peserta.

---

## 5. Menjalankan Pengujian

Jalankan perintah berikut di PowerShell atau Command Prompt dalam virtual environment:

```powershell
.\.venv\Scripts\pytest tests/ -v
```

Untuk menjalankan pengujian benchmark beserta output waktunya:

```powershell
.\.venv\Scripts\pytest tests/test_fase6.py -v -s
```
