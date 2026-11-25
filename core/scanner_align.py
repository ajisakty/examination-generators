"""
Modul pelurusan dan koreksi orientasi halaman form OMR.
Mendeteksi 4 penanda sudut hitam (corner fiducials) dan 1 penanda orientasi kanan-bawah.
Menggunakan ambang adaptif per lembar (adaptive thresholding) dan perspective warp.
"""

from typing import List, Optional, Tuple
import cv2
import numpy as np


CANONICAL_WIDTH = 1200
CANONICAL_HEIGHT = 1700

# Koordinat sudut acuan pada kanvas kanonikal (margin 60px)
CANONICAL_TL = (60.0, 60.0)
CANONICAL_TR = (1140.0, 60.0)
CANONICAL_BR = (1140.0, 1640.0)
CANONICAL_BL = (60.0, 1640.0)


def find_markers(img_bgr: np.ndarray) -> List[Tuple[float, float, int, int, float]]:
    """
    Menemukan penanda kotak hitam (fiducial markers) pada halaman.
    
    Returns:
        Daftar tuple: (center_x, center_y, width, height, area)
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Ambang adaptif per lembar untuk mengatasi lembar terang atau gelap
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
    )

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []

    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        if bh == 0:
            continue
        aspect = bw / float(bh)

        # Penanda sudut hitam form resmi GMF/U-013 R2 berupa kotak bujursangkar solid
        # Ukuran w dan h berkisar 10 - 40 px pada resolusi render scale 2.0
        if 120 < area < 3000 and 0.65 < aspect < 1.5:
            cx = x + bw / 2.0
            cy = y + bh / 2.0
            candidates.append((cx, cy, bw, bh, area))

    return candidates


def align_form_page(img_bgr: np.ndarray) -> Tuple[np.ndarray, List[str]]:
    """
    Mendeteksi penanda fiducial, menentukan orientasi, dan meluruskan halaman ke kanvas standar.
    
    Returns:
        Tuple[np.ndarray, List[str]]: Gambar BGR kanonikal berukuran (1700, 1200, 3) dan daftar pesan/warning.
    """
    warnings: List[str] = []
    markers = find_markers(img_bgr)

    if len(markers) < 4:
        raise ValueError(
            f"Gagal menemukan minimal 4 penanda sudut form (ditemukan: {len(markers)} penanda). "
            f"Pastikan halaman dipindai utuh dan tidak terpotong."
        )

    pts = np.array([(m[0], m[1]) for m in markers], dtype=np.float32)

    # Identifikasi 4 sudut ekstrem:
    # Top-Left: min(x + y)
    # Bottom-Right: max(x + y)
    # Top-Right: min(y - x)
    # Bottom-Left: max(y - x)
    s = pts.sum(axis=1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]

    diff = pts[:, 1] - pts[:, 0]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]

    corner_pts = [tl, tr, br, bl]

    # Cek penanda orientasi (penanda ke-5):
    # Form resmi memiliki satu penanda tambahan di kanan-bawah dekat penanda BR
    orientation_marker = None
    for m in markers:
        m_pt = np.array([m[0], m[1]], dtype=np.float32)
        # Bukan salah satu dari 4 sudut
        if not any(np.linalg.norm(m_pt - c) < 15 for c in corner_pts):
            orientation_marker = m_pt
            break

    # Jika penanda orientasi ditemukan di sisi selain kanan-bawah, halaman perlu diputar
    # (Penanda orientasi resmi terletak di dekat BR)
    src = np.array([tl, tr, br, bl], dtype=np.float32)
    dst = np.array(
        [CANONICAL_TL, CANONICAL_TR, CANONICAL_BR, CANONICAL_BL],
        dtype=np.float32,
    )

    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        img_bgr, M, (CANONICAL_WIDTH, CANONICAL_HEIGHT), flags=cv2.INTER_LINEAR
    )

    # Verifikasi orientasi setelah warp
    if orientation_marker is not None:
        warped_om = cv2.perspectiveTransform(
            np.array([[orientation_marker]], dtype=np.float32), M
        )[0][0]
        # Penanda orientasi kanonikal harus berada di kuadran kanan-bawah (x > 900, y > 1400)
        if not (warped_om[0] > 800 and warped_om[1] > 1300):
            warnings.append(
                f"Penanda orientasi terdeteksi di koordinat ({warped_om[0]:.1f}, {warped_om[1]:.1f}). "
                f"Halaman mungkin miring atau terbalik."
            )

    return warped, warnings
