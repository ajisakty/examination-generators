from pathlib import Path
import pytest
import cv2
import numpy as np
import pypdfium2 as pdfium

from core.scanner_align import align_form_page, find_markers, CANONICAL_WIDTH, CANONICAL_HEIGHT
from core.form_profile import (
    build_default_form_profile,
    detect_form_variant,
    render_profile_overlay,
    FormProfile,
)


def test_form_profile_box_counts():
    """
    Sesuai PLAN.md Bagian 7 (Fase 3):
    Jumlah total kotak area jawaban harus tepat 300 untuk 3 opsi,
    dan tepat 400 untuk 4 opsi.
    """
    prof3 = build_default_form_profile(num_options=3)
    prof4 = build_default_form_profile(num_options=4)

    assert len(prof3.answer_grid) == 100
    assert len(prof4.answer_grid) == 100

    # Hitung total kotak di seluruh 100 nomor
    total_boxes_3 = sum(len(opts) for opts in prof3.answer_grid.values())
    total_boxes_4 = sum(len(opts) for opts in prof4.answer_grid.values())

    assert total_boxes_3 == 300, f"Expected 300 boxes for 3-options, got {total_boxes_3}"
    assert total_boxes_4 == 400, f"Expected 400 boxes for 4-options, got {total_boxes_4}"

    # Verifikasi opsi tiap nomor
    for q_num in range(1, 101):
        q_str = str(q_num)
        assert set(prof3.answer_grid[q_str].keys()) == {"A", "B", "C"}
        assert set(prof4.answer_grid[q_str].keys()) == {"A", "B", "C", "D"}


def test_form_profile_json_roundtrip(tmp_path):
    """Uji serialisasi dan deserialisasi profil form ke format JSON."""
    prof4 = build_default_form_profile(num_options=4)
    json_path = tmp_path / "form_profile_4opts.json"
    prof4.to_json(json_path)

    assert json_path.is_file()
    loaded_prof = FormProfile.from_json(json_path)
    assert loaded_prof.num_options == 4
    assert len(loaded_prof.answer_grid) == 100
    assert loaded_prof.answer_grid["1"]["A"] == prof4.answer_grid["1"]["A"]


def test_align_and_detect_variant_3opts_fixture():
    """Uji pelurusan dan deteksi varian pada scan 3 opsi (4 halaman kosong)."""
    pdf_path = Path("tests/fixtures/contoh soal 3 opsi_261120_175753.pdf")
    if not pdf_path.is_file():
        pytest.skip("Fixture 3-opsi tidak ditemukan")

    doc = pdfium.PdfDocument(pdf_path)
    assert len(doc) == 4

    for page_idx in range(len(doc)):
        img_pil = doc[page_idx].render(scale=2.0).to_pil()
        img_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

        # 1. Temukan penanda sudut (harus ada minimal 4)
        markers = find_markers(img_bgr)
        assert len(markers) >= 4, f"Page {page_idx+1}: markers count {len(markers)} < 4"

        # 2. Luruskan halaman
        warped, warnings = align_form_page(img_bgr)
        assert warped.shape == (CANONICAL_HEIGHT, CANONICAL_WIDTH, 3)

        # 3. Deteksi varian (harus terdeteksi sebagai 3 opsi)
        variant = detect_form_variant(warped)
        assert variant == 3, f"Page {page_idx+1} expected 3-opts, got {variant}"


def test_align_and_detect_variant_4opts_fixture():
    """Uji pelurusan dan deteksi varian pada scan 4 opsi (5 halaman kosong)."""
    pdf_path = Path("tests/fixtures/cobtoh lembar soal_261120_174640.pdf")
    if not pdf_path.is_file():
        pytest.skip("Fixture 4-opsi tidak ditemukan")

    doc = pdfium.PdfDocument(pdf_path)
    assert len(doc) == 5

    for page_idx in range(len(doc)):
        img_pil = doc[page_idx].render(scale=2.0).to_pil()
        img_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

        # 1. Temukan penanda sudut (harus ada minimal 4)
        markers = find_markers(img_bgr)
        assert len(markers) >= 4, f"Page {page_idx+1}: markers count {len(markers)} < 4"

        # 2. Luruskan halaman
        warped, warnings = align_form_page(img_bgr)
        assert warped.shape == (CANONICAL_HEIGHT, CANONICAL_WIDTH, 3)

        # 3. Deteksi varian (harus terdeteksi sebagai 4 opsi)
        variant = detect_form_variant(warped)
        assert variant == 4, f"Page {page_idx+1} expected 4-opts, got {variant}"


def test_render_profile_overlay(tmp_path):
    """Uji pembuatan gambar overlay profil di atas scan yang diluruskan."""
    pdf_path = Path("tests/fixtures/cobtoh lembar soal_261120_174640.pdf")
    if not pdf_path.is_file():
        pytest.skip("Fixture tidak ditemukan")

    doc = pdfium.PdfDocument(pdf_path)
    img_pil = doc[0].render(scale=2.0).to_pil()
    img_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    warped, _ = align_form_page(img_bgr)
    prof4 = build_default_form_profile(num_options=4)
    overlay = render_profile_overlay(warped, prof4)

    assert overlay.shape == warped.shape
    out_overlay_file = tmp_path / "test_overlay.png"
    cv2.imwrite(str(out_overlay_file), overlay)
    assert out_overlay_file.is_file()
    assert out_overlay_file.stat().st_size > 50000
