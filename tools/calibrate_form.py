"""
Skrip kalibrasi profil form OMR (Tools).
Digunakan untuk mengekstrak atau memperbarui profil posisi kotak lembar jawaban JSON
dan menghasilkan gambar overlay visual untuk verifikasi mata.
"""

from pathlib import Path
import cv2
import pypdfium2 as pdfium

from core.scanner_align import align_form_page
from core.form_profile import (
    build_default_form_profile,
    detect_form_variant,
    render_profile_overlay,
)


def calibrate_and_export_profiles(output_dir: str | Path = "tools/profiles") -> None:
    """
    Menghasilkan file JSON form_profile_3opts.json, form_profile_4opts.json,
    serta gambar overlay pengecekan.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Bangun profil 3 opsi dan 4 opsi
    prof3 = build_default_form_profile(num_options=3)
    prof4 = build_default_form_profile(num_options=4)

    prof3.to_json(out_path / "form_profile_3opts.json")
    prof4.to_json(out_path / "form_profile_4opts.json")

    # 2. Buat overlay visual dari fixture jika tersedia
    f3_pdf = Path("tests/fixtures/contoh soal 3 opsi_261120_175753.pdf")
    f4_pdf = Path("tests/fixtures/cobtoh lembar soal_261120_174640.pdf")

    if f3_pdf.is_file():
        doc3 = pdfium.PdfDocument(f3_pdf)
        img3_raw = doc3[0].render(scale=2.0).to_pil()
        bgr3 = cv2.cvtColor(np.array(img3_raw), cv2.COLOR_RGB2BGR)
        warped3, _ = align_form_page(bgr3)
        ov3 = render_profile_overlay(warped3, prof3)
        cv2.imwrite(str(out_path / "overlay_3opts_sample.png"), ov3)

    if f4_pdf.is_file():
        doc4 = pdfium.PdfDocument(f4_pdf)
        img4_raw = doc4[0].render(scale=2.0).to_pil()
        bgr4 = cv2.cvtColor(np.array(img4_raw), cv2.COLOR_RGB2BGR)
        warped4, _ = align_form_page(bgr4)
        ov4 = render_profile_overlay(warped4, prof4)
        cv2.imwrite(str(out_path / "overlay_4opts_sample.png"), ov4)


if __name__ == "__main__":
    import numpy as np
    calibrate_and_export_profiles()
