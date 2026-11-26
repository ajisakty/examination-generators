from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
    sub_course_title: str = ""   # Sub Course Title (baris kedua sampul)
    exam_name: str = ""          # Exam Name (baris ketiga sampul)
    organization: str = ""       # Nama organisasi di footer (kosong = bawaan)
    form_label: str = ""         # Label nomor form di footer (kosong = bawaan)


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


# --- Model Hasil Pemindaian (Scanner) ---

@dataclass
class QuestionAnswerResult:
    """Hasil pembacaan satu nomor jawaban."""
    question_number: int                 # Nomor soal (1-100)
    selected_option: Optional[str]       # "A", "B", "C", "D", atau None jika kosong
    status: str                          # "jelas", "kosong", "ganda", "samar"
    needs_review: bool                   # True jika ambigu / samar / ganda
    scores: Dict[str, float] = field(default_factory=dict) # Skor kegelapan per opsi
    crop_image_path: Optional[str] = None # Path potongan gambar jika perlu_review


@dataclass
class SheetScanResult:
    """Hasil pembacaan satu lembar jawaban peserta."""
    sheet_index: int                     # Nomor urut lembar dalam PDF scan (mulai 1)
    detected_set: str                    # Kode exam yang terdeteksi ("A", "B", "R", atau "?")
    trainee_id: str = ""                 # ID peserta (6 digit)
    date_str: str = ""                   # Tanggal ujian (6 digit)
    course_code: str = ""                # Kode kursus dari lembar
    answers: Dict[int, QuestionAnswerResult] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    needs_review: bool = False           # True jika ada jawaban atau metadata yang perlu direview


@dataclass
class ScannerBatchResult:
    """Hasil pemindaian satu batch PDF lembar jawaban."""
    pdf_path: str
    total_sheets: int
    sheets: List[SheetScanResult] = field(default_factory=list)
    review_count: int = 0


# --- Model Hasil Analisis & Laporan Ujian ---

@dataclass
class SheetScoreResult:
    """Hasil penilaian satu lembar jawaban peserta."""
    sheet_index: int
    set_name: str                        # "A" atau "B"
    correct_count: int                   # Jumlah jawaban benar
    total_questions: int                 # Jumlah soal
    score: int                           # Skor akhir (0 - 100), dibulatkan ke bawah
    is_passed: bool                      # True jika score >= pass_mark
    wrong_questions: List[int] = field(default_factory=list) # Nomor urut soal salah di lembar ini


@dataclass
class QuestionAnalysisResult:
    """Hasil analisis tingkat kesulitan dan performa per butir soal (Question Code)."""
    question_code: str                   # Kode unik soal
    ata: str                             # ATA chapter
    question_text: str                   # Teks soal lengkap
    correct_answer: str                  # Kunci jawaban ("A", "B", "C", atau "D")
    order_number_a: Optional[int] = None # Nomor soal di Set A
    order_number_b: Optional[int] = None # Nomor soal di Set B
    correct_count_a: int = 0             # Jumlah jawaban benar di Set A
    total_participants_a: int = 0        # Total peserta Set A
    rate_a: Optional[float] = None       # Persentase keberhasilan di Set A (%)
    correct_count_b: int = 0             # Jumlah jawaban benar di Set B
    total_participants_b: int = 0        # Total peserta Set B
    rate_b: Optional[float] = None       # Persentase keberhasilan di Set B (%)
    total_correct: int = 0               # Total jawaban benar gabungan (A + B)
    total_participants: int = 0          # Total seluruh peserta (A + B)
    total_rate: float = 0.0              # Persentase keberhasilan gabungan (%)
    highlight_status: Optional[str] = None # "TERLALU_MUDAH", "TERLALU_SULIT", atau None


@dataclass
class ExamAnalysisSummary:
    """Ringkasan statistik hasil ujian keseluruhan."""
    total_sheets_a: int = 0
    total_sheets_b: int = 0
    total_sheets: int = 0
    average_score_a: float = 0.0
    average_score_b: float = 0.0
    average_score_total: float = 0.0
    passed_count: int = 0
    failed_count: int = 0
    pass_percentage: float = 0.0
    pass_mark: float = 75.0
    highest_score: int = 0
    lowest_score: int = 0


@dataclass
class ExamAnalysisReport:
    """Container lengkap seluruh hasil analisis ujian siap cetak PDF."""
    config: ExamConfig
    summary: ExamAnalysisSummary
    sheet_scores: List[SheetScoreResult] = field(default_factory=list)
    question_analyses: List[QuestionAnalysisResult] = field(default_factory=list)
    highlighted_questions: List[QuestionAnalysisResult] = field(default_factory=list)

