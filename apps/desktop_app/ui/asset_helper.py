import sys
import os
from pathlib import Path

def get_asset_path(filename: str) -> Path:
    """
    Robustly resolves assets across all execution environments:
    - Normal Python / development venv
    - PyInstaller onedir (_internal/apps/desktop_app/assets)
    - PyInstaller onefile (_MEIPASS/apps/desktop_app/assets)
    - Installed C:\\Program Files\\CtrlBooks\\
    """
    candidates = [
        # Relative to this helper file: apps/desktop_app/ui/asset_helper.py -> apps/desktop_app/assets
        Path(__file__).resolve().parents[1] / "assets" / filename,
        # Relative to main repo root
        Path(__file__).resolve().parents[2] / "apps" / "desktop_app" / "assets" / filename,
    ]

    # Check PyInstaller bundle temp
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.extend([
            Path(meipass) / "apps" / "desktop_app" / "assets" / filename,
            Path(meipass) / "assets" / filename,
        ])

    # Check executable folder
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / "_internal" / "apps" / "desktop_app" / "assets" / filename,
            exe_dir / "apps" / "desktop_app" / "assets" / filename,
            exe_dir / "assets" / filename,
        ])

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Return default expected path even if missing
    return candidates[0]


def create_more_dots_icon(color_hex: str = "#0F172A", size: int = 24):
    """
    Programmatically creates a crisp, bold, anti-aliased 3-dots icon (vertical ellipsis)
    that looks razor-sharp and clearly visible on any Windows screen or resolution.
    """
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush
    from PySide6.QtCore import Qt, QPointF

    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(color_hex)))
    painter.setPen(Qt.PenStyle.NoPen)

    cx = size / 2.0
    r = 2.5  # Solid, high-visibility 5px diameter dots
    gap = 6.5
    cy = size / 2.0

    painter.drawEllipse(QPointF(cx, cy - gap), r, r)
    painter.drawEllipse(QPointF(cx, cy), r, r)
    painter.drawEllipse(QPointF(cx, cy + gap), r, r)
    painter.end()

    return QIcon(pix)


_TALLY_PIXMAP_CACHE = {}

def get_tally_prime_pixmap(width: int = 28, height: int = 28):
    """
    Returns a cached, high-definition QPixmap of the official TallyPrime icon,
    scaled smoothly with Qt.TransformationMode.SmoothTransformation.
    """
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import Qt

    key = (width, height)
    if key in _TALLY_PIXMAP_CACHE:
        return _TALLY_PIXMAP_CACHE[key]

    path = get_asset_path("tally_prime.png")
    if not path.exists():
        path = get_asset_path("tally_prime_user_crop.png")

    if path.exists():
        src = QPixmap(str(path))
        if not src.isNull():
            pix = src.scaled(
                width, height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            _TALLY_PIXMAP_CACHE[key] = pix
            return pix

    return QPixmap()


def create_tally_logo_label(width: int = 28, height: int = 28):
    """
    Creates a QLabel displaying the crisp, HD official TallyPrime icon.
    """
    from PySide6.QtWidgets import QLabel
    from PySide6.QtCore import Qt

    lbl = QLabel()
    lbl.setFixedSize(width, height)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setToolTip("TallyPrime")

    pix = get_tally_prime_pixmap(width, height)
    if not pix.isNull():
        lbl.setPixmap(pix)
        lbl.setStyleSheet("border: none; background: transparent;")
    else:
        lbl.setText("TP")
        lbl.setStyleSheet("""
            QLabel {
                background-color: #149EC2;
                color: #FFFFFF;
                font-weight: 900;
                font-size: 11px;
                border-radius: 6px;
            }
        """)
    return lbl


