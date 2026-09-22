"""
CtrlBooks - Reusable Confirmation Modal Dialog
---------------------------------------------------------
Displays clean confirmation modal for destructive or major actions.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from apps.desktop_app.styles.colors import Colors

class ConfirmDialog(QDialog):
    def __init__(self, title: str, message: str, confirm_text: str = "Confirm", is_danger: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        icon_symbol = "⚠️" if is_danger else "❓"
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel(icon_symbol)
        icon_lbl.setStyleSheet("font-size: 24px;")

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {Colors.TEXT_PRIMARY};")

        header_row.addWidget(icon_lbl)
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        layout.addLayout(header_row)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; line-height: 1.4;")
        layout.addWidget(msg_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("class", "secondary")
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QPushButton(confirm_text)
        if is_danger:
            confirm_btn.setProperty("class", "danger")
        else:
            confirm_btn.setStyleSheet(f"background-color: {Colors.PRIMARY}; color: white;")
        confirm_btn.clicked.connect(self.accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)

        layout.addLayout(btn_row)
