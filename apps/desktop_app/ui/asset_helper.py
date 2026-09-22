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
    from PySide6.QtCore import Qt

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

    painter.drawEllipse(cx - r, cy - gap - r, r * 2, r * 2)
    painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
    painter.drawEllipse(cx - r, cy + gap - r, r * 2, r * 2)
    painter.end()

    return QIcon(pix)

