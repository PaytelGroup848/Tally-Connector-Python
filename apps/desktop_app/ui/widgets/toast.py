"""
CtrlBooks - Toast Notification Widget
-------------------------------------------------
Non-intrusive floating feedback notification toast.
Always positioned at the bottom-right corner of the active screen.
"""

from typing import List, Optional
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QGraphicsDropShadowEffect
from PySide6.QtGui import QGuiApplication, QColor
from PySide6.QtCore import Qt, QTimer
from apps.desktop_app.styles.colors import Colors

_active_toasts: List["ToastNotification"] = []


class ToastNotification(QFrame):
    def __init__(self, message: str, toast_type: str = "success", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.ToolTip
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        bg, fg, border = Colors.SUCCESS_BG, Colors.SUCCESS_FG, Colors.SUCCESS_BORDER
        icon = "✓"

        if toast_type == "error":
            bg, fg, border = Colors.ERROR_BG, Colors.ERROR_FG, Colors.ERROR_BORDER
            icon = "✕"
        elif toast_type == "info":
            bg, fg, border = Colors.INFO_BG, Colors.INFO_FG, Colors.INFO_BORDER
            icon = "ℹ"

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QLabel {{
                color: {fg};
                font-weight: 600;
                font-size: 12px;
            }}
        """)

        # Clean subtle shadow for modern look
        try:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(16)
            shadow.setColor(QColor(15, 23, 42, 35))
            shadow.setOffset(0, 4)
            self.setGraphicsEffect(shadow)
        except Exception:
            pass

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)

        self.lbl = QLabel(f"{icon}  {message}")
        self.lbl.setWordWrap(True)
        layout.addWidget(self.lbl)

        self.setMaximumWidth(650)
        self.setMinimumHeight(38)

        # Connect cleanup on destroy
        self.destroyed.connect(self._cleanup_active)

        QTimer.singleShot(4000, self.close)

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
            toast = cls(message, toast_type=toast_type, parent=parent)
            toast.show()
            QTimer.singleShot(duration_ms, toast.close)
            return toast
        except Exception:
            return None
