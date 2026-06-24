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

# Module-level stores — populated by load_reference_images()
_REF_IMGS:    Dict[int, np.ndarray] = {}   # {face: 64×64 gray reference image}
_ORB_FEATS:   Dict[int, list]       = {}   # {face: [(kp, des), ...]} rotated variants
_TEMPLATE_SOURCE: str = ""

_ORB_INST = None

def _get_orb():
    global _ORB_INST
    if _ORB_INST is None and OPENCV_AVAILABLE:
        _ORB_INST = cv2.ORB_create(nfeatures=500, scaleFactor=1.2, nlevels=8,
                                    edgeThreshold=10, firstLevel=0, WTA_K=2,
                                    scoreType=cv2.ORB_HARRIS_SCORE,
                                    patchSize=31, fastThreshold=15)
    return _ORB_INST


# ── Webcam config (persists default camera selection) ─────────────────────────

def _config_path() -> Path:
    from paths import webcam_config_path
    return webcam_config_path()

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


# ── Training data (correction log + bias learning) ────────────────────────────

def _get_training_dir() -> Path:
    from paths import training_data_dir
    return training_data_dir()

_TRAINING_DIR = _get_training_dir()
_CORRECTIONS_LOG = _TRAINING_DIR / 'corrections_log.json'


def _ensure_training_dir():
    _TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    (_TRAINING_DIR / 'frames').mkdir(exist_ok=True)


def _save_training_entry(frame, detected_d1: int, detected_d2: int,
                         true_d1: int, true_d2: int) -> None:
    """
    Save a training log entry.  Always called after a roll is confirmed.
    If the user corrected the values, was_corrected=True and the true_d*
    fields reflect the correction.  The full frame is saved as a JPEG so
    the detection algorithm can be re-evaluated against real examples later.
    """
    if not OPENCV_AVAILABLE:
        return
    try:
        _ensure_training_dir()
        import datetime
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        frame_name = f'frame_{ts}.jpg'
        frame_path = str(_TRAINING_DIR / 'frames' / frame_name)
        if frame is not None:
            cv2.imwrite(frame_path, frame)
        else:
            frame_path = ''

        was_corrected = (detected_d1 != true_d1 or detected_d2 != true_d2)
        entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'detected_d1': detected_d1,
            'detected_d2': detected_d2,
            'true_d1': true_d1,
            'true_d2': true_d2,
            'was_corrected': was_corrected,
            'frame_path': frame_path,
        }

        # Append to JSON log
        log: list = []
        if _CORRECTIONS_LOG.exists():
            try:
                with open(_CORRECTIONS_LOG, encoding='utf-8') as f:
                    log = json.load(f)
            except Exception:
                log = []
        log.append(entry)
        with open(_CORRECTIONS_LOG, 'w', encoding='utf-8') as f:
            json.dump(log, f, indent=2)
    except Exception:
        pass


def _load_bias_table() -> Dict[int, int]:
    """
    Build a per-value bias correction table from the correction log.

    For each detected value X that was manually corrected to Y:
      - If X has been corrected ≥ 5 times AND ≥ 75 % of those corrections
        changed it to the same value Y → add X→Y to the bias table.
      - Bias is only applied when detection confidence is low (< 0.75), so
        confident correct detections are never overridden.

    Returns {detected_value: corrected_value}.
    """
    if not _CORRECTIONS_LOG.exists():
        return {}
    try:
        with open(_CORRECTIONS_LOG, encoding='utf-8') as f:
            log = json.load(f)
    except Exception:
        return {}

    # Count per-die corrections (treat each die independently)
    corrections: Dict[int, Counter] = {}
    for entry in log:
        if not entry.get('was_corrected'):
            continue
        for det, true in [(entry['detected_d1'], entry['true_d1']),
                          (entry['detected_d2'], entry['true_d2'])]:
            if det != true and 1 <= det <= 6 and 1 <= true <= 6:
                corrections.setdefault(det, Counter())[true] += 1

    bias: Dict[int, int] = {}
    for det_val, counter in corrections.items():
        total = sum(counter.values())
        best_val, best_cnt = counter.most_common(1)[0]
        if total >= 5 and best_cnt / total >= 0.75:
            bias[det_val] = best_val
    return bias


# ── Reference image loading ───────────────────────────────────────────────────

