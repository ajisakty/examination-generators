"""
Modul pembuat PDF soal ujian.
Backend murni menggunakan reportlab.
"""
from pathlib import Path
from typing import Optional
from .models import Exam


def generate_exam_pdf(exam: Exam, output_path: str | Path, progress_callback=None) -> Path:
    """
    Kerangka fungsi pembuat PDF soal ujian.
    Akan diimplementasikan penuh pada fase berikutnya.
    """
    path = Path(output_path)
    # Placeholder implementasi
    return path
