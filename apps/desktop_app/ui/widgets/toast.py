"""
CtrlBooks - Toast Notification Widget
-------------------------------------------------
Non-intrusive floating feedback notification toast.
Always positioned at the bottom-right corner of the active screen.
"""

from typing import List, Optional
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
from PySide6.QtGui import QGuiApplication, QColor, QFontMetrics
from PySide6.QtCore import Qt, QTimer
from apps.desktop_app.styles.colors import Colors

_active_toasts: List["ToastNotification"] = []

_TOAST_THEMES = {
    "success": (Colors.SUCCESS_BG, "#065F46", Colors.SUCCESS_BORDER, "#10B981", "✓"),
    "error": (Colors.ERROR_BG, Colors.ERROR_FG, Colors.ERROR_BORDER, "#EF4444", "✕"),
    "info": (Colors.INFO_BG, Colors.INFO_FG, Colors.INFO_BORDER, "#2563EB", "i"),
}


class ToastNotification(QWidget):
    def __init__(self, message: str, toast_type: str = "success", parent=None, duration_ms: int = 4000):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.ToolTip
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        bg, fg, border, icon_bg, icon = _TOAST_THEMES.get(toast_type, _TOAST_THEMES["success"])

        # Outer transparent wrapper reserves padding for the card's drop shadow so corners stay artifact-free
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 10, 12, 14)

        self.card = QFrame(self)
        self.card.setObjectName("ToastCard")
        self.card.setStyleSheet(f"""
            QFrame#ToastCard {{
                background-color: {bg};
                border: 1.5px solid {border};
                border-radius: 10px;
            }}
        """)

        try:
            shadow = QGraphicsDropShadowEffect(self.card)
            shadow.setBlurRadius(18)
            shadow.setColor(QColor(15, 23, 42, 45))
            shadow.setOffset(0, 4)
            self.card.setGraphicsEffect(shadow)
        except Exception:
            pass

        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(12, 9, 16, 9)
        card_layout.setSpacing(10)

        self.icon_badge = QLabel(icon, self.card)
        self.icon_badge.setFixedSize(20, 20)
        self.icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {icon_bg};
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: 11px;
                font-weight: 900;
            }}
        """)
        card_layout.addWidget(self.icon_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        clean_msg = str(message or "")
        self.lbl = QLabel(clean_msg, self.card)
        self.lbl.setStyleSheet(f"""
            QLabel {{
                color: {fg};
                font-weight: 700;
                font-size: 12px;
                border: none;
                background: transparent;
            }}
        """)
        # Only wrap genuinely long messages; short notices stay cleanly single-line instead of collapsing width
        max_text_width = 420
        measure_font = self.lbl.font()
        measure_font.setPixelSize(12)
        measure_font.setBold(True)
        if QFontMetrics(measure_font).horizontalAdvance(clean_msg) > max_text_width:
            self.lbl.setWordWrap(True)
            self.lbl.setFixedWidth(max_text_width)
        else:
            self.lbl.setWordWrap(False)

        card_layout.addWidget(self.lbl, 1, Qt.AlignmentFlag.AlignVCenter)
        root_layout.addWidget(self.card)

        self.setMaximumWidth(560)
        self.destroyed.connect(self._cleanup_active)

        QTimer.singleShot(duration_ms, self.close)

    def _cleanup_active(self):
        global _active_toasts
        if self in _active_toasts:
            _active_toasts.remove(self)

    def reposition_to_bottom_right(self):
        """Positions this toast at the bottom-right corner of the active/primary screen."""
        try:
            self.adjustSize()
            screen = None
            if self.parent() and hasattr(self.parent(), "window"):
                p_win = self.parent().window()
                if p_win and hasattr(p_win, "screen") and p_win.screen():
                    screen = p_win.screen()
            if not screen:
                screen = QGuiApplication.primaryScreen()

            if screen:
                geo = screen.availableGeometry()
                margin_x = 24
                margin_y = 24

                # Calculate vertical offset for stacking multiple active toasts
                offset_y = 0
                for t in _active_toasts:
                    if t is not self and t.isVisible():
                        offset_y += t.height() + 8

                x = geo.x() + geo.width() - self.width() - margin_x
                y = geo.y() + geo.height() - self.height() - margin_y - offset_y
                self.move(max(geo.x(), x), max(geo.y(), y))
        except Exception:
            pass

    def show(self):
        if self not in _active_toasts:
            _active_toasts.append(self)
        self.reposition_to_bottom_right()
        super().show()
        self.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self.reposition_to_bottom_right()

    def closeEvent(self, event):
        self._cleanup_active()
        super().closeEvent(event)

    @classmethod
    def show_toast(cls, parent, message: str, toast_type: str = "success", duration_ms: int = 3500):
        """Helper to create, position, and show a toast notification in bottom-right corner."""
        try:
            toast = cls(message, toast_type=toast_type, parent=parent, duration_ms=duration_ms)
            toast.show()
            return toast
        except Exception:
            return None
