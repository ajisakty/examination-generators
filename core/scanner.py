"""
Modul Scanner Lembar Jawaban Ujian (OMR).
Membaca PDF scan berisi banyak lembar jawaban untuk satu set (A atau B).
Menggunakan ambang adaptif per lembar (tidak menggunakan angka tetap).
Prinsip: Ragu = tandai 'perlu_review' dan simpan crop gambar (tidak menebak diam-diam).
Backend murni tanpa GUI atau print langsung, mendukung progress_callback.
"""

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image

from .models import QuestionAnswerResult, SheetScanResult, ScannerBatchResult
from .scanner_align import align_form_page, CANONICAL_WIDTH, CANONICAL_HEIGHT
from .form_profile import detect_form_variant


# Tata letak kanonikal kisi jawaban resmi (4 Blok x 25 Baris)
# Koordinat ini adalah nilai Y-center dari baris bubble setelah warp ke kanonikal 1200x1700
ROW_Y = [
    802, 831, 861, 891, 920,
    949, 979, 1009, 1042, 1068,
    1098, 1131, 1158, 1188, 1220,
    1247, 1278, 1310, 1335, 1370,
    1397, 1423, 1457, 1484, 1515
]

COL_OFFSETS_4 = [
    [341, 368, 396, 425],  # Blok 1 (No. 1 - 25)
    [539, 567, 596, 626],  # Blok 2 (No. 26 - 50)
    [736, 764, 794, 823],  # Blok 3 (No. 51 - 75)
    [933, 961, 991, 1020]  # Blok 4 (No. 76 - 100)
]

COL_OFFSETS_3 = [
    [341, 368, 396],
    [539, 567, 596],
    [736, 764, 794],
    [933, 961, 991]
]

# Koordinat kotak Exam Code (A, B, R) pada gambar kanonikal
# Kotak berisi silang peserta untuk memilih set ujian (A/B/R)
EXAM_CODE_BOXES = {
    "A": (202, 125, 14, 14),
    "B": (218, 125, 14, 14),
    "R": (235, 125, 14, 14),
}


def read_exam_code(gray_img: np.ndarray) -> Tuple[str, List[str]]:
    """
    Membaca kode exam (A/B/R) dan mendeteksi bekas hapusan tipis.
    
    Returns:
        Tuple[str, List[str]]: Huruf kode exam yang dipilih dan daftar pesan peringatan.
    """
    warnings: List[str] = []
    box_scores: Dict[str, Tuple[float, int]] = {}

    for label, (bx, by, bw, bh) in EXAM_CODE_BOXES.items():
        crop = gray_img[by:by+bh, bx:bx+bw]
        dp = int(np.sum(crop < 130))
        mean_dark = float(255.0 - np.mean(crop))
        box_scores[label] = (mean_dark, dp)

    # Urutkan berdasarkan dark_pixels tertinggi
    sorted_codes = sorted(box_scores.keys(), key=lambda k: box_scores[k][1], reverse=True)
    best_code = sorted_codes[0]
    best_dp = box_scores[best_code][1]

    # Cek tanda aktif (dp >= 45)
    detected_code = best_code if best_dp >= 45 else "?"

    # Cek bekas hapusan tipis di kotak lain (dp antara 18 dan 45)
    for code, (mean_d, dp) in box_scores.items():
        if code != detected_code and 18 <= dp < best_dp:
            warnings.append(
                f"Peringatan: Terdeteksi bekas tanda tipis/terhapus di kotak kode exam {code} "
                f"(kode aktif terdeteksi: {detected_code})."
            )

    return detected_code, warnings


