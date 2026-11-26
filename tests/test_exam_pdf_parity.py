"""
Tes kesesuaian PDF soal: hasil core/exam_pdf.py harus sama dengan skrip asli
(legacy/exam_pdf_original.py) untuk Excel yang sama, kecuali label MODEL (huruf set).
"""
import importlib.util
import re
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from core import create_set_b, generate_exam_pdf, load_and_validate_exam_excel

BASE = Path(__file__).resolve().parent.parent
FIXTURE = BASE / "tests" / "fixtures" / "Exam Sample A.xlsx"
LEGACY = BASE / "legacy" / "exam_pdf_original.py"


def _load_legacy():
    spec = importlib.util.spec_from_file_location("exam_pdf_original", LEGACY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # pakai font yang sama dengan core (Carlito di assets/fonts)
    mod._FONT_DIRS.insert(0, str(BASE / "assets" / "fonts"))
    return mod


def _pages_text(path):
    pdf = pdfium.PdfDocument(str(path))
    texts = []
    for i in range(len(pdf)):
        t = pdf[i].get_textpage().get_text_range()
        t = re.sub(r"MODEL:\s*\S+", "MODEL:", t)      # label MODEL boleh beda (huruf set)
        texts.append(re.sub(r"\s+", " ", t).strip())
    return texts


@pytest.fixture(scope="module")
def sample_exam():
    if not FIXTURE.is_file() or not LEGACY.is_file():
        pytest.skip("Fixture Excel atau legacy/exam_pdf_original.py tidak ada.")
    exam, _warnings = load_and_validate_exam_excel(FIXTURE, set_name="A")
    return exam


def test_pdf_sama_dengan_skrip_asli(tmp_path, sample_exam):
    legacy = _load_legacy()
    old_pdf = tmp_path / "asli.pdf"
    legacy_exam = legacy.load_exam(str(FIXTURE))
    # Skrip asli mengurutkan soal per kode ATA; core mengikuti urutan baris Excel.
    # Samakan urutannya dulu supaya yang dibandingkan hanya tampilan (tata letak, teks, footer).
    legacy_exam.questions.sort(key=lambda q: q.row)
    # Judul ATA: skrip asli memakai tabel di sheet Config, core memakai kolom "ATA Title" di sheet Questions.
    judul = {q.ata: q.ata_title for q in sample_exam.questions}
    for i, q in enumerate(legacy_exam.questions, start=1):
        q.no = i
        q.ata_title = judul.get(q.ata, q.ata_title)
    legacy.build_question_paper(legacy_exam, str(old_pdf))
    new_pdf = generate_exam_pdf(sample_exam, tmp_path / "baru.pdf")

    old_pages, new_pages = _pages_text(old_pdf), _pages_text(new_pdf)
    assert len(new_pages) == len(old_pages), "Jumlah halaman berbeda dari skrip asli"
    for i, (a, b) in enumerate(zip(old_pages, new_pages), start=1):
        assert a == b, f"Teks halaman {i} berbeda dari skrip asli"


def test_sampul_dan_identitas_ada(tmp_path, sample_exam):
    pdf = generate_exam_pdf(sample_exam, tmp_path / "a.pdf")
    first = _pages_text(pdf)[0]
    for kata in ("Written Examination Paper", "personal identification", "NAME", "ID. NUMBER",
                 "SIGNATURE", "Course Code:", "disqualified from the training"):
        assert kata in first, f"'{kata}' tidak ada di halaman sampul"
    assert f"Page 1 of {len(_pages_text(pdf))}" in first


def test_karakter_khusus_tidak_hilang(tmp_path, sample_exam):
    import copy
    exam = copy.deepcopy(sample_exam)
    exam.questions[0].question_text = "Tekanan < 3000 psi & suhu > 90 C, mode <CLOSED>?"
    exam.questions[0].options[0] = "Valve A&B <OPEN>"
    pdf = generate_exam_pdf(exam, tmp_path / "khusus.pdf")
    semua = " ".join(_pages_text(pdf))
    assert "<CLOSED>" in semua
    assert "A&B <OPEN>" in semua


def test_set_b_terbentuk_dengan_label_model(tmp_path, sample_exam):
    exam_b, _seed, _warn = create_set_b(sample_exam, seed=123)
    pdf = generate_exam_pdf(exam_b, tmp_path / "b.pdf")
    semua = " ".join(_pages_text(pdf))
    assert "MODEL:" in semua
    pdf_text_raw = pdfium.PdfDocument(str(pdf))[0].get_textpage().get_text_range()
    assert "MODEL: B" in re.sub(r"\s+", " ", pdf_text_raw)
