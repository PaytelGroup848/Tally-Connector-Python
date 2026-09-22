"""
CtrlBooks - Toast Notification Widget
-------------------------------------------------
Non-intrusive floating feedback notification toast.
"""

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
from apps.desktop_app.styles.colors import Colors

class ToastNotification(QFrame):
    def __init__(self, message: str, toast_type: str = "success", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip)

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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        lbl = QLabel(f"{icon}  {message}")
        layout.addWidget(lbl)

        QTimer.singleShot(3500, self.close)

    @classmethod
    def show_toast(cls, parent, message: str, toast_type: str = "success", duration_ms: int = 3500):
        """Helper to create, position, and show a toast notification."""
        try:
            toast = cls(message, toast_type=toast_type, parent=parent)
            if parent is not None and hasattr(parent, "rect"):
                p_rect = parent.rect()
                toast.move(p_rect.center().x() - 100, p_rect.bottom() - 60)
            toast.show()
            QTimer.singleShot(duration_ms, toast.close)
            return toast
        except Exception:
            return None
