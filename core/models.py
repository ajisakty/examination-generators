from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Question:
    """Representasi satu butir soal."""
    question_code: str       # Kode unik per soal (Question Code)
    ata: str                 # ATA chapter (misal: "21", "36A")
    question_text: str       # Teks soal
    options: List[str]       # Daftar pilihan jawaban, misal [opsi A, opsi B, opsi C, opsi D]
    correct_answer: str      # Kunci jawaban ("A", "B", "C", atau "D")
    order_number: Optional[int] = None  # Urutan nomor soal pada lembar (1-100)
    ata_title: str = ""      # Judul ATA (opsional)
    level: Optional[int] = None         # Tingkat kesulitan (opsional)


@dataclass
class ExamConfig:
    """Konfigurasi dan metadata ujian dari Sheet Config."""
    title: str               # Judul ujian (Course Title)
    course_name: str         # Sub Course Title / Exam Name
    course_code: str         # Course Code (kode satu ujian, misal: "JCT-0220408A")
    duration_minutes: int    # Durasi ujian (menit)
    total_questions: int     # Jumlah soal
    num_options: int         # Jumlah opsi jawaban (3 atau 4)
    total_score: float = 100.0   # Total skor maksimal (misal: 100)
    pass_mark: float = 75.0      # Nilai batas kelulusan dalam persen (misal: 75)
    prepared_by: str = ""    # Nama penyusun
    form_no: str = ""        # Nomor form footer
    issue: int = 1           # Issue footer
    year: int = 2026         # Year footer
    model: str = ""          # Label model footer


@dataclass
class Exam:
    """Representasi lengkap satu set ujian (Set A, Set B, atau remedial)."""
    config: ExamConfig
    set_name: str            # "A", "B", atau "R"
    questions: List[Question] = field(default_factory=list)


@dataclass
class AnswerKeyMetadata:
    """Metadata untuk file Excel Kunci Jawaban."""
    schema_version: str = "1.0"
    exam_name: str = ""
    course_code: str = ""
    total_questions: int = 0
    num_options: int = 4
    total_score: float = 100.0
    pass_mark: float = 75.0
    created_date: str = ""
    random_seed: Optional[int] = None
    content_hash: str = ""
