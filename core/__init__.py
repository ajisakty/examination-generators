"""
Core package untuk backend Exam Generator.
Logika backend murni tanpa antarmuka grafis (GUI) atau print langsung.
"""

from .models import (
    Exam,
    ExamConfig,
    Question,
    AnswerKeyMetadata,
    QuestionAnswerResult,
    SheetScanResult,
    ScannerBatchResult,
    SheetScoreResult,
    QuestionAnalysisResult,
    ExamAnalysisSummary,
    ExamAnalysisReport,
)
from .excel_loader import load_and_validate_exam_excel, ExcelValidationError
from .shuffler import create_set_b
from .answer_key import (
    generate_answer_key_excel,
    load_and_verify_answer_key,
    validate_cross_set_integrity,
    calculate_key_hash,
)
from .exam_pdf import generate_exam_pdf
from .scanner_align import align_form_page, find_markers
from .form_profile import (
    FormProfile,
    BoxCoord,
    build_default_form_profile,
    detect_form_variant,
    render_profile_overlay,
)
from .scanner import scan_single_sheet, scan_pdf_batch, read_exam_code
from .analyzer import calculate_sheet_score, analyze_exam_results
from .report_pdf import generate_analysis_report_pdf

__all__ = [
    "Exam",
    "ExamConfig",
    "Question",
    "AnswerKeyMetadata",
    "QuestionAnswerResult",
    "SheetScanResult",
    "ScannerBatchResult",
    "SheetScoreResult",
    "QuestionAnalysisResult",
    "ExamAnalysisSummary",
    "ExamAnalysisReport",
    "load_and_validate_exam_excel",
    "ExcelValidationError",
    "create_set_b",
    "generate_answer_key_excel",
    "load_and_verify_answer_key",
    "validate_cross_set_integrity",
    "calculate_key_hash",
    "generate_exam_pdf",
    "align_form_page",
    "find_markers",
    "FormProfile",
    "BoxCoord",
    "build_default_form_profile",
    "detect_form_variant",
    "render_profile_overlay",
    "scan_single_sheet",
    "scan_pdf_batch",
    "read_exam_code",
    "calculate_sheet_score",
    "analyze_exam_results",
    "generate_analysis_report_pdf",
]
