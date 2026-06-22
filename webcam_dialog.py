"""
webcam_dialog.py
Webcam-based dice reader for Derby Dash.

Detection pipeline
──────────────────
1.  _find_die_candidates()  – multi-method (Canny / Otsu / adaptive) rectangle
                              detection to locate each die face in the frame.
2.  _classify_roi()         – if reference photos were loaded, compare the ROI
                              against augmented templates using normalised
                              cross-correlation (NCC).  This is the primary
                              classifier because it knows exactly what THESE
                              dice look like.
3.  _count_pips()           – fallback: blob/contour/Hough pip counting.
4.  Combined result:        – template result wins when NCC confidence ≥ 0.50;
                              falls back to pip count when confidence is lower.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QSlider,
    QSpinBox, QVBoxLayout, QWidget,
)

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    cv2 = None       # type: ignore
    np = None        # type: ignore
    OPENCV_AVAILABLE = False

# ── Default reference-image folder ───────────────────────────────────────────
_DEFAULT_TEMPLATE_DIR = r"C:\Users\mattwenning\Pictures\Camera Roll"
_TEMPLATE_SIZE        = (64, 64)

# Module-level stores populated by load_reference_images()
_TEMPLATES:     Dict[int, List] = {}   # {face: [36 augmented 64×64 grayscale imgs]}
_HOG_FEATURES:  Dict[int, List] = {}   # {face: [36 flattened HOG vectors]}
_TEMPLATE_SOURCE: str = ""


# ── HOG descriptor (shared, lazy-initialised) ─────────────────────────────────

_HOG_DESC = None

def _get_hog():
    global _HOG_DESC
    if _HOG_DESC is None and OPENCV_AVAILABLE:
        _HOG_DESC = cv2.HOGDescriptor(
            _winSize=(64, 64), _blockSize=(16, 16), _blockStride=(8, 8),
            _cellSize=(8, 8),  _nbins=9)
    return _HOG_DESC


# ── Webcam config (persists default camera selection) ─────────────────────────

def _config_path() -> Path:
    base = (Path(sys.executable).parent
            if getattr(sys, 'frozen', False) else Path(__file__).parent)
    return base / 'webcam_config.json'

def _load_webcam_config() -> Dict:
    try:
        with open(_config_path(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_webcam_config(data: Dict) -> None:
    try:
        existing = _load_webcam_config()
        existing.update(data)
        with open(_config_path(), 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass


# ── Template loading ──────────────────────────────────────────────────────────

def _crop_die_face(img) -> Optional[object]:
    """
    Try to locate the die face in a reference photo.
    Returns a BGR crop if found, otherwise the whole image.
    """
    candidates = _find_die_candidates(img)
    if not candidates:
        h, w = img.shape[:2]
        side = min(h, w)
        cy, cx = h // 2, w // 2
        return img[cy - side//2 : cy + side//2, cx - side//2 : cx + side//2]
    # Use the largest candidate (most likely to be the die face)
    best = max(candidates, key=lambda r: r[2] * r[3])
    x, y, bw, bh = best
    fh, fw = img.shape[:2]
    pad = max(4, int(min(bw, bh) * 0.06))
    return img[max(0, y-pad):min(fh, y+bh+pad), max(0, x-pad):min(fw, x+bw+pad)]


def _normalize_die_patch(gray) -> np.ndarray:
    """
    Lighting-invariant normalization: min-max stretch + bilateral smoothing.
    This makes live frames look much closer to reference photos regardless of
    ambient light level.
    """
    # Min-max stretch to full 0-255 range
    mn, mx = float(gray.min()), float(gray.max())
    if mx > mn:
        gray = np.clip((gray.astype(np.float32) - mn) / (mx - mn) * 255, 0, 255).astype(np.uint8)
    # Bilateral filter: smooths noise but keeps pip edges sharp
    gray = cv2.bilateralFilter(gray, d=7, sigmaColor=40, sigmaSpace=40)
    return gray


def _edge_map(gray64) -> np.ndarray:
    """Canny edge map of a 64×64 patch, normalized 0-255."""
    edges = cv2.Canny(gray64, 20, 80)
    return edges


def _augment_template(gray64) -> List:
    """
    Generate 54 augmented 64×64 grayscale variants per die face:
    9 rotations (every 40°) × 3 brightness × 2 (original + edge-normalized).
    Edge-normalized variants allow lighting-invariant matching.
    """
    results = []
    for angle in range(0, 360, 40):          # 9 rotations
        if angle == 0:
            rot = gray64
        else:
            M   = cv2.getRotationMatrix2D((32, 32), float(angle), 1.0)
            rot = cv2.warpAffine(gray64, M, _TEMPLATE_SIZE)
        for alpha in (0.70, 1.0, 1.35):      # dark / normal / bright
            adj = np.clip(rot.astype(np.float32) * alpha, 0, 255).astype(np.uint8)
            results.append(adj)
            # Also add an edge-map variant for lighting-invariant matching
            results.append(_edge_map(adj))
    return results   # 54 variants (9 × 3 × 2)


def load_reference_images(folder: str) -> Tuple[int, str]:
    """
    Scan *folder* for files named 1–6 (any image extension), load each,
    try to crop the die face, apply CLAHE, resize to 64×64, and build
    augmented template banks.

    Returns (n_loaded, status_message).
    """
    global _TEMPLATE_SOURCE
    _TEMPLATES.clear()
    _HOG_FEATURES.clear()

    if not OPENCV_AVAILABLE:
        return 0, "OpenCV not available — templates not loaded"

    p = Path(folder)
    if not p.is_dir():
        return 0, f"Folder not found: {folder}"

    extensions = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif",
                  ".JPG", ".JPEG", ".PNG", ".BMP")
    loaded = 0

    for value in range(1, 7):
        img_path: Optional[Path] = None
        for ext in extensions:
            candidate = p / f"{value}{ext}"
            if candidate.exists():
                img_path = candidate
                break

        if img_path is None:
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            continue

        crop = _crop_die_face(img)
        if crop is None or crop.size == 0:
            continue

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = _normalize_die_patch(gray)
        gray = cv2.resize(gray, _TEMPLATE_SIZE)

        _TEMPLATES[value] = _augment_template(gray)

        # Pre-compute HOG only for intensity templates (every other, at indices 0,2,4,...)
        hog = _get_hog()
        if hog:
            _HOG_FEATURES[value] = [
                hog.compute(_TEMPLATES[value][i]).flatten()
                for i in range(0, len(_TEMPLATES[value]), 2)
            ]
        loaded += 1

    _TEMPLATE_SOURCE = str(p) if loaded else ""
    status = (f"{loaded}/6 dice templates + HOG features loaded from ...{p.name}"
              if loaded else "No template images found in selected folder")
    return loaded, status


# ── NMS helper ────────────────────────────────────────────────────────────────

def _nms(rects: List[Tuple[int,int,int,int]], iou_thresh: float = 0.35) \
        -> List[Tuple[int,int,int,int]]:
    rects = sorted(set(rects), key=lambda r: r[2]*r[3], reverse=True)
    kept: List[Tuple[int,int,int,int]] = []
    while rects:
        best = rects.pop(0)
        kept.append(best)
        bx, by, bw, bh = best
        survivors = []
        for r in rects:
            rx, ry, rw, rh = r
            ix1, iy1 = max(bx, rx), max(by, ry)
            ix2, iy2 = min(bx+bw, rx+rw), min(by+bh, ry+rh)
            if ix2 <= ix1 or iy2 <= iy1:
                survivors.append(r)
                continue
            inter  = (ix2-ix1)*(iy2-iy1)
            union  = bw*bh + rw*rh - inter
            if union <= 0 or inter/union < iou_thresh:
                survivors.append(r)
        rects = survivors
    return kept


# ── Die face detection ────────────────────────────────────────────────────────

def _find_die_candidates(frame) -> List[Tuple[int,int,int,int]]:
    fh, fw = frame.shape[:2]
    fa   = fh * fw
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)
    blur  = cv2.GaussianBlur(gray, (5, 5), 0)

    found: List[Tuple[int,int,int,int]] = []

    def _check(cnt):
        area = cv2.contourArea(cnt)
        if not (fa * 0.002 <= area <= fa * 0.35):
            return None
        peri = cv2.arcLength(cnt, True)
        if peri == 0:
            return None
        rx, ry, rw, rh = cv2.boundingRect(cnt)
        if rh == 0:
            return None
        if not (0.45 <= rw/rh <= 1.90):
            return None
        if area / (rw * rh) < 0.30:
            return None
        hull_area = cv2.contourArea(cv2.convexHull(cnt))
        if hull_area > 0 and area / hull_area < 0.50:
            return None
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if not (3 <= len(approx) <= 12):
            return None
        return (rx, ry, rw, rh)

    # Canny at three sigma levels
    median = float(np.median(blur))
    for sigma in (0.25, 0.4, 0.6):
        lo = max(10, int(median * (1 - sigma)))
        hi = min(255, int(median * (1 + sigma)))
        edges = cv2.Canny(blur, lo, hi)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
        for cnt in cv2.findContours(edges, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)[0]:
            r = _check(cnt)
            if r:
                found.append(r)

    # Global Otsu — both polarities
    for flags in (cv2.THRESH_BINARY + cv2.THRESH_OTSU,
                  cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU):
        _, binary = cv2.threshold(blur, 0, 255, flags)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                                  np.ones((7, 7), np.uint8), iterations=2)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                                  np.ones((3, 3), np.uint8), iterations=1)
        for cnt in cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)[0]:
            r = _check(cnt)
            if r:
                found.append(r)

    # Adaptive threshold — three block sizes
    for block, c in ((21, 5), (31, 8), (11, 3)):
        adapt = cv2.adaptiveThreshold(blur, 255,
                                       cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, block, c)
        adapt = cv2.morphologyEx(adapt, cv2.MORPH_OPEN,
                                 np.ones((3, 3), np.uint8), iterations=1)
        adapt = cv2.morphologyEx(adapt, cv2.MORPH_CLOSE,
                                 np.ones((5, 5), np.uint8), iterations=2)
        for cnt in cv2.findContours(adapt, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)[0]:
            r = _check(cnt)
            if r:
                found.append(r)

    # ── Method 4: HSV white-region detection ─────────────────────────────────
    # Try two ranges: standard white dice and slightly off-white/cream dice
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    for lo_v, hi_s in ((140, 80), (120, 100), (160, 55)):
        lo = np.array([0,   0,   lo_v], dtype=np.uint8)
        hi = np.array([179, hi_s, 255], dtype=np.uint8)
        wmask = cv2.inRange(hsv, lo, hi)
        wmask = cv2.morphologyEx(wmask, cv2.MORPH_CLOSE,
                                 np.ones((9, 9), np.uint8), iterations=2)
        wmask = cv2.morphologyEx(wmask, cv2.MORPH_OPEN,
                                 np.ones((5, 5), np.uint8), iterations=1)
        for cnt in cv2.findContours(wmask, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)[0]:
            r = _check(cnt)
            if r:
                found.append(r)

    # ── Method 5: Bright-spot relative to surroundings ────────────────────────
    # Finds regions brighter than their local neighbourhood — works when die
    # colour is close to background but still slightly brighter.
    kernel_size = max(31, min(fh, fw) // 12)
    if kernel_size % 2 == 0:
        kernel_size += 1
    local_mean = cv2.GaussianBlur(gray.astype(np.float32),
                                  (kernel_size, kernel_size), 0)
    bright_rel = np.clip(gray.astype(np.float32) - local_mean + 30, 0, 255).astype(np.uint8)
    _, bright_mask = cv2.threshold(bright_rel, 25, 255, cv2.THRESH_BINARY)
    bright_mask = cv2.morphologyEx(bright_mask, cv2.MORPH_CLOSE,
                                   np.ones((11, 11), np.uint8), iterations=2)
    bright_mask = cv2.morphologyEx(bright_mask, cv2.MORPH_OPEN,
                                   np.ones((5,  5),  np.uint8), iterations=1)
    for cnt in cv2.findContours(bright_mask, cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)[0]:
        r = _check(cnt)
        if r:
            found.append(r)

    return _nms(found)


# ── Template-based classification ─────────────────────────────────────────────

def _classify_roi(roi) -> Tuple[int, float]:
    """
    Multi-method template matching:
      - NCC on normalized intensity patch (good when lighting matches)
      - NCC on edge map (lighting invariant)
      - HOG cosine similarity (structure/shape invariant)
    All three are combined; best-matching face value wins.
    """
    if not _TEMPLATES or roi is None or roi.size == 0:
        return 0, 0.0
    if min(roi.shape[:2]) < 18:
        return 0, 0.0

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi.copy()
    gray = _normalize_die_patch(gray)
    gray = cv2.resize(gray, _TEMPLATE_SIZE)

    # Edge map of live ROI — lighting invariant
    roi_edges = _edge_map(gray)

    # HOG of live ROI
    hog          = _get_hog()
    roi_hog      = None
    roi_hog_norm = 0.0
    if hog and _HOG_FEATURES:
        try:
            roi_hog      = hog.compute(gray).flatten()
            roi_hog_norm = float(np.linalg.norm(roi_hog))
        except Exception:
            roi_hog = None

    best_val, best_score = 0, -1.0

    for value, tmpls in _TEMPLATES.items():
        hog_feats = _HOG_FEATURES.get(value, [])
        val_score = -1.0

        # Templates alternate: [intensity_0, edge_0, intensity_1, edge_1, ...]
        for i in range(0, len(tmpls), 2):
            tmpl_intensity = tmpls[i]
            tmpl_edge      = tmpls[i + 1] if i + 1 < len(tmpls) else None

            ncc_intensity = float(cv2.matchTemplate(
                gray, tmpl_intensity, cv2.TM_CCOEFF_NORMED)[0, 0])

            ncc_edge = 0.0
            if tmpl_edge is not None:
                ncc_edge = float(cv2.matchTemplate(
                    roi_edges, tmpl_edge, cv2.TM_CCOEFF_NORMED)[0, 0])

            # HOG similarity (use the intensity template's HOG features)
            hog_sim = 0.0
            hog_idx = i // 2  # every other template pair shares a HOG index
            if (roi_hog is not None and roi_hog_norm > 1e-8
                    and hog_idx < len(hog_feats)):
                hf      = hog_feats[hog_idx]
                hf_norm = float(np.linalg.norm(hf))
                if hf_norm > 1e-8:
                    hog_sim = float(np.dot(roi_hog, hf)) / (roi_hog_norm * hf_norm)

            # Weighted combination: intensity 45% + edge 35% + HOG 20%
            # Edge NCC is most lighting-invariant so gets strong weight
            score = 0.45 * ncc_intensity + 0.35 * ncc_edge + 0.20 * hog_sim

            if score > val_score:
                val_score = score

        if val_score > best_score:
            best_score, best_val = val_score, value

    return best_val, max(0.0, best_score)


# ── Pip counting (fallback) ───────────────────────────────────────────────────

def _count_pips_in_mask(mask, border: int, h: int, w: int) -> int:
    roi_area = h * w
    min_pip  = max(8, roi_area * 0.0012)
    max_pip  = max(min_pip + 1, roi_area * 0.09)

    p = cv2.SimpleBlobDetector_Params()
    p.filterByArea        = True;  p.minArea       = min_pip; p.maxArea = max_pip
    p.filterByCircularity = True;  p.minCircularity = 0.30
    p.filterByColor       = True;  p.blobColor     = 255
    p.filterByConvexity   = False; p.filterByInertia = False
    kps = cv2.SimpleBlobDetector_create(p).detect(mask)
    c_blob = sum(1 for kp in kps
                 if (border < kp.pt[0] - kp.size/2 and kp.pt[0] + kp.size/2 < w - border and
                     border < kp.pt[1] - kp.size/2 and kp.pt[1] + kp.size/2 < h - border))

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c_cnt = 0
    for cnt in cnts:
        a = cv2.contourArea(cnt)
        if not (min_pip <= a <= max_pip):
            continue
        peri = cv2.arcLength(cnt, True)
        if peri == 0:
            continue
        if (4 * 3.14159 * a / peri**2) < 0.28:
            continue
        rx, ry, rw, rh = cv2.boundingRect(cnt)
        if (border < rx and rx+rw < w-border and border < ry and ry+rh < h-border):
            c_cnt += 1

    min_r   = max(2, min(h, w) // 20)
    max_r   = max(min_r + 2, min(h, w) // 5)
    circles = cv2.HoughCircles(mask, cv2.HOUGH_GRADIENT, dp=1.2,
                               minDist=max(min_r * 2, 5), param1=25, param2=8,
                               minRadius=min_r, maxRadius=max_r)
    c_hough = 0
    if circles is not None:
        c_hough = sum(1 for c in circles[0]
                      if (border < c[0]-c[2] and c[0]+c[2] < w-border and
                          border < c[1]-c[2] and c[1]+c[2] < h-border))

    votes = [v for v in (c_blob, c_cnt, c_hough) if 1 <= v <= 6]
    if not votes:
        return 0, 0
    winner, freq = Counter(votes).most_common(1)[0]
    return winner, freq          # (value, number_of_methods_that_agreed)


def _count_pips_blackhat(gray: np.ndarray, b: int) -> int:
    """
    Morphological black-hat: finds dark blobs (pips) on a bright background.
    More robust than blob/Hough under uneven lighting.
    Works for dark pips on white/ivory dice.
    """
    h, w   = gray.shape
    k_size = max(5, min(h, w) // 5)
    if k_size % 2 == 0:
        k_size += 1
    kernel   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    _, thr   = cv2.threshold(blackhat, 22, 255, cv2.THRESH_BINARY)
    thr[:b, :] = thr[-b:, :] = thr[:, :b] = thr[:, -b:] = 0
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    roi_area = h * w
    min_pip  = max(6, roi_area * 0.001)
    max_pip  = max(min_pip + 1, roi_area * 0.07)
    cnts, _  = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    count = 0
    for cnt in cnts:
        a = cv2.contourArea(cnt)
        if not (min_pip <= a <= max_pip):
            continue
        peri = cv2.arcLength(cnt, True)
        if peri > 0 and (4 * 3.14159 * a / peri**2) > 0.28:
            count += 1
    return count


def _count_pips(roi) -> Tuple[int, float]:
    """
    Count pips using 4 methods with majority vote:
      1. SimpleBlobDetector  2. Contour filter  3. HoughCircles  4. Black-hat morphology
    Confidence reflects agreement: 4/4→0.95 | 3/4→0.82 | 2/4→0.60 | 1/4→0.40
    """
    if not OPENCV_AVAILABLE or roi is None or roi.size == 0:
        return 0, 0.0
    if min(roi.shape[:2]) < 18:
        return 0, 0.0

    gray  = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    gray  = clahe.apply(gray)
    gray  = cv2.GaussianBlur(gray, (3, 3), 0)
    h, w  = gray.shape
    b     = max(3, int(min(h, w) * 0.09))
    _CONF = {4: 0.95, 3: 0.82, 2: 0.60, 1: 0.40}

    for inv in (True, False):
        flags = (cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU if inv
                 else cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, mask = cv2.threshold(gray, 0, 255, flags)
        mask[:b, :] = mask[-b:, :] = mask[:, :b] = mask[:, -b:] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                                np.ones((2, 2), np.uint8), iterations=1)
        blob_val, votes = _count_pips_in_mask(mask, b, h, w)

        # Add black-hat result as 4th voter (works even when threshold fails)
        bh_val = _count_pips_blackhat(gray, b)

        all_votes = [v for v in (blob_val if votes > 0 else 0, bh_val) if 1 <= v <= 6]
        if votes > 0 and 1 <= blob_val <= 6:
            all_votes = [blob_val] * votes + ([bh_val] if 1 <= bh_val <= 6 else [])
        elif 1 <= bh_val <= 6:
            all_votes = [bh_val]

        if all_votes:
            winner, freq = Counter(all_votes).most_common(1)[0]
            if 1 <= winner <= 6:
                return winner, _CONF.get(min(freq, 4), 0.40)

    return 0, 0.0


# ── Combined classifier ───────────────────────────────────────────────────────

def _detect_die_value(roi) -> Tuple[int, float, str]:
    """
    Returns (face_value, confidence 0-1, method_label).
    Template matching wins when NCC >= 0.40 or it beats pip confidence.
    """
    tmpl_val, tmpl_conf = _classify_roi(roi)
    pip_val,  pip_conf  = _count_pips(roi)

    # Hard gate: if no pips detected at all, demand very high template confidence.
    # This stops blank/flat white objects from being accepted on template match alone.
    if pip_val == 0 and tmpl_conf < 0.65:
        return 0, 0.0, "?"

    # Strong template match — trust it
    if tmpl_conf >= 0.55 and tmpl_val > 0:
        return tmpl_val, tmpl_conf, "template"
    # Both methods agree — high confidence even if individual scores are modest
    if tmpl_val > 0 and pip_val > 0 and tmpl_val == pip_val:
        combined = min(0.95, (tmpl_conf + pip_conf) / 2 + 0.10)
        return tmpl_val, combined, "template+pips"
    # Both have signal but disagree — pick the more confident one (higher bar)
    if tmpl_val > 0 and pip_val > 0:
        if tmpl_conf >= 0.52 and tmpl_conf >= pip_conf:
            return tmpl_val, tmpl_conf, "template"
        if pip_conf >= 0.60:
            return pip_val, pip_conf, "pips"
    # Template only — need higher threshold since no pip confirmation
    if tmpl_conf >= 0.55 and tmpl_val > 0:
        return tmpl_val, tmpl_conf, "template"
    # Pip only — need decent confidence
    if pip_val > 0 and pip_conf >= 0.60:
        return pip_val, pip_conf, "pips"
    # Nothing reliable enough
    return 0, 0.0, "?"


def _is_die_like(roi) -> bool:
    """
    Quick sanity checks before spending time on template matching.
    Returns False for anything that clearly isn't a white/cream die face.
    """
    if roi is None or roi.size == 0:
        return False
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    mean_brightness = float(np.mean(gray))
    # Dice are white/cream — reject clearly dark objects
    if mean_brightness < 85:
        return False
    # Must not be nearly all black
    bright_pixels = float(np.sum(gray > 70)) / gray.size
    if bright_pixels < 0.35:
        return False
    std = float(np.std(gray))
    # Reject only very extreme cases:
    # - Nearly uniform solid colour (std < 5): blank wall/paper with no pips
    # - Wildly complex texture (std > 95): tablecloth, carpet, etc.
    if std < 5 or std > 95:
        return False
    # Must have some dark pixels relative to the mean — the pips.
    # A die face always has at least 1 pip (~1% dark area minimum).
    dark_pixels = float(np.sum(gray < mean_brightness * 0.70)) / gray.size
    if dark_pixels < 0.008:
        return False
    return True


# ── Main analysis pipeline ────────────────────────────────────────────────────

def _analyze_frame(frame) -> Tuple[List[Dict], List[Dict]]:
    if not OPENCV_AVAILABLE or frame is None:
        return [], []

    fh, fw        = frame.shape[:2]
    cand_rects    = _find_die_candidates(frame)
    detections:  List[Dict] = []
    candidates:  List[Dict] = []

    for (x, y, rw, rh) in cand_rects:
        pad    = max(4, int(min(rw, rh) * 0.06))
        x1, y1 = max(0, x-pad),   max(0, y-pad)
        x2, y2 = min(fw, x+rw+pad), min(fh, y+rh+pad)
        roi    = frame[y1:y2, x1:x2]

        # Fast reject: must look like a white/bright die face
        if not _is_die_like(roi):
            continue

        val, conf, method = _detect_die_value(roi)
        candidates.append({'rect': (x, y, rw, rh), 'pips': val,
                           'conf': conf, 'method': method, 'area': rw*rh})
        if 1 <= val <= 6:
            detections.append({'value': val, 'conf': conf,
                               'method': method, 'rect': (x, y, rw, rh)})

    # Auto-select top-2 by confidence, then re-sort left-to-right (left die first)
    detections.sort(key=lambda d: d['conf'], reverse=True)
    top2 = detections[:2]
    top2.sort(key=lambda d: d['rect'][0])
    candidates.sort(key=lambda d: d['rect'][0])
    return top2, candidates


# ── Confidence bar widget ─────────────────────────────────────────────────────

from PyQt6.QtGui import QColor, QFont, QPainter  # noqa: E402 (already imported above)

class ConfidenceBar(QWidget):
    """Compact horizontal bar showing die value and confidence %."""
    def __init__(self, die_label: str, parent=None):
        super().__init__(parent)
        self._die   = die_label
        self._val   = 0
        self._conf  = 0.0
        self._meth  = ''
        self.setFixedHeight(26)
        self.setMinimumWidth(200)

    def update_value(self, val: int, conf: float, method: str = ''):
        self._val  = val
        self._conf = max(0.0, min(1.0, conf))
        self._meth = method
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bar_y, bar_h = 5, h - 10

        # Track
        p.setBrush(QColor(30, 50, 30));  p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, bar_y, w, bar_h, 4, 4)

        # Fill — colour by confidence level
        fill = int(w * self._conf)
        if fill > 0:
            if self._conf >= 0.70:   col = QColor(50, 200, 70)
            elif self._conf >= 0.45: col = QColor(220, 185, 30)
            else:                    col = QColor(210, 60, 60)
            p.setBrush(col)
            p.drawRoundedRect(0, bar_y, fill, bar_h, 4, 4)

        # Text
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont('Georgia', 9, QFont.Weight.Bold))
        die_str = f"Die {self._die}: " + (f"[ {self._val} ]" if self._val else "[ ? ]")
        pct_str = f"  {int(self._conf * 100)}%"
        meth    = f"  {self._meth}" if self._meth else ''
        p.drawText(6, 0, w - 8, h, Qt.AlignmentFlag.AlignVCenter,
                   die_str + pct_str + meth)


# ── Dialog ────────────────────────────────────────────────────────────────────

class WebcamDialog(QDialog):
    dice_detected = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Webcam Dice Reader')
        self.setModal(False)
        self.capture: Optional[object]      = None
        self.current_frame                  = None
        self.current_detections: List[Dict] = []
        self.camera_available               = False
        self.is_frozen                      = False

        # ── Cooldown state ─────────────────────────────────────────────────
        self._in_cooldown        = False
        self._cooldown_remaining = 0          # seconds left

        # ── Temporal stability buffer ──────────────────────────────────────
        # Stores last N frame-readings as (d1_val, d2_val) sorted ascending.
        # A result is "stable" when the same pair appears in >= _STABLE_NEEDED
        # of the last _STABLE_WINDOW frames. Prevents single-frame false positives.
        self._STABLE_WINDOW  = 8
        self._STABLE_NEEDED  = 6
        self._stable_buffer: deque = deque(maxlen=self._STABLE_WINDOW)
        self._stable_progress = 0   # how many consecutive matching frames

        self._live_timer = QTimer(self)        # camera frames (50 ms)
        self._live_timer.setInterval(50)
        self._live_timer.timeout.connect(self._update_frame)

        # Alias used by open_camera / release_camera
        self.timer = self._live_timer

        self._cd_timer = QTimer(self)          # 1-second cooldown ticks
        self._cd_timer.setInterval(1000)
        self._cd_timer.setSingleShot(False)
        self._cd_timer.timeout.connect(self._cooldown_tick)

        self._build_ui()
        self._apply_styles()
        self._populate_cameras()

        # Size to 88% of available screen, centred — no hard minimum so it
        # always fits regardless of monitor resolution.
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        dlg_w  = min(screen.width()  - 40, max(760, int(screen.width()  * 0.72)))
        dlg_h  = min(screen.height() - 40, max(560, int(screen.height() * 0.88)))
        self.resize(dlg_w, dlg_h)
        self.move(screen.x() + (screen.width()  - dlg_w) // 2,
                  screen.y() + (screen.height() - dlg_h) // 2)

        # Auto-load templates from default folder
        if OPENCV_AVAILABLE:
            n, msg = load_reference_images(_DEFAULT_TEMPLATE_DIR)
            self._set_template_status(msg, n)
            default_cam = _load_webcam_config().get('default_camera', 0)
            self.open_camera(default_cam)
        else:
            self.capture_button.setEnabled(False)
            self.camera_combo.setEnabled(False)
            self.status_label.setText('OpenCV not installed — use manual entry below')
            self.feed_label.setText('OpenCV not installed\n\nUse manual dice entry below')

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 10)
        root.setSpacing(7)

        root.addWidget(self._make_title())

        # Camera selector
        cam_row = QHBoxLayout()
        cam_row.addWidget(QLabel('Camera:'))
        self.camera_combo = QComboBox()
        cam_row.addWidget(self.camera_combo, 1)
        self.set_default_btn = QPushButton('Set as Default')
        self.set_default_btn.setFixedWidth(115)
        self.set_default_btn.setToolTip('Save this camera as the one that opens automatically')
        self.set_default_btn.clicked.connect(self._set_default_camera)
        cam_row.addWidget(self.set_default_btn)
        self.debug_chk = QCheckBox('Show candidates')
        self.debug_chk.setChecked(False)
        cam_row.addWidget(self.debug_chk)
        root.addLayout(cam_row)

        # Live feed — small safety minimum; takes all spare vertical space
        self.feed_label = QLabel('Starting camera...')
        self.feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feed_label.setMinimumSize(320, 240)   # bare minimum — dialog handles sizing
        from PyQt6.QtWidgets import QSizePolicy
        self.feed_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.feed_label.setObjectName('feedLabel')
        root.addWidget(self.feed_label, stretch=1)

        # Confidence bars (one per die)
        conf_row = QHBoxLayout()
        conf_row.setSpacing(10)
        self.conf_bar1 = ConfidenceBar('1')
        self.conf_bar2 = ConfidenceBar('2')
        conf_row.addWidget(self.conf_bar1, 1)
        conf_row.addWidget(self.conf_bar2, 1)
        root.addLayout(conf_row)

        # Auto-submit row
        auto_row = QHBoxLayout()
        self.auto_chk = QCheckBox('Auto-submit when both dice confidence >=')
        self.auto_chk.setChecked(True)
        self.auto_slider = QSlider(Qt.Orientation.Horizontal)
        self.auto_slider.setRange(20, 90)
        self.auto_slider.setValue(65)
        self.auto_slider.setFixedWidth(110)
        self.auto_thresh_lbl = QLabel('65%')
        self.auto_thresh_lbl.setFixedWidth(34)
        self.auto_slider.valueChanged.connect(
            lambda v: self.auto_thresh_lbl.setText(f'{v}%'))
        auto_row.addWidget(self.auto_chk)
        auto_row.addWidget(self.auto_slider)
        auto_row.addWidget(self.auto_thresh_lbl)
        auto_row.addStretch()
        root.addLayout(auto_row)

        # Stability + Cooldown row
        sc_row = QHBoxLayout()
        sc_row.addWidget(QLabel('Stability frames:'))
        self.stable_spin = QSpinBox()
        self.stable_spin.setRange(1, 10)
        self.stable_spin.setValue(6)
        self.stable_spin.setToolTip(
            'How many consecutive matching frames are required before auto-submitting.\n'
            'Higher = more reliable but slightly slower response.')
        self.stable_spin.setFixedWidth(52)
        self.stable_spin.valueChanged.connect(
            lambda v: setattr(self, '_STABLE_NEEDED', v))
        sc_row.addWidget(self.stable_spin)
        sc_row.addSpacing(20)
        sc_row.addWidget(QLabel('Cooldown between rolls:'))
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(2, 15)
        self.cooldown_spin.setValue(5)
        self.cooldown_spin.setSuffix(' s')
        self.cooldown_spin.setFixedWidth(68)
        sc_row.addWidget(self.cooldown_spin)
        sc_row.addStretch()
        root.addLayout(sc_row)

        # Status / method labels
        self.status_label = QLabel('Status: Searching for dice...')
        self.method_label = QLabel('')
        self.method_label.setStyleSheet('color: #90C890; font-size: 11px;')
        root.addWidget(self.status_label)
        root.addWidget(self.method_label)

        # Action buttons
        btn_row = QHBoxLayout()
        self.capture_button    = QPushButton('Capture & Detect')
        self.use_result_button = QPushButton('Use Result')
        self.save_frame_button = QPushButton('Save Frame')
        self.save_frame_button.setToolTip('Save current frame for debugging / new reference photos')
        self.use_result_button.setObjectName('useResultButton')
        self.use_result_button.setEnabled(False)
        self.capture_button.clicked.connect(self.capture_and_detect)
        self.use_result_button.clicked.connect(self.use_detected_result)
        self.save_frame_button.clicked.connect(self._save_debug_frame)
        btn_row.addWidget(self.capture_button)
        btn_row.addWidget(self.use_result_button)
        btn_row.addWidget(self.save_frame_button)
        root.addLayout(btn_row)

        # Template images group
        tmpl_group = QGroupBox('Reference Template Images')
        tmpl_group.setObjectName('tmplGroup')
        tl = QVBoxLayout(tmpl_group)
        tl.setSpacing(4)

        self.tmpl_status_label = QLabel('Loading templates...')
        self.tmpl_status_label.setWordWrap(True)
        tl.addWidget(self.tmpl_status_label)

        self.tmpl_folder_label = QLabel(_DEFAULT_TEMPLATE_DIR)
        self.tmpl_folder_label.setStyleSheet('color: #90A890; font-size: 10px;')
        self.tmpl_folder_label.setWordWrap(True)
        tl.addWidget(self.tmpl_folder_label)

        tmpl_btn_row = QHBoxLayout()
        reload_btn = QPushButton('Reload')
        reload_btn.setFixedWidth(72)
        browse_btn = QPushButton('Browse...')
        browse_btn.setFixedWidth(80)
        reload_btn.clicked.connect(self._reload_templates)
        browse_btn.clicked.connect(self._browse_templates)
        tmpl_btn_row.addWidget(reload_btn)
        tmpl_btn_row.addWidget(browse_btn)
        tmpl_btn_row.addStretch()
        tl.addLayout(tmpl_btn_row)
        tl.addWidget(self.tmpl_folder_label)

        # Capture-from-camera reference workflow
        cap_ref_row = QHBoxLayout()
        cap_ref_row.addWidget(QLabel('Capture die face from camera:'))
        self.cap_ref_spin = QSpinBox()
        self.cap_ref_spin.setRange(1, 6)
        self.cap_ref_spin.setValue(1)
        self.cap_ref_spin.setPrefix('Face ')
        self.cap_ref_spin.setFixedWidth(78)
        self.cap_ref_btn = QPushButton('📷 Capture')
        self.cap_ref_btn.setFixedWidth(90)
        self.cap_ref_btn.setToolTip(
            'Show this die face to the camera, then click to save it as a '
            'reference image. Do this for all 6 faces under your actual lighting.')
        self.cap_ref_btn.clicked.connect(self._capture_reference_face)
        cap_ref_row.addWidget(self.cap_ref_spin)
        cap_ref_row.addWidget(self.cap_ref_btn)
        self.cap_ref_status = QLabel('')
        self.cap_ref_status.setStyleSheet('color: #6EC86E; font-size: 11px;')
        cap_ref_row.addWidget(self.cap_ref_status)
        cap_ref_row.addStretch()
        tl.addLayout(cap_ref_row)
        root.addWidget(tmpl_group)

        # Tips
        tips = QLabel(
            '💡  Tips: place dice on a plain contrasting surface · '
            'ensure even lighting · keep dice flat and facing the camera'
        )
        tips.setWordWrap(True)
        tips.setStyleSheet('color: #90A890; font-size: 11px;')
        root.addWidget(tips)

        # Manual override
        manual = QGridLayout()
        manual.addWidget(QLabel('Manual override:'), 0, 0)
        manual.addWidget(QLabel('Die 1'), 0, 1)
        self.manual_die1 = QSpinBox()
        self.manual_die1.setRange(1, 6)
        manual.addWidget(self.manual_die1, 0, 2)
        manual.addWidget(QLabel('Die 2'), 0, 3)
        self.manual_die2 = QSpinBox()
        self.manual_die2.setRange(1, 6)
        manual.addWidget(self.manual_die2, 0, 4)
        use_manual = QPushButton('Use Manual')
        use_manual.clicked.connect(self.use_manual_result)
        manual.addWidget(use_manual, 0, 5)
        root.addLayout(manual)

        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.close)
        root.addWidget(close_btn)

        self.camera_combo.currentIndexChanged.connect(self.switch_camera)

    def _make_title(self) -> QLabel:
        lbl = QLabel('🎲  Webcam Dice Reader')
        lbl.setObjectName('titleLabel')
        return lbl

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog { background: #1A2420; }
            QLabel  { color: white; font-size: 13px; }
            QLabel#titleLabel { font-size: 18px; font-weight: bold; color: #F5D76E; }
            QLabel#feedLabel  { background: #0D1411; border: 1px solid #3A6B2A;
                                color: #888; font-size: 14px; }
            QGroupBox#tmplGroup { color: #C8A84B; font-weight: bold; font-size: 12px;
                                  border: 1px solid #3A5A2A; border-radius: 6px;
                                  margin-top: 4px; padding: 6px; }
            QGroupBox#tmplGroup::title { subcontrol-origin: margin; left: 8px;
                                         padding: 0 4px; }
            QPushButton { background: #3A6B2A; color: white; border: none;
                          border-radius: 6px; padding: 8px 14px; font-weight: bold; }
            QPushButton:hover    { background: #4E8538; }
            QPushButton:disabled { background: #2A3A2A; color: #666; }
            QPushButton#useResultButton       { background: #8B6900; color: #F0EAD6; }
            QPushButton#useResultButton:hover { background: #C8A84B; color: #0E1A14; }
            QComboBox, QSpinBox { background: #22302B; color: white;
                                  border: 1px solid #3A6B2A; border-radius: 4px;
                                  padding: 4px 6px; min-height: 26px; }
            QCheckBox { color: #A8C8A8; font-size: 12px; }
            QSlider::groove:horizontal { background: #22402A; height: 6px;
                                          border-radius: 3px; }
            QSlider::handle:horizontal { background: #C8A84B; width: 14px; height: 14px;
                                          margin: -4px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #4A9B3A; border-radius: 3px; }
        """)

    def _populate_cameras(self):
        """Scan indices 0-4 for cameras that actually open, then pre-select default."""
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()

        available = []
        if OPENCV_AVAILABLE:
            for i in range(5):
                cap = cv2.VideoCapture(i)
                if cap and cap.isOpened():
                    available.append(i)
                    cap.release()
        if not available:
            available = list(range(4))   # fallback when OpenCV unavailable

        for i in available:
            self.camera_combo.addItem(f'Camera {i}', i)

        # Pre-select saved default
        default = _load_webcam_config().get('default_camera', 0)
        for idx in range(self.camera_combo.count()):
            if self.camera_combo.itemData(idx) == default:
                self.camera_combo.setCurrentIndex(idx)
                break

        self.camera_combo.blockSignals(False)

    def _set_default_camera(self):
        idx = self.camera_combo.currentData()
        _save_webcam_config({'default_camera': idx})
        self.set_default_btn.setText('Saved!')
        QTimer.singleShot(1800, lambda: self.set_default_btn.setText('Set as Default'))

    def _set_template_status(self, msg: str, n: int):
        self.tmpl_status_label.setText(msg)
        color = '#6EC86E' if n == 6 else ('#F5D76E' if n > 0 else '#E06060')
        self.tmpl_status_label.setStyleSheet(f'color: {color}; font-size: 12px;')
        self.tmpl_folder_label.setText(_TEMPLATE_SOURCE or _DEFAULT_TEMPLATE_DIR)

    # ── Template management ────────────────────────────────────────────────────

    def _reload_templates(self):
        folder = self.tmpl_folder_label.text()
        n, msg = load_reference_images(folder)
        self._set_template_status(msg, n)

    def _browse_templates(self):
        folder = QFileDialog.getExistingDirectory(
            self, 'Select folder containing dice images (1.jpg … 6.jpg)',
            self.tmpl_folder_label.text())
        if folder:
            n, msg = load_reference_images(folder)
            self._set_template_status(msg, n)

    def _capture_reference_face(self):
        """
        Capture the current camera frame and save it as a reference image for the
        selected die face value. The ROI of the best-detected die is used; if none
        is found the full frame is saved. Reloads templates automatically.
        """
        if not OPENCV_AVAILABLE or self.current_frame is None:
            self.cap_ref_status.setText('No frame available')
            return
        value = self.cap_ref_spin.value()
        folder = Path(self.tmpl_folder_label.text())
        if not folder.is_dir():
            # Fall back to default folder, create if needed
            folder = Path(_DEFAULT_TEMPLATE_DIR)
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except Exception:
                self.cap_ref_status.setText('Cannot create folder')
                return

        # Use detected ROI if available, else full frame
        frame = self.current_frame.copy()
        saved_roi = frame
        if self.current_detections:
            # Use the highest-confidence detection's ROI
            best = max(self.current_detections, key=lambda d: d['conf'])
            x, y, w, h = best['rect']
            fh, fw = frame.shape[:2]
            pad = max(4, int(min(w, h) * 0.08))
            saved_roi = frame[max(0, y-pad):min(fh, y+h+pad),
                               max(0, x-pad):min(fw, x+w+pad)]
        else:
            # Try detecting from current frame directly
            cands = _find_die_candidates(frame)
            if cands:
                best_c = max(cands, key=lambda r: r[2] * r[3])
                x, y, w, h = best_c
                fh, fw = frame.shape[:2]
                pad = max(4, int(min(w, h) * 0.08))
                saved_roi = frame[max(0, y-pad):min(fh, y+h+pad),
                                   max(0, x-pad):min(fw, x+w+pad)]

        out_path = folder / f"{value}.jpg"
        cv2.imwrite(str(out_path), saved_roi)

        # Reload templates from the folder
        n, msg = load_reference_images(str(folder))
        self._set_template_status(msg, n)

        self.cap_ref_status.setText(f'✓ Face {value} saved!')
        # Auto-advance to next face
        if value < 6:
            self.cap_ref_spin.setValue(value + 1)
        QTimer.singleShot(2500, lambda: self.cap_ref_status.setText(''))

    # ── Camera lifecycle ───────────────────────────────────────────────────────

    def open_camera(self, index: int):
        self.release_camera()
        if not OPENCV_AVAILABLE:
            return
        cap = cv2.VideoCapture(int(index))
        if cap:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
        if not cap or not cap.isOpened():
            self.camera_available = False
            self.feed_label.setText('No camera found')
            self.status_label.setText('Status: No camera found')
            self.capture_button.setEnabled(False)
            return
        self.capture          = cap
        self.camera_available = True
        self.is_frozen        = False
        self.capture_button.setEnabled(True)
        self.capture_button.setText('📷  Capture && Detect')
        self.status_label.setText('Status: Searching for dice…')
        self.timer.start()

    def switch_camera(self, *_):
        if OPENCV_AVAILABLE:
            self.open_camera(self.camera_combo.currentData())

    def release_camera(self):
        self.timer.stop()
        if self.capture:
            self.capture.release()
            self.capture = None

    # ── Frame loop ─────────────────────────────────────────────────────────────

    def _update_frame(self):
        if not self.capture or not self.camera_available or self.is_frozen:
            return
        ok, frame = self.capture.read()
        if not ok or frame is None:
            return
        self.current_frame = frame.copy()
        try:
            if self._in_cooldown:
                self._draw_cooldown_overlay(frame)
            else:
                self._process(frame, captured=False)
        except Exception as exc:
            import traceback
            self.status_label.setText(f'Error: {exc}')
            traceback.print_exc()

    def _draw_cooldown_overlay(self, frame):
        """Show camera feed with a centred countdown banner during cooldown."""
        h, w = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, h//2 - 70), (w, h//2 + 80), (10, 20, 10), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        secs = self._cooldown_remaining
        # Scale text to frame width
        fs_big  = max(0.8, w / 640 * 1.4)
        fs_small = max(0.5, w / 640 * 0.62)
        text = f'Next roll in  {secs}s'
        (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, fs_big, 3)
        cv2.putText(frame, text, ((w - tw) // 2, h//2 + 14),
                    cv2.FONT_HERSHEY_DUPLEX, fs_big, (80, 220, 80), 3, cv2.LINE_AA)
        sub = 'Players — pick up and roll the dice'
        (tw2, _), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_SIMPLEX, fs_small, 1)
        cv2.putText(frame, sub, ((w - tw2) // 2, h//2 + int(58 * w / 640)),
                    cv2.FONT_HERSHEY_SIMPLEX, fs_small, (200, 200, 200), 1, cv2.LINE_AA)
        self._show_frame(frame)

    def _process(self, frame, captured: bool):
        dets, cands = _analyze_frame(frame)
        self.current_detections = dets
        overlay = self._draw_overlay(frame.copy(), dets, cands)
        # Debug counter on frame — helps diagnose if shapes are found at all
        h, w = overlay.shape[:2]
        dbg = f"shapes:{len(cands)}  dets:{len(dets)}"
        cv2.putText(overlay, dbg, (8, h - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, max(0.4, w / 1600),
                    (180, 255, 180), 1, cv2.LINE_AA)
        self._show_frame(overlay)
        self._update_labels(dets, cands, captured)

    def _show_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        fh, fw, ch = rgb.shape
        img = QImage(rgb.data, fw, fh, ch * fw, QImage.Format.Format_RGB888).copy()
        pix = QPixmap.fromImage(img)
        # Scale to fill the label while keeping aspect ratio
        self.feed_label.setPixmap(
            pix.scaled(self.feed_label.size(),
                       Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation))

    def _draw_overlay(self, frame, detections, candidates):
        det_map = {tuple(d['rect']): d for d in detections}
        for c in candidates:
            key  = tuple(c['rect'])
            det  = det_map.get(key)
            x, y, w, h = c['rect']
            conf = c.get('conf', 0.0)

            if det:
                # Colour by confidence: green >= 70%, yellow 45-70%, red < 45%
                if conf >= 0.70:   color = (50, 210, 50)
                elif conf >= 0.45: color = (30, 185, 220)
                else:              color = (60, 60, 210)
                label = f"Die: {det['value']}  {int(conf*100)}%  [{det['method']}]"
            elif self.debug_chk.isChecked():
                color = (0, 140, 200)
                label = f"? pips={c['pips']}  {int(conf*100)}%"
            else:
                continue

            # Bounding box
            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)

            # Confidence fill bar drawn inside the top edge of the bounding box
            bar_h    = max(5, h // 8)
            bar_fill = int(w * max(0.0, min(1.0, conf)))
            cv2.rectangle(frame, (x, y), (x+w, y+bar_h), (20, 30, 20), -1)
            if bar_fill > 0:
                cv2.rectangle(frame, (x, y), (x+bar_fill, y+bar_h), color, -1)

            cv2.putText(frame, label, (x, max(20, y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2, cv2.LINE_AA)
        return frame

    def _update_labels(self, dets, cands, captured: bool):
        d1_val  = dets[0]['value']  if len(dets) > 0 else 0
        d1_conf = dets[0]['conf']   if len(dets) > 0 else 0.0
        d1_meth = dets[0]['method'] if len(dets) > 0 else ''
        d2_val  = dets[1]['value']  if len(dets) > 1 else 0
        d2_conf = dets[1]['conf']   if len(dets) > 1 else 0.0
        d2_meth = dets[1]['method'] if len(dets) > 1 else ''

        # Update confidence bars
        self.conf_bar1.update_value(d1_val, d1_conf, d1_meth)
        self.conf_bar2.update_value(d2_val, d2_conf, d2_meth)

        # Method label
        if dets:
            parts = [f"Die {i+1}: {d['method']} ({int(d['conf']*100)}%)"
                     for i, d in enumerate(dets)]
            self.method_label.setText('  |  '.join(parts))
        else:
            self.method_label.setText('')

        # ── Temporal stability check ──────────────────────────────────────
        # Push current frame's reading into the buffer (0,0 if no dice found)
        if not captured and not self._in_cooldown:
            reading = (min(d1_val, d2_val), max(d1_val, d2_val)) if len(dets) == 2 else (0, 0)
            self._stable_buffer.append(reading)

            # Count how many of the last N frames agree on the same valid pair
            thresh = self.auto_slider.value() / 100.0
            if (len(dets) == 2 and d1_conf >= thresh and d2_conf >= thresh
                    and reading != (0, 0)):
                count = sum(1 for r in self._stable_buffer if r == reading)
                self._stable_progress = count
            else:
                self._stable_progress = 0

            # Auto-submit once we hit the stability target
            if (self.auto_chk.isChecked()
                    and self._stable_progress >= self._STABLE_NEEDED
                    and len(dets) == 2):
                self._stable_buffer.clear()
                self._stable_progress = 0
                self._submit_roll(d1_val, d2_val)
                return

        # ── Status display ────────────────────────────────────────────────
        if len(dets) == 2:
            thresh = self.auto_slider.value() / 100.0
            prog   = self._stable_progress
            needed = self._STABLE_NEEDED
            if self.auto_chk.isChecked() and not self._in_cooldown and not captured:
                if prog > 0:
                    bar = '█' * prog + '░' * (needed - prog)
                    self.status_label.setText(
                        f'Stabilizing [{bar}] {prog}/{needed} — '
                        f'Die1={d1_val} Die2={d2_val}')
                else:
                    self.status_label.setText(
                        f'Two dice detected — waiting for confidence >= {int(thresh*100)}%')
            else:
                self.status_label.setText(
                    f'Two dice found: {d1_val} + {d2_val} — click "Use Result"')
            self.use_result_button.setEnabled(True)
        elif len(dets) == 1:
            self._stable_progress = 0
            self.status_label.setText(
                f'One die detected ({len(cands)} shapes) — show both dice clearly')
            self.use_result_button.setEnabled(False)
        else:
            self._stable_progress = 0
            n = len(cands)
            if n > 0:
                self.status_label.setText(
                    f'{n} shape(s) found but value unclear — adjust lighting/angle')
            elif captured:
                self.status_label.setText('No shapes found — try a plain background')
            else:
                self.status_label.setText('Searching... (place dice on a plain surface)')
            self.use_result_button.setEnabled(False)

    # ── Actions ────────────────────────────────────────────────────────────────

    def capture_and_detect(self):
        if not OPENCV_AVAILABLE or not self.camera_available or self._in_cooldown:
            return
        if self.is_frozen:
            self.is_frozen = False
            self.capture_button.setText('Capture & Detect')
            self.status_label.setText('Searching...')
            self._live_timer.start()
            return
        if self.current_frame is None:
            return
        self.is_frozen = True
        self.capture_button.setText('Resume Live Feed')
        self._live_timer.stop()
        self._process(self.current_frame.copy(), captured=True)

    def _save_debug_frame(self):
        """Save the current frame to disk for debugging or use as a new reference photo."""
        if not OPENCV_AVAILABLE or self.current_frame is None:
            return
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save Current Frame',
            str(Path.home() / 'debug_frame.jpg'),
            'Images (*.jpg *.png)')
        if path:
            cv2.imwrite(path, self.current_frame)
            self.save_frame_button.setText('Saved!')
            QTimer.singleShot(2000, lambda: self.save_frame_button.setText('Save Frame'))

    def use_detected_result(self):
        if len(self.current_detections) != 2:
            return
        d1 = int(self.current_detections[0]['value'])
        d2 = int(self.current_detections[1]['value'])
        if 1 <= d1 <= 6 and 1 <= d2 <= 6:
            self._submit_roll(d1, d2)

    def use_manual_result(self):
        self._submit_roll(self.manual_die1.value(), self.manual_die2.value())

    # ── Roll submission + cooldown ─────────────────────────────────────────────

    def _submit_roll(self, d1: int, d2: int):
        """Emit dice result and start the between-roll cooldown."""
        self.dice_detected.emit(d1, d2)
        secs = self.cooldown_spin.value()
        self._in_cooldown        = True
        self._cooldown_remaining = secs
        self._stable_buffer.clear()
        self._stable_progress = 0
        # Unfreeze camera so players can see the live feed during cooldown
        self.is_frozen = False
        if not self._live_timer.isActive():
            self._live_timer.start()
        self.capture_button.setText('Capture & Detect')
        self.capture_button.setEnabled(False)
        self.use_result_button.setEnabled(False)
        self.conf_bar1.update_value(d1, 0.0, '')
        self.conf_bar2.update_value(d2, 0.0, '')
        self.status_label.setText(
            f'Roll [{d1} + {d2} = {d1+d2}] submitted!  '
            f'Next roll in {secs}s...')
        self.method_label.setText('')
        self._cd_timer.start()

    def _cooldown_tick(self):
        self._cooldown_remaining -= 1
        if self._cooldown_remaining <= 0:
            self._cd_timer.stop()
            self._in_cooldown = False
            self.capture_button.setEnabled(True)
            self.conf_bar1.update_value(0, 0.0, '')
            self.conf_bar2.update_value(0, 0.0, '')
            self.status_label.setText('Ready — roll the dice and hold them in frame!')
        else:
            self.status_label.setText(
                f'Cooldown — players roll the dice...  '
                f'detecting again in {self._cooldown_remaining}s')

    def closeEvent(self, event):
        self._cd_timer.stop()
        self.release_camera()
        super().closeEvent(event)
