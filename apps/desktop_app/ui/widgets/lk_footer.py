

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

class CtrlBooksFooter(QWidget):
    def __init__(self, phone: str = "+91 7564044692", email: str = "support@ctrlbooks.com", parent=None):
        super().__init__(parent)
        self.phone = phone
        self.email = email
        self.init_ui()

    def init_ui(self):
        self.setFixedHeight(42)
        self.setStyleSheet("background-color: #FFFFFF; border-top: 1px solid #E2E8F0;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 6, 24, 6)

        phone_lbl = QLabel(f"📞  {self.phone}")
        phone_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #334155; border: none; background: transparent;")

        email_lbl = QLabel(f"✉️  {self.email}")
        email_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #334155; border: none; background: transparent;")

        layout.addWidget(phone_lbl)
        layout.addStretch()
        layout.addWidget(email_lbl)


CtrlBooksFooter = CtrlBooksFooter
CtrlBooksFooter = CtrlBooksFooter
