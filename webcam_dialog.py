"""
webcam_dialog.py
Webcam-based dice reader for Derby Dash.

Detection pipeline
──────────────────
1.  _find_die_candidates()  – multi-method (HSV / Canny / Otsu) rectangle
                              detection to locate each die face in the frame.
2.  _match_orb()            – ORB feature matching against reference photos.
                              Primary classifier when reference images are loaded.
3.  _count_pips()           – fallback: connected-component pip counting.
4.  _detect_die_value()     – combines ORB + pip results; boost when they agree.
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
    Pip-first die localization: find dark circular pip blobs, cluster into dice.
    This approach is specifically designed for white dice on cream/light backgrounds
    where die edges have poor contrast but dark pips are highly visible.
    Falls back to CLAHE+Otsu for other setups.
    """
    fh, fw = frame.shape[:2]
    fa     = fh * fw
    gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur   = cv2.GaussianBlur(gray, (5, 5), 0)
    found: List[Tuple[int,int,int,int]] = []

    # ── Primary: pip-first clustering ────────────────────────────────────────
    # Dark pips become bright blobs in inverted threshold — very high contrast
    # regardless of whether the die face and background look similar.
    _, pip_thr = cv2.threshold(blur, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    pip_min = max(8, fa * 0.000012)   # min pip blob area (scales with resolution)
    pip_max = fa * 0.0020             # max pip blob area

    pip_pts: List[Tuple[int, int, int]] = []  # (cx, cy, size)

    for cnt in cv2.findContours(pip_thr, cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)[0]:
        area = cv2.contourArea(cnt)
        if not (pip_min <= area <= pip_max):
            continue
        peri = cv2.arcLength(cnt, True)
        if peri <= 0:
            continue
        circ = 4.0 * np.pi * area / (peri * peri)
        if circ < 0.40:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        pip_pts.append((x + w // 2, y + h // 2, max(w, h)))

    if pip_pts:
        sizes     = [p[2] for p in pip_pts]
        med_size  = float(np.median(sizes))
        clust_d   = med_size * 9.0  # pips on the same die fall within 9× pip size

        # BFS cluster — groups pips that are spatially close
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
                x1  = max(0, min(xs) - pad)
                y1  = max(0, min(ys) - pad)
                x2  = min(fw, max(xs) + pad)
                y2  = min(fh, max(ys) + pad)
                dw, dh = x2 - x1, y2 - y1
                if dw > 12 and dh > 12:
                    found.append((x1, y1, dw, dh))

    # ── Fallback: CLAHE + Otsu + RETR_TREE for darker/higher-contrast setups ─
    clahe  = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    gray_c = clahe.apply(gray)
    blur_c = cv2.GaussianBlur(gray_c, (5, 5), 0)

    def _check_sq(cnt):
        area = cv2.contourArea(cnt)
        if not (fa * 0.0005 <= area <= fa * 0.25):
            return None
        x, y, w, h = cv2.boundingRect(cnt)
        if h == 0 or not (0.70 <= w / h <= 1.45):
            return None
        if area / (w * h) < 0.45:
            return None
        return (x, y, w, h)

    for flags in (cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
                  cv2.THRESH_BINARY + cv2.THRESH_OTSU):
        _, thr2 = cv2.threshold(blur_c, 0, 255, flags)
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

def _count_pips(roi) -> Tuple[int, float]:
    """
    Count pips using the dice_recognizer circularity approach:
      - Otsu threshold (both polarities) + RETR_EXTERNAL
      - Keep contours with circularity > 0.55 and appropriate area
      - Black-hat morphology as 3rd vote (especially good for diagonal '3')
    Three independent votes; confidence based on agreement.
    """
    if not OPENCV_AVAILABLE or roi is None or roi.size == 0:
        return 0, 0.0
    if min(roi.shape[:2]) < 20:
        return 0, 0.0

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi.copy()
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    h, w = gray.shape
    roi_area = h * w
    min_pip  = max(6,  roi_area * 0.003)
    max_pip  = roi_area * 0.12

    def _circ_count(thr_img) -> int:
        cnts, _ = cv2.findContours(thr_img, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
        count = 0
        for cnt in cnts:
            area = cv2.contourArea(cnt)
            if not (min_pip <= area <= max_pip):
                continue
            peri = cv2.arcLength(cnt, True)
            if peri <= 0:
                continue
            circularity = 4.0 * np.pi * area / (peri * peri)
            if circularity > 0.55:
                count += 1
        return count

    votes = []

    # Votes 1 & 2: Otsu both polarities (dice_recognizer approach)
    for inv in (True, False):
        flags = (cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU if inv
                 else cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, thr = cv2.threshold(blur, 0, 255, flags)
        c = _circ_count(thr)
        if 1 <= c <= 6:
            votes.append(c)

    # Vote 3: black-hat morphology — finds dark pips regardless of Otsu polarity
    k = max(5, min(h, w) // 4)
    if k % 2 == 0:
        k += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    _, bh_thr = cv2.threshold(bh, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    c = _circ_count(bh_thr)
    if 1 <= c <= 6:
        votes.append(c)

    if not votes:
        return 0, 0.0
    winner, freq = Counter(votes).most_common(1)[0]
    conf = {3: 0.92, 2: 0.82, 1: 0.65}.get(freq, 0.65)
    return winner, conf


# ── Combined classifier ───────────────────────────────────────────────────────

def _detect_die_value(roi) -> Tuple[int, float, str]:
    """
    Returns (face_value, confidence 0-1, method_label).
    ORB matching is primary when reference images are loaded.
    Pip counting is the fallback and validator.
    """
    orb_val,  orb_conf  = _match_orb(roi)
    pip_val,  pip_conf  = _count_pips(roi)

    # Both agree → highest possible confidence
    if orb_val > 0 and pip_val > 0 and orb_val == pip_val:
        combined = min(0.97, max(orb_conf, pip_conf) + 0.15)
        return orb_val, combined, "orb+pips"

    # Strong ORB match (reference images loaded and matching well)
    if orb_conf >= 0.55 and orb_val > 0:
        return orb_val, orb_conf, "orb"

    # Decent pip result, no ORB (no reference images loaded or poor match)
    if pip_val > 0 and pip_conf >= 0.65:
        return pip_val, pip_conf, "pips"

    # Moderate ORB with some pip signal (different value is ok — ORB wins)
    if orb_conf >= 0.40 and orb_val > 0 and pip_val > 0:
        return orb_val, orb_conf, "orb"

    # Weak pip only
    if pip_val > 0 and pip_conf >= 0.50:
        return pip_val, pip_conf, "pips"

    return 0, 0.0, "?"


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
        x1, y1 = max(0, x - pad),    max(0, y - pad)
        x2, y2 = min(fw, x + rw + pad), min(fh, y + rh + pad)
        roi    = frame[y1:y2, x1:x2]

        if not _is_die_like(roi):
            continue

        val, conf, method = _detect_die_value(roi)
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