def scan_single_sheet(
    img_bgr: np.ndarray,
    sheet_index: int,
    total_questions: int = 100,
    expected_set: Optional[str] = None,
    review_output_dir: Optional[Path] = None,
) -> SheetScanResult:
    """
    Memproses satu lembar gambar scan:
    - Meluruskan halaman
    - Mengukur tinta pada setiap opsi dengan ambang adaptif per lembar
    - Mengklasifikasikan status jawaban
    - Menyimpan potongan gambar jika status perlu_review
    """
    warped, align_warnings = align_form_page(img_bgr)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    num_options = detect_form_variant(warped)
    col_offsets = COL_OFFSETS_4 if num_options == 4 else COL_OFFSETS_3
    option_letters = ["A", "B", "C", "D"] if num_options == 4 else ["A", "B", "C"]

    # Baca Exam Code
    detected_set, code_warnings = read_exam_code(gray)
    warnings = list(align_warnings) + list(code_warnings)

    if expected_set and detected_set != "?" and detected_set != expected_set:
        warnings.append(
            f"Peringatan Lembar {sheet_index}: Kode exam terdeteksi '{detected_set}', "
            f"berbeda dari set yang dipilih pengguna ('{expected_set}')."
        )

    # Ambang adaptif per lembar (mengukur mean background kertas)
    # Latar kertas diambil dari sampling margin kosong (y: 200..300, x: 200..300)
    paper_sample = gray[200:300, 200:300]
    paper_mean = float(np.mean(paper_sample))
    # Threshold adaptif: lembar gelap/kotor menyesuaikan ambang batas
    dark_threshold = 140 if paper_mean > 240 else 130

    answers: Dict[int, QuestionAnswerResult] = {}
    sheet_needs_review = False

    for q in range(1, total_questions + 1):
        col_idx = (q - 1) // 25
        r_idx = (q - 1) % 25
        if col_idx >= len(col_offsets):
            break

        cy = ROW_Y[r_idx]
        cols = col_offsets[col_idx]

        opt_scores: Dict[str, float] = {}
        opt_dps: Dict[str, int] = {}

        for opt_idx, opt_letter in enumerate(option_letters):
            cx = cols[opt_idx]
            crop = gray[cy-7:cy+8, cx-7:cx+8]
            dp = int(np.sum(crop < dark_threshold))
            mean_darkness = float(255.0 - np.mean(crop))
            # Skor gabungan: mean_darkness + 1.5 * dp
            score = mean_darkness + 1.5 * dp
            opt_scores[opt_letter] = score
            opt_dps[opt_letter] = dp

        # Evaluasi opsi
        sorted_opts = sorted(opt_scores.keys(), key=lambda k: opt_scores[k], reverse=True)
        top1 = sorted_opts[0]
        top2 = sorted_opts[1] if len(sorted_opts) > 1 else None

        score1 = opt_scores[top1]
        score2 = opt_scores[top2] if top2 else 0.0

        # Kategori status jawaban:
        # Ambang tanda aktif adaptif: score1 >= 8.0
        # Ganda: score2 cukup dekat dengan score1 (misal score2 >= 15.0 dan score2 >= 0.7 * score1)
        # Samar: score1 di ambang batas ragu (misal 5.0 <= score1 < 8.0)
        # Kosong: score1 < 5.0
        # Jelas: score1 >= 8.0 dan score2 jauh di bawah (score2 < 0.6 * score1 atau score2 < 12.0)

        selected_option: Optional[str] = None
        status: str = "jelas"
        needs_review: bool = False

        if score1 < 5.0:
            status = "kosong"
            selected_option = None
        elif 5.0 <= score1 < 8.0:
            status = "samar"
            needs_review = True
            selected_option = top1
        elif top2 and score2 >= 15.0 and score2 >= 0.65 * score1:
            status = "ganda"
            needs_review = True
            selected_option = top1 # opsi paling tebal tapi ditandai ganda
        else:
            status = "jelas"
            selected_option = top1

        crop_path_str = None
        if needs_review:
            sheet_needs_review = True
            if review_output_dir:
                review_output_dir.mkdir(parents=True, exist_ok=True)
                # Potong seluruh area nomor soal (semua opsi A-D)
                x_start = cols[0] - 15
                x_end = cols[-1] + 15
                q_crop = warped[cy-12:cy+13, x_start:x_end]
                crop_file = review_output_dir / f"sheet_{sheet_index}_q{q}.png"
                cv2.imwrite(str(crop_file), q_crop)
                crop_path_str = str(crop_file)

        answers[q] = QuestionAnswerResult(
            question_number=q,
            selected_option=selected_option,
            status=status,
            needs_review=needs_review,
            scores=opt_scores,
            crop_image_path=crop_path_str,
        )

    return SheetScanResult(
        sheet_index=sheet_index,
        detected_set=detected_set,
        answers=answers,
        warnings=warnings,
        needs_review=sheet_needs_review,
    )


def scan_pdf_batch(
    pdf_path: str | Path,
    total_questions: int = 32,
    expected_set: Optional[str] = None,
    review_output_dir: Optional[str | Path] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> ScannerBatchResult:
    """
    Memproses file PDF scan gabungan berisi banyak lembar jawaban.
    
    Args:
        pdf_path: Lokasi file PDF scan.
        total_questions: Jumlah nomor soal yang akan dievaluasi (default 32).
        expected_set: "A" atau "B" (opsional, untuk validasi kesesuaian set).
        review_output_dir: Direktori untuk menyimpan potongan gambar "perlu_review".
        progress_callback: Fungsi callback progres (persen: 0.0 - 1.0, pesan: str).
        
    Returns:
        ScannerBatchResult: Hasil pemindaian batch lengkap.
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"File PDF scan tidak ditemukan: {path}")

    review_dir = Path(review_output_dir) if review_output_dir else None

    doc = pdfium.PdfDocument(path)
    total_sheets = len(doc)
    sheets_result: List[SheetScanResult] = []
    total_reviews = 0

    if progress_callback:
        progress_callback(0.05, f"Membuka file PDF ({total_sheets} halaman)...")

    for p_idx in range(total_sheets):
        if progress_callback:
            pct = 0.05 + 0.9 * (p_idx / total_sheets)
            progress_callback(pct, f"Memindai lembar ke-{p_idx+1} dari {total_sheets}...")

        # Render halaman ke gambar scale 2.0 (~150-200 DPI)
        pil_img = doc[p_idx].render(scale=2.0).to_pil()
        bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        sheet_res = scan_single_sheet(
            img_bgr=bgr,
            sheet_index=p_idx + 1,
            total_questions=total_questions,
            expected_set=expected_set,
            review_output_dir=review_dir,
        )

        if sheet_res.needs_review:
            total_reviews += 1

        sheets_result.append(sheet_res)

    if progress_callback:
        progress_callback(1.0, f"Selesai memindai {total_sheets} lembar.")

    return ScannerBatchResult(
        pdf_path=str(path),
        total_sheets=total_sheets,
        sheets=sheets_result,
        review_count=total_reviews,
    )
