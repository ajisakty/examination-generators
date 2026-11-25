"""
Modul pengacakan soal untuk Set B.
Set B diacak di dalam tiap kelompok ATA menggunakan random seed.
Opsi jawaban (A-D) tidak diacak.
"""

import copy
import random
from typing import Dict, List, Optional, Tuple

from .models import Exam, Question


def create_set_b(
    exam_a: Exam,
    seed: Optional[int] = None,
    similarity_threshold: float = 0.8,
) -> Tuple[Exam, int, List[str]]:
    """
    Menghasilkan Exam Set B dari Set A.
    
    Aturan:
    - Urutan kelompok ATA dipertahankan.
    - Urutan soal di dalam tiap ATA diacak.
    - Pilihan opsi (A-D) tidak diacak.
    - Menggunakan random seed (jika None, seed dibuat otomatis).
    - Memeriksa kemiripan: jika urutan soal Set B terlalu mirip Set A, beri warning.
    
    Returns:
        Tuple[Exam, int, List[str]]: Objek Exam Set B, seed yang dipakai, dan daftar peringatan.
    """
    if seed is None:
        seed = random.randint(100000, 999999)

    rng = random.Random(seed)
    warnings: List[str] = []

    # Kelompokkan soal per ATA dengan mempertahankan urutan kemunculan ATA pertama kali
    ata_groups: Dict[str, List[Question]] = {}
    for q in exam_a.questions:
        ata_key = str(q.ata).strip()
        if ata_key not in ata_groups:
            ata_groups[ata_key] = []
        ata_groups[ata_key].append(copy.deepcopy(q))

    shuffled_questions: List[Question] = []
    identical_positions = 0
    total_multi_questions = 0

    for ata_key, q_list in ata_groups.items():
        if len(q_list) > 1:
            total_multi_questions += len(q_list)
            # Simpan urutan asli kode soal dalam kelompok ATA ini
            original_codes = [q.question_code for q in q_list]
            
            # Acak urutan soal di dalam kelompok ATA
            shuffled_group = list(q_list)
            rng.shuffle(shuffled_group)
            
            shuffled_codes = [q.question_code for q in shuffled_group]
            for orig, shuff in zip(original_codes, shuffled_codes):
                if orig == shuff:
                    identical_positions += 1
            shuffled_questions.extend(shuffled_group)
        else:
            shuffled_questions.extend(q_list)

    # Beri nomor urut baru (order_number) 1..N
    for idx, q in enumerate(shuffled_questions, start=1):
        q.order_number = idx

    # Evaluasi kemiripan
    if total_multi_questions > 0:
        similarity_ratio = identical_positions / total_multi_questions
        if similarity_ratio >= similarity_threshold:
            warnings.append(
                f"Peringatan: Urutan soal Set B cukup mirip dengan Set A "
                f"({identical_positions} dari {total_multi_questions} soal pada ATA majemuk tidak berpindah posisi, "
                f"rasio: {similarity_ratio:.1%}). Pertimbangkan memakai seed lain."
            )

    # Buat Exam Set B
    config_b = copy.deepcopy(exam_a.config)
    exam_b = Exam(
        config=config_b,
        set_name="B",
        questions=shuffled_questions,
    )

    return exam_b, seed, warnings
