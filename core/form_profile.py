"""
Modul profil form dan tata letak kisi lembar jawaban (3 opsi vs 4 opsi).
Mendefinisikan koordinat kanonikal kotak jawaban 1-100 dan area metadata form.
Mendukung export/import profil ke/dari format JSON dan deteksi otomatis varian form.
"""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np


@dataclass
class BoxCoord:
    """Koordinat bounding box (x, y, w, h) pada kanvas kanonikal (1200 x 1700)."""
    x: int
    y: int
    w: int
    h: int


@dataclass
class FormProfile:
    """Profil lengkap posisi kotak-kotak pada form lembar jawaban."""
    num_options: int                     # 3 atau 4 opsi
    canvas_width: int = 1200
    canvas_height: int = 1700
    # Map: str(question_number: 1..100) -> {"A": BoxCoord, "B": BoxCoord, ...}
    answer_grid: Dict[str, Dict[str, Dict[str, int]]] = field(default_factory=dict)
    # Kotak Exam Code ("A", "B", "R")
    exam_code_boxes: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # Kisi Trainee ID (6 digit x 10 baris 0-9)
    trainee_id_boxes: List[Dict[str, Dict[str, int]]] = field(default_factory=list)
    # Kisi Date (6 digit)
    date_boxes: List[Dict[str, Dict[str, int]]] = field(default_factory=list)
    # Kisi Course Code
    course_code_boxes: List[Dict[str, Dict[str, int]]] = field(default_factory=list)

    def to_json(self, file_path: str | Path) -> None:
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def from_json(cls, file_path: str | Path) -> "FormProfile":
        p = Path(file_path)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)


def build_default_form_profile(num_options: int = 4) -> FormProfile:
    """
    Menghasilkan FormProfile default berdasarkan pengukuran kanonikal lembar resmi GMF/U-013 R2.
    
    Layout Jawaban (100 Nomor):
    - 4 Blok x 25 Baris:
      - Blok 1: No. 1 - 25
      - Blok 2: No. 26 - 50
      - Blok 3: No. 51 - 75
      - Blok 4: No. 76 - 100
    - Baris: Y mulai ~511 px, step ~29.8 px per nomor
    - Kolom Opsi:
      - 4 Opsi (A, B, C, D):
        - Blok 1: [234, 262, 290, 318]
        - Blok 2: [518, 546, 574, 602]
        - Blok 3: [744, 772, 800, 828]
        - Blok 4: [966, 994, 1022, 1050]
      - 3 Opsi (A, B, C):
        - Blok 1: [236, 264, 292]
        - Blok 2: [546, 574, 602]
        - Blok 3: [744, 772, 800]
        - Blok 4: [966, 994, 1022]
    """
    profile = FormProfile(num_options=num_options)
    options = ["A", "B", "C", "D"] if num_options == 4 else ["A", "B", "C"]

    # 4 Blok Kolom
    if num_options == 4:
        block_cols = [
            [234, 262, 290, 318],
            [518, 546, 574, 602],
            [744, 772, 800, 828],
            [966, 994, 1022, 1050],
        ]
    else:
        block_cols = [
            [236, 264, 292],
            [546, 574, 602],
            [744, 772, 800],
            [966, 994, 1022],
        ]

    y_start = 511.0
    y_step = 29.8
    box_w = 18
    box_h = 18

    # Susun 100 nomor
    q_num = 1
    for block_idx in range(4):
        cols = block_cols[block_idx]
        for row_idx in range(25):
            cy = int(round(y_start + row_idx * y_step))
            opts_map = {}
            for opt_idx, opt_letter in enumerate(options):
                cx = cols[opt_idx]
                opts_map[opt_letter] = {
                    "x": cx - box_w // 2,
                    "y": cy - box_h // 2,
                    "w": box_w,
                    "h": box_h,
                }
            profile.answer_grid[str(q_num)] = opts_map
            q_num += 1

    # Kotak Exam Code (A, B, R)
    profile.exam_code_boxes = {
        "A": {"x": 201, "y": 124, "w": 18, "h": 18},
        "B": {"x": 224, "y": 124, "w": 18, "h": 18},
        "R": {"x": 247, "y": 124, "w": 18, "h": 18},
    }

    return profile


def detect_form_variant(img_bgr: np.ndarray) -> int:
    """
    Mendeteksi varian form secara otomatis (3 opsi vs 4 opsi).
    
    Prinsip:
    Mengukur intensitas warna merah cetakan pada area jawaban (y: 480..1300, x: 100..1100).
    Form 4 opsi memiliki 400 bulatan merah (total piksel merah > 37,000).
    Form 3 opsi memiliki 300 bulatan merah (total piksel merah <= 37,000).
    
    Returns:
        3 atau 4 (jumlah opsi jawaban).
    """
    sub = img_bgr[480:1300, 100:1100]
    b, g, r = cv2.split(sub)
    diff = r.astype(int) - b.astype(int)
    red_count = int(np.sum(diff > 20))

    # Threshold adaptif
    if red_count > 37000:
        return 4
    return 3


def render_profile_overlay(img_bgr: np.ndarray, profile: FormProfile) -> np.ndarray:
    """
    Menggambar visualisasi kotak-kotak profil di atas gambar scan yang sudah diluruskan
    untuk verifikasi visual kecocokan posisi kotak form.
    """
    overlay = img_bgr.copy()

    # Warna garis overlay (BGR): Hijau untuk jawaban, Biru untuk metadata
    grid_color = (0, 255, 0)
    meta_color = (255, 0, 0)

    # Gambar kotak jawaban 1 - 100
    for q_str, opts in profile.answer_grid.items():
        for opt_str, b in opts.items():
            cv2.rectangle(
                overlay,
                (b["x"], b["y"]),
                (b["x"] + b["w"], b["y"] + b["h"]),
                grid_color,
                1,
            )

    # Gambar kotak exam code
    for code, b in profile.exam_code_boxes.items():
        cv2.rectangle(
            overlay,
            (b["x"], b["y"]),
            (b["x"] + b["w"], b["y"] + b["h"]),
            meta_color,
            2,
        )

    return overlay
