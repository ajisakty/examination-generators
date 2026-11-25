"""
Modul analisis skor dan performa soal ujian (Fase 5).
Menghitung skor per lembar (dibulatkan ke bawah), menganalisis tingkat keberhasilan
per Question Code (gabungan A+B, rate A, rate B), serta mendeteksi highlight soal
terlalu mudah (>90%) dan terlalu sulit (<50%).
"""

import math
from typing import Dict, List, Optional
from .models import (
    Exam,
    ExamConfig,
    ExamAnalysisReport,
    ExamAnalysisSummary,
    QuestionAnalysisResult,
    SheetScanResult,
    SheetScoreResult,
)


def calculate_sheet_score(
    sheet: SheetScanResult,
    key_by_order: Dict[int, str],
    total_questions: int,
    pass_mark: float = 75.0,
    set_name: str = "A",
) -> SheetScoreResult:
    """
    Menghitung skor untuk satu lembar jawaban peserta.
    
    Skor dihitung sebagai (jumlah benar / jumlah soal) * 100,
    dan dibulatkan ke bawah (floor) ke integer terdekat.
    """
    correct_count = 0
    wrong_questions: List[int] = []

    for q_no in range(1, total_questions + 1):
        expected_ans = key_by_order.get(q_no)
        user_ans_obj = sheet.answers.get(q_no)
        user_ans = user_ans_obj.selected_option if user_ans_obj else None

        if expected_ans and user_ans == expected_ans:
            correct_count += 1
        else:
            wrong_questions.append(q_no)

    raw_percentage = (correct_count / total_questions) * 100.0 if total_questions > 0 else 0.0
    score = int(math.floor(raw_percentage))
    is_passed = score >= pass_mark

    return SheetScoreResult(
        sheet_index=sheet.sheet_index,
        set_name=set_name,
        correct_count=correct_count,
        total_questions=total_questions,
        score=score,
        is_passed=is_passed,
        wrong_questions=wrong_questions,
    )