def _prep_gray(img) -> np.ndarray:
    """Normalize a die-face image for consistent matching."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()
    gray = cv2.resize(gray, _TEMPLATE_SIZE)
    # Bilateral filter preserves pip edges while smoothing noise
    gray = cv2.bilateralFilter(gray, d=7, sigmaColor=50, sigmaSpace=50)
    # Min-max stretch — makes lighting differences less impactful
    mn, mx = float(gray.min()), float(gray.max())
    if mx > mn:
        gray = np.clip((gray.astype(np.float32) - mn) / (mx - mn) * 255,
                       0, 255).astype(np.uint8)
    return gray


def _crop_to_die(img):
    """Try to isolate the die face in a reference photo using HSV white detection."""
    if not OPENCV_AVAILABLE:
        return img
    hsv   = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lo    = np.array([0,   0, 130], dtype=np.uint8)
    hi    = np.array([179, 80, 255], dtype=np.uint8)
    mask  = cv2.inRange(hsv, lo, hi)
    mask  = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return img
    fh, fw = img.shape[:2]
    fa = fh * fw
    candidates = []
    for cnt in cnts:
        a = cv2.contourArea(cnt)
        if not (fa * 0.01 <= a <= fa * 0.95):
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        if h == 0 or not (0.5 <= w/h <= 2.0):
            continue
        candidates.append((a, x, y, w, h))
    if not candidates:
        return img
    _, x, y, w, h = max(candidates, key=lambda t: t[0])
    pad = max(4, int(min(w, h) * 0.05))
    return img[max(0, y-pad):min(fh, y+h+pad), max(0, x-pad):min(fw, x+w+pad)]


def load_reference_images(folder: str) -> Tuple[int, str]:
    """
    Load reference images (1.jpg–6.jpg), crop to die face, and build
    ORB feature banks (4 rotations × augmented brightness per face).
    """
    global _TEMPLATE_SOURCE
    _REF_IMGS.clear()
    _ORB_FEATS.clear()

    if not OPENCV_AVAILABLE:
        return 0, "OpenCV not available"

    p = Path(folder)
    if not p.is_dir():
        return 0, f"Folder not found: {folder}"

    extensions = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif",
                  ".JPG", ".JPEG", ".PNG", ".BMP")
    loaded = 0
    orb    = _get_orb()

    for value in range(1, 7):
        img_path: Optional[Path] = None
        for ext in extensions:
            c = p / f"{value}{ext}"
            if c.exists():
                img_path = c
                break
        if img_path is None:
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            continue

        crop = _crop_to_die(img)
        gray = _prep_gray(crop)
        _REF_IMGS[value] = gray

        # Build ORB features for 4 rotations × 3 brightness levels = 12 variants
        if orb:
            variants = []
            for angle in (0, 90, 180, 270):
                if angle:
                    M   = cv2.getRotationMatrix2D((32, 32), float(angle), 1.0)
                    rot = cv2.warpAffine(gray, M, _TEMPLATE_SIZE)
                else:
                    rot = gray
                for alpha in (0.75, 1.0, 1.30):
                    adj = np.clip(rot.astype(np.float32) * alpha, 0, 255).astype(np.uint8)
                    try:
                        kp, des = orb.detectAndCompute(adj, None)
                        if des is not None and len(des) >= 4:
                            variants.append((kp, des))
                    except Exception:
                        pass
            if variants:
                _ORB_FEATS[value] = variants
        loaded += 1

    _TEMPLATE_SOURCE = str(p) if loaded else ""
    status = (f"{loaded}/6 reference images loaded (ORB features ready)"
              if loaded else "No reference images found")
    return loaded, status


# ── NMS helper ────────────────────────────────────────────────────────────────

def _nms(rects: List[Tuple[int,int,int,int]], iou_thresh: float = 0.30) \
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
            inter = (ix2-ix1) * (iy2-iy1)
            union = bw*bh + rw*rh - inter
            if union <= 0 or inter/union < iou_thresh:
                survivors.append(r)
        rects = survivors
    return kept


# ── Die localization ──────────────────────────────────────────────────────────

def _find_die_candidates(frame) -> List[Tuple[int,int,int,int]]:
    """
    Multi-strategy die localization — works on both dark and light backgrounds:

    Method 1 (dark background): Find bright white rectangular blobs directly.
      White dice on black surface have extreme contrast — simple threshold finds
      them instantly. This is the most reliable method when using a dark backdrop.

    Method 2 (any background): Pip-first clustering.
      Find dark circular pip blobs, group nearby ones into dice. Works even when
      die face and background are similar brightness (white on cream).

    Method 3 (fallback): CLAHE + Otsu for higher-contrast non-white setups.
    """
    fh, fw = frame.shape[:2]
    fa     = fh * fw
    gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur   = cv2.GaussianBlur(gray, (5, 5), 0)
    found: List[Tuple[int,int,int,int]] = []

    def _check_sq(cnt):
        area = cv2.contourArea(cnt)
        if not (fa * 0.0005 <= area <= fa * 0.06):   # contour area
            return None
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h > fa * 0.08:                         # bounding rect area — rejects frame/border
            return None
        if h == 0 or not (0.65 <= w / h <= 1.55):
            return None
        if area / (w * h) < 0.42:
            return None
        return (x, y, w, h)

    # ── Method 1: bright-region on dark background ────────────────────────────
    # Simple fixed + Otsu thresholds find white dice on black instantly.
    # Also catches rotated dice since we filter by fill ratio not exact shape.
    for thresh in (180, 200, 220):
        _, thr = cv2.threshold(blur, thresh, 255, cv2.THRESH_BINARY)
        thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE,
                               np.ones((7, 7), np.uint8), iterations=2)
        thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN,
                               np.ones((3, 3), np.uint8), iterations=1)
        for cnt in cv2.findContours(thr, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)[0]:
            r = _check_sq(cnt)
            if r:
                found.append(r)

    _, thr_otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr_otsu = cv2.morphologyEx(thr_otsu, cv2.MORPH_CLOSE,
                                np.ones((7, 7), np.uint8), iterations=2)
    for cnt in cv2.findContours(thr_otsu, cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)[0]:
        r = _check_sq(cnt)
        if r:
            found.append(r)

    # ── Method 2: pip-first clustering (works on light/cream backgrounds) ─────
    # Dark pips become bright blobs in inverted threshold — very high contrast
    # regardless of whether the die face and background look similar.
    _, pip_thr = cv2.threshold(blur, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    pip_min = max(8, fa * 0.000012)
    pip_max = fa * 0.0020
    pip_pts: List[Tuple[int, int, int]] = []

    for cnt in cv2.findContours(pip_thr, cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)[0]:
        area = cv2.contourArea(cnt)
        if not (pip_min <= area <= pip_max):
            continue
        peri = cv2.arcLength(cnt, True)
        if peri <= 0:
            continue
        if 4.0 * np.pi * area / (peri * peri) < 0.35:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        pip_pts.append((x + w // 2, y + h // 2, max(w, h)))

    if pip_pts:
        med_size = float(np.median([p[2] for p in pip_pts]))
        clust_d  = med_size * 9.0
        used = [False] * len(pip_pts)
        for i in range(len(pip_pts)):
            if used[i]:
                continue
            cluster: List[int] = []
            stack = [i]
            used[i] = True
            while stack:
                cur = stack.pop()
                cluster.append(cur)
                cx0, cy0, _ = pip_pts[cur]
                for j in range(len(pip_pts)):
                    if not used[j]:
                        cx1, cy1, _ = pip_pts[j]
                        if (cx0 - cx1)**2 + (cy0 - cy1)**2 < clust_d**2:
                            used[j] = True
                            stack.append(j)
            n = len(cluster)
            if 1 <= n <= 6:
                xs  = [pip_pts[k][0] for k in cluster]
                ys  = [pip_pts[k][1] for k in cluster]
                pad = max(int(med_size * 2.2), 6)
                x1, y1 = max(0, min(xs) - pad), max(0, min(ys) - pad)
                x2, y2 = min(fw, max(xs) + pad), min(fh, max(ys) + pad)
                dw, dh = x2 - x1, y2 - y1
                # Reject non-square pip clusters (noise streaks, frame edges)
                if dw > 12 and dh > 12 and 0.55 <= dw / dh <= 1.80:
                    found.append((x1, y1, dw, dh))

    # ── Method 3: CLAHE fallback ──────────────────────────────────────────────
    clahe  = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    blur_c = cv2.GaussianBlur(clahe.apply(gray), (5, 5), 0)
    _, thr2 = cv2.threshold(blur_c, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    for cnt in cv2.findContours(thr2, cv2.RETR_TREE,
                                cv2.CHAIN_APPROX_SIMPLE)[0]:
        r = _check_sq(cnt)
        if r:
            found.append(r)

    return _nms(found)


# ── Die face sanity check ─────────────────────────────────────────────────────

def _is_die_like(roi) -> bool:
    """Return True only if the ROI plausibly contains a die face.
    Intentionally loose — pip-first localization already ensures we're
    looking at a pip cluster region; we just reject obviously wrong patches.
    """
    if roi is None or roi.size == 0:
        return False
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    mean_b = float(np.mean(gray))
    if mean_b < 50:                                          # too dark overall
        return False
    std = float(np.std(gray))
    if std < 3 or std > 110:                                 # blank or chaotic
        return False
    # Must have some dark pixels (the pips)
    if float(np.sum(gray < mean_b * 0.75)) / gray.size < 0.003:
        return False
    return True


# ── ORB-based classifier ──────────────────────────────────────────────────────

def _match_orb(roi) -> Tuple[int, float]:
    """
    Match live ROI against pre-computed ORB features of all 6 reference faces.
    Returns (best_value, confidence 0-1).
    Uses Lowe's ratio test; confidence = good_matches / target_matches.
    """
    orb = _get_orb()
    if not orb or not _ORB_FEATS or roi is None or roi.size == 0:
        return 0, 0.0
    if min(roi.shape[:2]) < 20:
        return 0, 0.0

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi.copy()
    gray = _prep_gray(roi if roi.ndim == 3 else
                      cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR))

    try:
        kp2, des2 = orb.detectAndCompute(gray, None)
    except Exception:
        return 0, 0.0
    if des2 is None or len(des2) < 4:
        return 0, 0.0

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    best_val, best_conf = 0, 0.0

    for value, variants in _ORB_FEATS.items():
        val_good = 0
        for (kp1, des1) in variants:
            try:
                raw = bf.knnMatch(des1, des2, k=2)
                for pair in raw:
                    if len(pair) == 2:
                        m, n = pair
                        if m.distance < 0.75 * n.distance:
                            val_good += 1
            except Exception:
                continue
        # Normalise: 12 good matches = 100% confidence (empirical target)
        conf = min(1.0, val_good / 12.0)
        if conf > best_conf:
            best_conf, best_val = conf, value

    return best_val, best_conf


# ── Pip counting (connected components) ──────────────────────────────────────

def _deskew_roi(roi):
    """
    Return a rotation-corrected copy of a die ROI.
    Finds the largest bright blob, gets its minAreaRect angle, and rotates
    the crop to axis-align the die face. Falls back to the original if it fails.
    """
    if roi is None or roi.size == 0 or min(roi.shape[:2]) < 20:
        return roi
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi.copy()
    _, thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cnts, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return roi
    largest = max(cnts, key=cv2.contourArea)
    rect = cv2.minAreaRect(largest)
    angle = rect[2]
    # minAreaRect returns angle in (-90, 0]; normalise to (-45, 45]
    if angle < -45:
        angle += 90
    if abs(angle) < 3:   # already nearly square — skip expensive warp
        return roi
    h, w = roi.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(roi if roi.ndim == 3 else
                              cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR),
                              M, (w, h),
                              flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT,
                              borderValue=(0, 0, 0))
    return rotated


def _count_pips(roi) -> Tuple[int, float]:
    """
    Two-stage pip counting: isolate die face, then find pips inside it.

    Stage 1 -- THRESH_BINARY + OTSU finds the bright die face on black background.
    Two separate close kernels are used:
      - face_big (large kernel): fills pip holes completely -> used for V2/V4/V5
      - face_small (small kernel): leaves pip holes open -> used for V6 RETR_CCOMP

    Stage 2 -- 6 independent votes, all masked to die face only:
      V1  SimpleBlobDetector with area+circ+convexity+inertia filters
      V2  pip_holes = face_big_interior AND NOT face_mask  (filled holes)
      V3  HoughCircles on inverted die face
      V4  Adaptive threshold within die face
      V5  Black-hat morphology within die face
      V6  RETR_CCOMP internal contours of face_small blob

    Key improvements:
    - min_pip based on die FACE area (not total ROI area) -- handles pips that
      are small relative to bounding box (e.g. rotated dice where bbox > face)
    - Circularity threshold 0.50 (was 0.35) -- rejects text/edge shadow artifacts
      (real pips are near-circular: circ > 0.65; text/noise: 0.20-0.50)
    - Larger k_close for V2 ensures pip holes are fully filled even for larger pips
    - Upsample to 200px for consistent sizing regardless of camera distance
    """
    if not OPENCV_AVAILABLE or roi is None or roi.size == 0:
        return 0, 0.0
    if min(roi.shape[:2]) < 16:
        return 0, 0.0

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi.copy()

    # Upsample to ~200px on longest side for consistent pip size
    h, w = gray.shape
    upscale = 200 / max(h, w)
    if upscale > 1.0:
        nh, nw = max(1, int(h * upscale)), max(1, int(w * upscale))
        gray = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_CUBIC)
        h, w = nh, nw

    gray = cv2.equalizeHist(gray)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # Stage 1: die face mask
    _, face_mask = cv2.threshold(blur, 0, 255,
                                 cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Large close: fills pip holes completely (used for V2 pip-holes subtraction)
    k_big = max(17, min(h, w) // 4)
    if k_big % 2 == 0:
        k_big += 1
    kern_big = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_big, k_big))
    face_big = cv2.morphologyEx(face_mask, cv2.MORPH_CLOSE, kern_big)

    # Small close: just kills tiny noise, leaves pip holes open (for V6 RETR_CCOMP)
    k_small = max(5, min(h, w) // 14)
    if k_small % 2 == 0:
        k_small += 1
    kern_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_small, k_small))
    face_small = cv2.morphologyEx(face_mask, cv2.MORPH_CLOSE, kern_small)

    # Erode face_big to get die face interior (strips edge shadow)
    k_erode = max(3, min(h, w) // 20)
    if k_erode % 2 == 0:
        k_erode += 1
    kern_e = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_erode, k_erode))
    face_interior = cv2.erode(face_big, kern_e, iterations=1)

    face_area = float(np.sum(face_interior > 0))
    # Sanity check: if face fills >90% of ROI, this is likely a noise false-positive
    if face_area / (h * w) > 0.90 or face_area < 400:
        return 0, 0.0

    # Pip bounds based on DIE FACE area (not total ROI area).
    # Real pips typically cover 0.8-8% of the die face; we accept 0.7-18%.
    min_pip = max(50, face_area * 0.008)
    max_pip = face_area * 0.18

    kern_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    def count_round(img, circ_thresh=0.50) -> int:
        """Count roughly-circular blobs within pip area bounds.
        Default circ=0.50 filters out text and shadow artifacts while keeping
        real pips (which are near-perfect circles: circ typically 0.65-0.95).

        Applies a consistency filter: after collecting circular blobs, any blob
        with area < 55% of the median blob area is rejected as a fragment.
        This handles the case where noise blobs are significantly smaller than
        the real pips (e.g. 186px² noise alongside 380px² real pips on a 2-die).
        """
        cnts, _ = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
        areas = []
        for cnt in cnts:
            area = cv2.contourArea(cnt)
            if not (min_pip <= area <= max_pip):
                continue
            peri = cv2.arcLength(cnt, True)
            if peri > 0 and 4 * np.pi * area / (peri * peri) > circ_thresh:
                areas.append(area)
        if not areas:
            return 0
        # Consistency filter: reject blobs much smaller than the median.
        # Real pips on the same die are roughly equal in size; fragments are not.
        median_a = sorted(areas)[len(areas) // 2]
        areas = [a for a in areas if a >= median_a * 0.55]
        return min(6, len(areas))

    votes = []
    v1_result = 0   # anchor: SimpleBlobDetector is most reliable (6/6 correct)

    # Vote 1: SimpleBlobDetector -- dark pips on bright die face.
    # Added TWICE to the vote list to give it double weight; it is the only
    # method that is correct for all 6 die values on these dice.
    #
    # Key live-video improvements over earlier versions:
    #   • face_big (not face_interior) is used as the mask — the k_erode step
    #     can clip pips that sit near the die edge in a slightly rotated live
    #     frame, causing under-counts.  face_big = fully-closed face without
    #     the erosion strip, so all pips remain visible.
    #   • minCircularity lowered 0.55→0.45: slight motion blur or defocus in
    #     live video makes pips appear less perfectly circular; 0.45 still
    #     rejects elongated text/shadow artifacts.
    #   • minConvexity lowered 0.75→0.65 for the same reason.
    try:
        bparams = cv2.SimpleBlobDetector_Params()
        bparams.minThreshold = 10
        bparams.maxThreshold = 220
        bparams.thresholdStep = 10
        bparams.filterByColor       = True
        bparams.blobColor           = 0
        bparams.filterByArea        = True
        bparams.minArea             = float(max(40, min_pip * 0.7))
        bparams.maxArea             = float(min(6000, max_pip * 1.3))
        bparams.filterByCircularity = True
        bparams.minCircularity      = 0.55
        bparams.filterByConvexity   = True
        bparams.minConvexity        = 0.75
        bparams.filterByInertia     = True
        bparams.minInertiaRatio     = 0.45
        bparams.minDistBetweenBlobs = float(max(5, min(h, w) // 15))
        detector = cv2.SimpleBlobDetector_create(bparams)
        # Use face_interior (eroded face) so die-edge shadow pixels are excluded
        die_only = np.where(face_interior > 0, blur,
                            np.full_like(blur, 255)).astype(np.uint8)
        kps = detector.detect(die_only)
        c = min(6, len(kps))
        if 1 <= c <= 6:
            v1_result = c
            votes.append(c)   # first vote
            votes.append(c)   # double weight — V1 is the anchor
    except Exception:
        pass

    # Vote 2: pip holes -- face_big has pips filled; subtract from original mask
    pip_holes = cv2.bitwise_and(face_interior, cv2.bitwise_not(face_mask))
    pip_holes = cv2.morphologyEx(pip_holes, cv2.MORPH_OPEN, kern_open)
    c = count_round(pip_holes, circ_thresh=0.55)   # stricter: holes are rounder
    if 1 <= c <= 6:
        votes.append(c)

    # Vote 3: HoughCircles removed — tested against all 6 die values and found
    # to be incorrect 4/6 times (systematically over-detects circles on these
    # dice), making it a net negative for accuracy.

    # Vote 4: adaptive threshold within die face.
    # Gated: only counted if the result is within ±1 of V1's anchor value.
    # Without the gate, V4 was wrong 4/6 times (text/shadow artifacts).
    block = max(11, min(h, w) // 5)
    if block % 2 == 0:
        block += 1
    adapt = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY_INV, block, 5)
    adapt_face = cv2.bitwise_and(adapt, face_interior)
    adapt_face = cv2.morphologyEx(adapt_face, cv2.MORPH_OPEN, kern_open)
    c = count_round(adapt_face)
    if 1 <= c <= 6:
        if v1_result == 0 or abs(c - v1_result) <= 1:
            votes.append(c)

    # Vote 5: black-hat morphology within die face
    k_bh = max(11, min(h, w) // 6)
    if k_bh % 2 == 0:
        k_bh += 1
    kern_bh = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_bh, k_bh))
    bh = cv2.morphologyEx(blur, cv2.MORPH_BLACKHAT, kern_bh)
    bh_face = cv2.bitwise_and(bh, face_interior)
    if bh_face.max() > 4:
        _, bh_thr = cv2.threshold(bh_face, 0, 255,
                                  cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        bh_thr = cv2.morphologyEx(bh_thr, cv2.MORPH_OPEN, kern_open)
        c = count_round(bh_thr)
        if 1 <= c <= 6:
            votes.append(c)

    # Vote 6: RETR_CCOMP -- internal contours (pip holes) of face_small blob.
    # Circularity raised to 0.55 (was 0.40) to match the other methods and
    # prevent false pip detections from noise in the die face texture.
    cnts_tree, hier = cv2.findContours(face_small, cv2.RETR_CCOMP,
                                       cv2.CHAIN_APPROX_SIMPLE)
    if hier is not None:
        pip_n = 0
        for i, cnt in enumerate(cnts_tree):
            if hier[0][i][3] >= 0:     # has parent -> pip hole
                area = cv2.contourArea(cnt)
                if min_pip <= area <= max_pip:
                    peri = cv2.arcLength(cnt, True)
                    if peri > 0 and 4 * np.pi * area / (peri * peri) > 0.55:
                        pip_n += 1
        if 1 <= pip_n <= 6:
            votes.append(pip_n)

    if not votes:
        return 0, 0.0

    winner, freq = Counter(votes).most_common(1)[0]
    total = len(votes)
    conf = min(0.95, 0.50 + (freq / total) * 0.47)
    return winner, conf



# ── Combined classifier ───────────────────────────────────────────────────────

def _detect_die_value(roi) -> Tuple[int, float, str]:
    """
    Returns (face_value, confidence 0-1, method_label).
    Runs detection on the original ROI **and** on a deskewed copy — takes the
    result with higher confidence (rotation-corrected often wins for tilted dice).
    """
    def _classify(r) -> Tuple[int, float, str]:
        orb_val, orb_conf = _match_orb(r)
        pip_val, pip_conf = _count_pips(r)

        if orb_val > 0 and pip_val > 0 and orb_val == pip_val:
            combined = min(0.97, max(orb_conf, pip_conf) + 0.15)
            return orb_val, combined, "orb+pips"
        if orb_conf >= 0.55 and orb_val > 0:
            return orb_val, orb_conf, "orb"
        if pip_val > 0 and pip_conf >= 0.60:
            return pip_val, pip_conf, "pips"
        if orb_conf >= 0.40 and orb_val > 0 and pip_val > 0:
            return orb_val, orb_conf, "orb"
        if pip_val > 0 and pip_conf >= 0.45:
            return pip_val, pip_conf, "pips"
        return 0, 0.0, "?"

    val, conf, method = _classify(roi)

    # Also try deskewed version — rotated dice often score higher after correction
    deskewed = _deskew_roi(roi)
    if deskewed is not roi:
        val2, conf2, meth2 = _classify(deskewed)
        if conf2 > conf + 0.05:   # only switch if meaningfully better
            return val2, conf2, meth2 + "+dsk"

    return val, conf, method


# ── Main analysis pipeline ────────────────────────────────────────────────────

def _analyze_frame(frame) -> Tuple[List[Dict], List[Dict]]:
    if not OPENCV_AVAILABLE or frame is None:
        return [], []

    fh, fw     = frame.shape[:2]
    cand_rects = _find_die_candidates(frame)
    detections: List[Dict] = []
    candidates: List[Dict] = []

    for (x, y, rw, rh) in cand_rects:
        pad    = max(4, int(min(rw, rh) * 0.06))
        x1, y1 = max(0, x - pad),       max(0, y - pad)
        x2, y2 = min(fw, x + rw + pad), min(fh, y + rh + pad)
        roi    = frame[y1:y2, x1:x2]

        if not _is_die_like(roi):
            continue

        val, conf, method = _detect_die_value(roi)

        # Small confidence penalty for detections close to frame edges
        # (frame borders, shelf, etc. tend to produce false detections there)
        margin = min(x, fw - (x + rw), y, fh - (y + rh))
        if margin < min(fw, fh) * 0.04:
            conf = max(0.0, conf - 0.15)

        candidates.append({'rect': (x, y, rw, rh), 'pips': val,
                           'conf': conf, 'method': method, 'area': rw * rh})
        if 1 <= val <= 6:
            detections.append({'value': val, 'conf': conf,
                               'method': method, 'rect': (x, y, rw, rh)})

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
        self._STABLE_WINDOW  = 6
        self._STABLE_NEEDED  = 4
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

        # ── ROI state ──────────────────────────────────────────────────────────
        self._roi: Optional[tuple]  = None   # (x1, y1, x2, y2) in frame pixels
        self._roi_selecting         = False
        self._roi_drag_start: Optional[tuple] = None
        self._roi_preview: Optional[tuple]    = None
        self._current_frame                   = None  # most recent raw frame
        self._saved_roi_fractions             = None  # loaded from config

        # ── Confirmation / training state ──────────────────────────────────────
        # When a stable reading fires, _pending_detected stores (d1, d2) and the
        # confirmation panel is shown instead of immediately emitting.
        self._pending_detected: Optional[tuple] = None   # (d1, d2) last auto-detected
        self._pending_frame                     = None   # frame snapshot for training
        self._bias_table: Dict[int, int]        = {}     # loaded from corrections_log

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

        if OPENCV_AVAILABLE:
            load_reference_images(_DEFAULT_TEMPLATE_DIR)
            default_cam = _load_webcam_config().get('default_camera', 0)
            self.open_camera(default_cam)
            # Restore saved ROI (stored as fractions, resolved on first frame)
            self._saved_roi_fractions = _load_webcam_config().get('roi', None)
            # Load learned correction bias from training log
            self._bias_table = _load_bias_table()
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

        # Camera selector row
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

        # ROI row — draw detection area on the live feed
        roi_row = QHBoxLayout()
        self._roi_btn = QPushButton('📐 Set Detection Area')
        self._roi_btn.setToolTip(
            'Click then drag a rectangle on the camera feed to limit\n'
            'detection to that area. Useful for ignoring borders/clutter.')
        self._roi_btn.setCheckable(True)
        self._roi_btn.toggled.connect(self._on_roi_mode_toggled)
        self._roi_clear_btn = QPushButton('✕ Clear Area')
        self._roi_clear_btn.setToolTip('Remove the detection area crop — use full frame')
        self._roi_clear_btn.setEnabled(False)
        self._roi_clear_btn.clicked.connect(self._clear_roi)
        self._roi_status_lbl = QLabel('')
        self._roi_status_lbl.setStyleSheet('color: #F5D76E; font-size: 11px;')
        roi_row.addWidget(self._roi_btn)
        roi_row.addWidget(self._roi_clear_btn)
        roi_row.addWidget(self._roi_status_lbl, 1)
        root.addLayout(roi_row)

        # Live feed — fills spare vertical space; mouse events used for ROI
        from PyQt6.QtWidgets import QSizePolicy
        self.feed_label = QLabel('Starting camera...')
        self.feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feed_label.setMinimumSize(320, 240)
        self.feed_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.feed_label.setObjectName('feedLabel')
        self.feed_label.setMouseTracking(True)
        self.feed_label.installEventFilter(self)
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
        self.stable_spin.setValue(4)
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

        # ── Confirmation panel ────────────────────────────────────────────────
        # Shown after each stable auto-detection; hidden during normal scanning.
        self._confirm_grp = QGroupBox('Dice Result — Confirm or Correct')
        self._confirm_grp.setObjectName('confirmGrp')
        self._confirm_grp.setVisible(False)
        cg_layout = QVBoxLayout(self._confirm_grp)
        cg_layout.setSpacing(6)
        cg_layout.setContentsMargins(8, 8, 8, 8)

        # Result display + action buttons
        result_row = QHBoxLayout()
        self._confirm_result_lbl = QLabel('')
        self._confirm_result_lbl.setStyleSheet(
            'font-size: 15px; font-weight: bold; color: #FFD700;'
            'font-family: Georgia, serif; padding: 2px 6px;')
        result_row.addWidget(self._confirm_result_lbl, 1)
        self._confirm_accept_btn = QPushButton('✓  Accept')
        self._confirm_accept_btn.setObjectName('confirmAcceptBtn')
        self._confirm_accept_btn.setMinimumWidth(90)
        self._confirm_accept_btn.clicked.connect(self._on_confirm_accept)
        self._confirm_edit_btn = QPushButton('✏  Edit')
        self._confirm_edit_btn.setMinimumWidth(70)
        self._confirm_edit_btn.setCheckable(True)
        self._confirm_edit_btn.clicked.connect(self._on_confirm_edit_toggle)
        result_row.addWidget(self._confirm_accept_btn)
        result_row.addWidget(self._confirm_edit_btn)
        cg_layout.addLayout(result_row)

        # Edit row — hidden until "Edit" is toggled on
        self._confirm_edit_row = QWidget()
        edit_hl = QHBoxLayout(self._confirm_edit_row)
        edit_hl.setContentsMargins(0, 0, 0, 0)
        edit_hl.addWidget(QLabel('Correct to:'))
        self._confirm_d1 = QSpinBox()
        self._confirm_d1.setRange(1, 6)
        self._confirm_d1.setPrefix('Die 1: ')
        self._confirm_d1.setFixedWidth(80)
        self._confirm_d2 = QSpinBox()
        self._confirm_d2.setRange(1, 6)
        self._confirm_d2.setPrefix('Die 2: ')
        self._confirm_d2.setFixedWidth(80)
        edit_hl.addWidget(self._confirm_d1)
        edit_hl.addWidget(self._confirm_d2)
        self._confirm_submit_btn = QPushButton('Submit Correction')
        self._confirm_submit_btn.setObjectName('confirmSubmitBtn')
        self._confirm_submit_btn.clicked.connect(self._on_confirm_submit)
        edit_hl.addWidget(self._confirm_submit_btn)
        edit_hl.addStretch()
        self._confirm_edit_row.setVisible(False)
        cg_layout.addWidget(self._confirm_edit_row)

        # Training stats label (shows how many corrections have been logged)
        self._training_stats_lbl = QLabel('')
        self._training_stats_lbl.setStyleSheet('color: #78A878; font-size: 10px;')
        cg_layout.addWidget(self._training_stats_lbl)
        root.addWidget(self._confirm_grp)

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


        # Tips
        tips = QLabel(
            '💡  Tips: place dice on a plain dark surface · '
            'use Set Detection Area to crop out borders/clutter'
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
            QGroupBox#confirmGrp { color: #FFD700; font-weight: bold; font-size: 12px;
                                   border: 2px solid #C8A84B; border-radius: 8px;
                                   background: #1C2A1C; margin-top: 4px; padding: 6px; }
            QGroupBox#confirmGrp::title { subcontrol-origin: margin; left: 8px;
                                          padding: 0 4px; color: #FFD700; }
            QPushButton { background: #3A6B2A; color: white; border: none;
                          border-radius: 6px; padding: 8px 14px; font-weight: bold; }
            QPushButton:hover    { background: #4E8538; }
            QPushButton:disabled { background: #2A3A2A; color: #666; }
            QPushButton#useResultButton       { background: #8B6900; color: #F0EAD6; }
            QPushButton#useResultButton:hover { background: #C8A84B; color: #0E1A14; }
            QPushButton#confirmAcceptBtn       { background: #1A6830; color: #B0FFB0;
                                                 border: 1px solid #3ADA60; }
            QPushButton#confirmAcceptBtn:hover { background: #22903A; color: white; }
            QPushButton#confirmSubmitBtn       { background: #8B4400; color: #FFD8A0;
                                                 border: 1px solid #E88020; }
            QPushButton#confirmSubmitBtn:hover { background: #B05800; color: white; }
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
    # ── ROI selection ─────────────────────────────────────────────────────────

    def _on_roi_mode_toggled(self, checked: bool):
        if checked:
            self._roi_btn.setText('📐 Drawing… (drag on feed)')
            self._roi_status_lbl.setText('Click and drag on the camera feed')
            self.feed_label.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._roi_btn.setText('📐 Set Detection Area')
            self._roi_status_lbl.setText('')
            self.feed_label.setCursor(Qt.CursorShape.ArrowCursor)
        self._roi_selecting = checked
        self._roi_drag_start = None

    def _clear_roi(self):
        self._roi = None
        self._roi_clear_btn.setEnabled(False)
        self._roi_status_lbl.setText('')
        self._roi_btn.setChecked(False)
        cfg = _load_webcam_config()
        cfg.pop('roi', None)
        _save_webcam_config(cfg)

    def _label_pos_to_frame(self, lx: int, ly: int):
        """Convert a pixel position in feed_label to frame pixel coordinates."""
        if self._current_frame is None:
            return None, None
        fh, fw = self._current_frame.shape[:2]
        lw, lh = self.feed_label.width(), self.feed_label.height()
        scale = min(lw / fw, lh / fh)
        ox = (lw - int(fw * scale)) // 2
        oy = (lh - int(fh * scale)) // 2
        fx = int((lx - ox) / scale)
        fy = int((ly - oy) / scale)
        fx = max(0, min(fw - 1, fx))
        fy = max(0, min(fh - 1, fy))
        return fx, fy

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QMouseEvent
        if obj is self.feed_label and self._roi_selecting:
            t = event.type()
            if t == QEvent.Type.MouseButtonPress:
                fx, fy = self._label_pos_to_frame(event.pos().x(), event.pos().y())
                if fx is not None:
                    self._roi_drag_start = (fx, fy)
            elif t == QEvent.Type.MouseMove and self._roi_drag_start:
                fx, fy = self._label_pos_to_frame(event.pos().x(), event.pos().y())
                if fx is not None:
                    x1, y1 = self._roi_drag_start
                    self._roi_preview = (min(x1, fx), min(y1, fy),
                                        max(x1, fx), max(y1, fy))
            elif t == QEvent.Type.MouseButtonRelease and self._roi_drag_start:
                fx, fy = self._label_pos_to_frame(event.pos().x(), event.pos().y())
                if fx is not None:
                    x1, y1 = self._roi_drag_start
                    x2, y2 = max(x1, fx), max(y1, fy)
                    if (x2 - x1) > 10 and (y2 - y1) > 10:
                        self._roi = (x1, y1, x2, y2)
                        self._roi_preview = None
                        self._roi_drag_start = None
                        self._roi_btn.setChecked(False)
                        self._roi_clear_btn.setEnabled(True)
                        w, h = x2 - x1, y2 - y1
                        self._roi_status_lbl.setText(f'Area: {x1},{y1} → {x2},{y2}  ({w}×{h}px)')
                        # Persist as fractions
                        if self._current_frame is not None:
                            fh, fw = self._current_frame.shape[:2]
                            cfg = _load_webcam_config()
                            cfg['roi'] = [x1/fw, y1/fh, x2/fw, y2/fh]
                            _save_webcam_config(cfg)
        return super().eventFilter(obj, event)

    def _populate_cameras(self):
        """Scan indices 0-3 for cameras that actually open, then pre-select default."""
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()

        available = []
        if OPENCV_AVAILABLE:
            for i in range(4):
                try:
                    cap = cv2.VideoCapture(i)
                    if cap and cap.isOpened():
                        available.append(i)
                    if cap:
                        cap.release()
                except Exception:
                    pass
        if not available:
            available = list(range(2))   # fallback

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
        # Verify the camera actually produces frames (some indices report as
        # "opened" on Windows but return no real frames)
        ok, _ = cap.read()
        if not ok:
            cap.release()
            self.camera_available = False
            self.feed_label.setText(f'Camera {index} opened but returned no frames.\nTry a different camera.')
            self.status_label.setText(f'Status: Camera {index} not usable')
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
            # Always show the raw feed even if detection crashes
            self._show_frame(frame)

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
        self._current_frame = frame  # used by ROI label-to-frame mapping

        # Resolve saved ROI fractions on first frame after camera opens
        if hasattr(self, '_saved_roi_fractions') and self._saved_roi_fractions:
            fh, fw = frame.shape[:2]
            rx1f, ry1f, rx2f, ry2f = self._saved_roi_fractions
            self._roi = (int(rx1f * fw), int(ry1f * fh),
                         int(rx2f * fw), int(ry2f * fh))
            self._roi_clear_btn.setEnabled(True)
            x1, y1, x2, y2 = self._roi
            self._roi_status_lbl.setText(
                f'Area: {x1},{y1} → {x2},{y2}  ({x2-x1}×{y2-y1}px)')
            self._saved_roi_fractions = None   # only resolve once

        # Crop to ROI before running detection
        roi_offset = (0, 0)
        work_frame = frame
        if self._roi:
            x1, y1, x2, y2 = self._roi
            fh, fw = frame.shape[:2]
            x1c, y1c = max(0, x1), max(0, y1)
            x2c, y2c = min(fw, x2), min(fh, y2)
            if x2c > x1c + 20 and y2c > y1c + 20:
                work_frame = frame[y1c:y2c, x1c:x2c]
                roi_offset = (x1c, y1c)

        dets, cands = _analyze_frame(work_frame)

        # Offset detection rects back to full-frame coords
        if roi_offset != (0, 0):
            ox, oy = roi_offset
            for item in dets + cands:
                rx, ry, rw, rh = item['rect']
                item['rect'] = (rx + ox, ry + oy, rw, rh)

        self.current_detections = dets
        overlay = self._draw_overlay(frame.copy(), dets, cands)

        # Draw ROI rectangle on overlay
        if self._roi:
            x1, y1, x2, y2 = self._roi
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (50, 200, 255), 2)
            cv2.putText(overlay, 'Detection Area', (x1 + 4, y1 + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (50, 200, 255), 1, cv2.LINE_AA)
        # Draw in-progress ROI drag preview
        if self._roi_preview:
            px1, py1, px2, py2 = self._roi_preview
            cv2.rectangle(overlay, (px1, py1), (px2, py2), (0, 255, 200), 1)

        # Debug counter on frame
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
                self._show_confirm(d1_val, d2_val)
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
            self._show_confirm(d1, d2)

    def use_manual_result(self):
        self._submit_roll(self.manual_die1.value(), self.manual_die2.value())

    # ── Confirmation panel logic ───────────────────────────────────────────────

    def _show_confirm(self, d1: int, d2: int):
        """
        Show the confirmation panel for a stable detection result.
        Pauses further detection; the user must Accept or Edit+Submit.
        """
        # Apply learned bias before showing (low-confidence correction)
        d1_show, d2_show = self._apply_bias_if_needed(d1, d2)

        self._pending_detected = (d1, d2)          # original detected values
        self._pending_frame    = (self.current_frame.copy()
                                  if self.current_frame is not None else None)

        horse = d1_show + d2_show
        self._confirm_result_lbl.setText(
            f'  {d1_show}  +  {d2_show}  =  {horse}   →   Horse #{horse}')
        self._confirm_d1.setValue(d1_show)
        self._confirm_d2.setValue(d2_show)
        self._confirm_edit_btn.setChecked(False)
        self._confirm_edit_row.setVisible(False)

        # Show correction count in stats label
        self._refresh_training_stats()

        self._confirm_grp.setVisible(True)
        self.use_result_button.setEnabled(False)   # block while confirming

    def _on_confirm_accept(self):
        """User accepts the detected values — log as correct and submit."""
        if self._pending_detected is None:
            return
        d1_det, d2_det = self._pending_detected
        d1_use, d2_use = self._apply_bias_if_needed(d1_det, d2_det)

        # Log: detected == true (no correction needed)
        _save_training_entry(self._pending_frame,
                             d1_det, d2_det, d1_use, d2_use)
        self._hide_confirm()
        self._submit_roll(d1_use, d2_use)

    def _on_confirm_edit_toggle(self, checked: bool):
        self._confirm_edit_row.setVisible(checked)

    def _on_confirm_submit(self):
        """User submitted a manual correction — log it and submit corrected roll."""
        if self._pending_detected is None:
            return
        d1_det, d2_det = self._pending_detected
        d1_true = self._confirm_d1.value()
        d2_true = self._confirm_d2.value()

        # Log: detected vs corrected values + frame
        _save_training_entry(self._pending_frame,
                             d1_det, d2_det, d1_true, d2_true)

        # Reload bias table in case this correction pushed us over a threshold
        self._bias_table = _load_bias_table()

        self._hide_confirm()
        self._submit_roll(d1_true, d2_true)

    def _hide_confirm(self):
        self._confirm_grp.setVisible(False)
        self._confirm_edit_btn.setChecked(False)
        self._confirm_edit_row.setVisible(False)
        self._pending_detected = None
        self._pending_frame    = None

    def _apply_bias_if_needed(self, d1: int, d2: int) -> tuple:
        """
        Apply learned bias corrections (from training log).
        Bias is only applied when we have strong evidence (≥5 corrections,
        ≥75 % one-way) — see _load_bias_table().  This corrects systematic
        misreadings without risking false corrections on confident reads.
        """
        if not self._bias_table:
            return d1, d2
        # Get confidence of most recent detections if available
        confs = {d['value']: d['conf'] for d in self.current_detections}
        d1_out = d1
        d2_out = d2
        if d1 in self._bias_table and confs.get(d1, 1.0) < 0.75:
            d1_out = self._bias_table[d1]
        if d2 in self._bias_table and confs.get(d2, 1.0) < 0.75:
            d2_out = self._bias_table[d2]
        return d1_out, d2_out

    def _refresh_training_stats(self):
        """Update the small stats label in the confirmation panel."""
        try:
            if not _CORRECTIONS_LOG.exists():
                self._training_stats_lbl.setText('Training log: 0 entries')
                return
            with open(_CORRECTIONS_LOG, encoding='utf-8') as f:
                log = json.load(f)
            total     = len(log)
            corrected = sum(1 for e in log if e.get('was_corrected'))
            bias_info = (f'  |  Bias table: {len(self._bias_table)} value(s)'
                         if self._bias_table else '')
            self._training_stats_lbl.setText(
                f'Training log: {total} entries, {corrected} corrected{bias_info}')
        except Exception:
            self._training_stats_lbl.setText('')

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
