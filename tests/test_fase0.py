from pathlib import Path
import pytest
from core.models import Exam, ExamConfig, Question, AnswerKeyMetadata
from core.exam_pdf import generate_exam_pdf


def test_core_models_instantiation():
    """Uji inisialisasi struktur data dasar Exam, Config, dan Question."""
    config = ExamConfig(
        title="Ujian Akhir Training",
        course_name="Aircraft Systems Basic",
        course_code="ASB1012026",
        duration_minutes=60,
        total_questions=2,
        num_options=4,
        total_score=100,
        pass_mark=75,
    )
    
    q1 = Question(
        question_code="Q001",
        ata="21",
        question_text="Apa fungsi utama Air Conditioning System pada pesawat?",
        options=["Mengatur suhu kabin", "Menaikkan tekanan oli", "Memadamkan api mesin", "Mengisi bahan bakar"],
        correct_answer="A",
        order_number=1,
    )
    
    q2 = Question(
        question_code="Q002",
        ata="36A",
        question_text="Pneumatic source berasal dari mana?",
        options=["Engine bleed air", "Baterai utama", "Hydraulic reservoir", "Oxygen bottle"],
        correct_answer="A",
        order_number=2,
    )
    
    exam = Exam(config=config, set_name="A", questions=[q1, q2])
    
    assert exam.set_name == "A"
    assert exam.config.course_code == "ASB1012026"
    assert len(exam.questions) == 2
    assert exam.questions[0].question_code == "Q001"
    assert exam.questions[1].ata == "36A"


def test_answer_key_metadata():
    """Uji model metadata kunci jawaban."""
    meta = AnswerKeyMetadata(
        schema_version="1.0",
        exam_name="Aircraft Systems Basic",
        course_code="ASB1012026",
        total_questions=2,
        num_options=4,
        total_score=100,
        pass_mark=75,
        created_date="2026-11-25",
        random_seed=42,
        content_hash="abc123def456",
    )
    assert meta.schema_version == "1.0"
    assert meta.random_seed == 42


def test_exam_pdf_placeholder():
    """Uji fungsi antarmuka generator PDF."""
    config = ExamConfig(
        title="Sample",
        course_name="Sample",
        course_code="SMPL123456",
        duration_minutes=30,
        total_questions=0,
        num_options=4,
        total_score=100,
        pass_mark=75,
    )
    exam = Exam(config=config, set_name="A")
    out = generate_exam_pdf(exam, "dummy.pdf")
    assert isinstance(out, Path)


def test_project_structure_exists():
    """Pastikan direktori proyek sesuai PLAN.md ada."""
    base_dir = Path(__file__).resolve().parent.parent
    assert (base_dir / "core").is_dir()
    assert (base_dir / "tests").is_dir()
    assert (base_dir / "assets").is_dir()
    assert (base_dir / "tools").is_dir()
    assert (base_dir / "requirements.txt").is_file()
