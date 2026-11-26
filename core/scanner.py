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
from .form_profile import build_default_form_profile, detect_form_variant, FormProfile


# Cache profil form default untuk 3 opsi dan 4 opsi
_DEFAULT_PROFILES: Dict[int, FormProfile] = {
    3: build_default_form_profile(num_options=3),
    4: build_default_form_profile(num_options=4),
}


def read_exam_code(
    gray_img: np.ndarray,
    exam_boxes: Optional[Dict[str, Dict[str, int]]] = None,
) -> Tuple[str, List[str]]:
    """
    Membaca kode exam (A/B/R) dan mendeteksi bekas hapusan tipis.
    Mendukung koordinat kotak dari FormProfile (3 opsi vs 4 opsi).
    
    Returns:
        Tuple[str, List[str]]: Huruf kode exam yang dipilih dan daftar pesan peringatan.
    """
    warnings: List[str] = []
    box_scores: Dict[str, Tuple[float, int]] = {}

    boxes = exam_boxes or {
        "A": {"x": 202, "y": 125, "w": 14, "h": 14},
        "B": {"x": 218, "y": 125, "w": 14, "h": 14},
        "R": {"x": 235, "y": 125, "w": 14, "h": 14},
    }

    for label, b in boxes.items():
        bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]
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
    profile: Optional[FormProfile] = None,
) -> SheetScanResult:
    """
    Memproses satu lembar gambar scan:
    - Meluruskan halaman
    - Menggunakan profil form (3 opsi vs 4 opsi dari hasil kalibrasi)
    - Mengukur tinta pada setiap opsi dengan ambang adaptif per lembar
    - Melakukan sanity check (semua jawaban identik atau lembar kosong)
    - Mengklasifikasikan status jawaban
    - Menyimpan potongan gambar jika status perlu_review
    """
    warped, align_warnings = align_form_page(img_bgr)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    num_options = detect_form_variant(warped)
    current_profile = profile or _DEFAULT_PROFILES.get(num_options, _DEFAULT_PROFILES[4])

    # Baca Exam Code menggunakan profil yang sesuai
    detected_set, code_warnings = read_exam_code(gray, current_profile.exam_code_boxes)
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
    # Threshold adaptif relatif terhadap background kertas
    dark_threshold = paper_mean - 35.0

    answers: Dict[int, QuestionAnswerResult] = {}
    sheet_needs_review = False

    for q in range(1, total_questions + 1):
        q_str = str(q)
        if q_str not in current_profile.answer_grid:
            break

        opts_map = current_profile.answer_grid[q_str]
        opt_scores: Dict[str, float] = {}
        opt_dps: Dict[str, int] = {}

        for opt_letter, b in opts_map.items():
            bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]
            crop = gray[by:by+bh, bx:bx+bw]
            dp = int(np.sum(crop < dark_threshold))
            mean_darkness = float(255.0 - np.mean(crop))
            # Skor gabungan: darkness + 1.5 * dp
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
            selected_option = top1  # opsi paling tebal tapi ditandai ganda
        else:
            status = "jelas"
            selected_option = top1

        crop_path_str = None
        if needs_review:
            sheet_needs_review = True
            if review_output_dir:
                review_output_dir.mkdir(parents=True, exist_ok=True)
                # Potong seluruh area nomor soal (semua opsi A-C/D)
                all_xs = [b["x"] for b in opts_map.values()]
                all_ys = [b["y"] for b in opts_map.values()]
                min_x = max(0, min(all_xs) - 15)
                max_x = min(CANONICAL_WIDTH, max(all_xs) + 30)
                min_y = max(0, min(all_ys) - 5)
                max_y = min(CANONICAL_HEIGHT, max(all_ys) + 20)
                q_crop = warped[min_y:max_y, min_x:max_x]
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

    # Sanity checks per lembar:
    valid_answers = [ans.selected_option for ans in answers.values() if ans.selected_option is not None]
    total_evaluated = len(answers)

    # 1. Sanity check: sebagian besar kotak kosong / tidak berubah
    if total_evaluated >= 5 and len(valid_answers) <= total_evaluated * 0.1:
        sheet_needs_review = True
        warnings.append(
            f"Peringatan Lembar {sheet_index}: Sebagian besar kotak jawaban kosong atau tidak terisi "
            f"({len(valid_answers)}/{total_evaluated} terisi). Perlu review manual."
        )

    # 2. Sanity check: semua jawaban yang terisi seragam/identik
    if len(valid_answers) >= 5:
        from collections import Counter
        counts = Counter(valid_answers)
        most_common_opt, most_common_count = counts.most_common(1)[0]
        if most_common_count >= len(valid_answers) * 0.95:
            sheet_needs_review = True
            warnings.append(
                f"Peringatan Lembar {sheet_index}: Jawaban peserta sangat seragam "
                f"('{most_common_opt}' sebanyak {most_common_count}/{len(valid_answers)}). Perlu review manual."
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