def analyze_exam_results(
    exam_a: Exam,
    exam_b: Exam,
    sheets_a: List[SheetScanResult],
    sheets_b: List[SheetScanResult],
) -> ExamAnalysisReport:
    """
    Menganalisis hasil ujian Set A dan Set B secara menyeluruh:
    - Memvalidasi bahwa tidak ada lembar atau nomor yang berstatus perlu_review.
    - Menghitung skor per lembar untuk seluruh peserta.
    - Menghitung statistik ringkasan ujian.
    - Menghitung rate keberhasilan per Question Code (Set A, Set B, dan Gabungan).
    - Menentukan status highlight (>90% terlalu mudah, <50% terlalu sulit; tepat 90% dan 50% tidak ditandai).
    """
    # 1. Validasi: Jangan buat laporan jika masih ada jawaban 'perlu review'
    unresolved_reviews: List[str] = []
    for s in sheets_a:
        if s.needs_review:
            unresolved_reviews.append(f"Set A Lembar {s.sheet_index}")
    for s in sheets_b:
        if s.needs_review:
            unresolved_reviews.append(f"Set B Lembar {s.sheet_index}")

    if unresolved_reviews:
        details = ", ".join(unresolved_reviews)
        raise ValueError(
            f"Tidak dapat membuat analisis laporan: masih terdapat {len(unresolved_reviews)} "
            f"lembar jawaban yang berstatus 'perlu review' ({details}). "
            f"Selesaikan verifikasi review terlebih dahulu."
        )

    config = exam_a.config
    total_questions = config.total_questions
    pass_mark = config.pass_mark

    # Pemetaan kunci jawaban per nomor urut
    keys_a: Dict[int, str] = {q.order_number: q.correct_answer for q in exam_a.questions if q.order_number}
    keys_b: Dict[int, str] = {q.order_number: q.correct_answer for q in exam_b.questions if q.order_number}

    # 2. Hitung skor tiap lembar
    scores_a = [
        calculate_sheet_score(s, keys_a, total_questions, pass_mark, set_name="A")
        for s in sheets_a
    ]
    scores_b = [
        calculate_sheet_score(s, keys_b, total_questions, pass_mark, set_name="B")
        for s in sheets_b
    ]
    all_scores = scores_a + scores_b

    # 3. Hitung ringkasan statistik
    total_sheets_a = len(scores_a)
    total_sheets_b = len(scores_b)
    total_sheets = total_sheets_a + total_sheets_b

    avg_a = (sum(s.score for s in scores_a) / total_sheets_a) if total_sheets_a > 0 else 0.0
    avg_b = (sum(s.score for s in scores_b) / total_sheets_b) if total_sheets_b > 0 else 0.0
    avg_total = (sum(s.score for s in all_scores) / total_sheets) if total_sheets > 0 else 0.0

    passed_count = sum(1 for s in all_scores if s.is_passed)
    failed_count = total_sheets - passed_count
    pass_pct = (passed_count / total_sheets * 100.0) if total_sheets > 0 else 0.0
    highest = max((s.score for s in all_scores), default=0)
    lowest = min((s.score for s in all_scores), default=0)

    summary = ExamAnalysisSummary(
        total_sheets_a=total_sheets_a,
        total_sheets_b=total_sheets_b,
        total_sheets=total_sheets,
        average_score_a=round(avg_a, 2),
        average_score_b=round(avg_b, 2),
        average_score_total=round(avg_total, 2),
        passed_count=passed_count,
        failed_count=failed_count,
        pass_percentage=round(pass_pct, 2),
        pass_mark=pass_mark,
        highest_score=highest,
        lowest_score=lowest,
    )

    # 4. Analisis performa per butir soal (Question Code)
    order_a_by_code: Dict[str, int] = {
        q.question_code: q.order_number for q in exam_a.questions if q.order_number
    }
    order_b_by_code: Dict[str, int] = {
        q.question_code: q.order_number for q in exam_b.questions if q.order_number
    }

    # Hitung kebenaran jawaban per soal
    question_analyses: List[QuestionAnalysisResult] = []
    highlighted_questions: List[QuestionAnalysisResult] = []

    for q in exam_a.questions:
        q_code = q.question_code
        ord_a = order_a_by_code.get(q_code)
        ord_b = order_b_by_code.get(q_code)

        # Hitung benar di Set A
        correct_a = 0
        expected_a = keys_a.get(ord_a) if ord_a else None
        if ord_a and expected_a:
            for s in sheets_a:
                ans_obj = s.answers.get(ord_a)
                if ans_obj and ans_obj.selected_option == expected_a:
                    correct_a += 1

        # Hitung benar di Set B
        correct_b = 0
        expected_b = keys_b.get(ord_b) if ord_b else None
        if ord_b and expected_b:
            for s in sheets_b:
                ans_obj = s.answers.get(ord_b)
                if ans_obj and ans_obj.selected_option == expected_b:
                    correct_b += 1

        total_correct = correct_a + correct_b
        rate_a = (correct_a / total_sheets_a * 100.0) if total_sheets_a > 0 else None
        rate_b = (correct_b / total_sheets_b * 100.0) if total_sheets_b > 0 else None
        total_rate = (total_correct / total_sheets * 100.0) if total_sheets > 0 else 0.0

        # Evaluasi highlight: > 90% (mudah), < 50% (sulit). Tepat 90.0% dan 50.0% tidak ditandai
        highlight_status: Optional[str] = None
        if total_rate > 90.0:
            highlight_status = "TERLALU_MUDAH"
        elif total_rate < 50.0:
            highlight_status = "TERLALU_SULIT"

        q_analysis = QuestionAnalysisResult(
            question_code=q_code,
            ata=q.ata,
            question_text=q.question_text,
            correct_answer=q.correct_answer,
            order_number_a=ord_a,
            order_number_b=ord_b,
            correct_count_a=correct_a,
            total_participants_a=total_sheets_a,
            rate_a=round(rate_a, 2) if rate_a is not None else None,
            correct_count_b=correct_b,
            total_participants_b=total_sheets_b,
            rate_b=round(rate_b, 2) if rate_b is not None else None,
            total_correct=total_correct,
            total_participants=total_sheets,
            total_rate=round(total_rate, 2),
            highlight_status=highlight_status,
        )

        question_analyses.append(q_analysis)
        if highlight_status:
            highlighted_questions.append(q_analysis)

    return ExamAnalysisReport(
        config=config,
        summary=summary,
        sheet_scores=all_scores,
        question_analyses=question_analyses,
        highlighted_questions=highlighted_questions,
    )
