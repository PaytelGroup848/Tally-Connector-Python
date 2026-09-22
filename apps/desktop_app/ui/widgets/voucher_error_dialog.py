


from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QWidget
)
from PySide6.QtCore import Qt

class VoucherErrorDialog(QDialog):
    """
    Modal dialog that alerts the user in clear English when an incoming voucher fails in Tally,
    explaining the root cause (why Tally rejected it) and actionable steps to resolve it.
    """

    def __init__(self, error_details: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Tally Import Error - Action Required")
        self.setMinimumWidth(560)
        self.setMaximumWidth(680)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #FFFFFF;
            }
        """)

        self.error_details = error_details or {}
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 28px;")
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        title_lbl = QLabel("Tally Voucher Creation Failed")
        title_lbl.setStyleSheet("font-size: 17px; font-weight: 800; color: #DC2626;")
        title_vbox.addWidget(title_lbl)

        subtitle_lbl = QLabel("Tally Prime rejected this incoming voucher entry from the cloud.")
        subtitle_lbl.setStyleSheet("font-size: 12px; color: #64748B;")
        title_vbox.addWidget(subtitle_lbl)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #E2E8F0; margin: 0px;")
        main_layout.addWidget(div)

        summary_card = QFrame()
        summary_card.setStyleSheet("""
            QFrame {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        s_layout = QVBoxLayout(summary_card)
        s_layout.setSpacing(6)

        v_type = self.error_details.get("voucher_type") or "Sales"
        v_num = self.error_details.get("voucher_number") or "N/A"
        company = self.error_details.get("company") or "Active Company"
        party = self.error_details.get("party") or "Cash"
        amount = self.error_details.get("amount", 0.0)
        date_str = self.error_details.get("date") or "N/A"

        row1 = QHBoxLayout()
        lbl_vch = QLabel(f"📄 <b>Voucher:</b> {v_type} #{v_num}")
        lbl_vch.setStyleSheet("font-size: 12px; color: #1E293B;")
        try:
            amt_formatted = f"₹{float(amount):,.2f}"
        except (ValueError, TypeError):
            amt_formatted = f"₹{amount}"
        lbl_amt = QLabel(f"💰 <b>Amount:</b> {amt_formatted}")
        lbl_amt.setStyleSheet("font-size: 12px; color: #0F172A; font-weight: 700;")
        row1.addWidget(lbl_vch)
        row1.addStretch()
        row1.addWidget(lbl_amt)
        s_layout.addLayout(row1)

        row2 = QHBoxLayout()
        lbl_comp = QLabel(f"🏢 <b>Company:</b> {company}")
        lbl_comp.setStyleSheet("font-size: 12px; color: #475569;")
        lbl_dt = QLabel(f"📅 <b>Date:</b> {date_str}")
        lbl_dt.setStyleSheet("font-size: 12px; color: #475569;")
        row2.addWidget(lbl_comp)
        row2.addStretch()
        row2.addWidget(lbl_dt)
        s_layout.addLayout(row2)

        lbl_pty = QLabel(f"👤 <b>Party/Customer:</b> {party}")
        lbl_pty.setStyleSheet("font-size: 12px; color: #475569;")
        s_layout.addWidget(lbl_pty)

        main_layout.addWidget(summary_card)

        reason_card = QFrame()
        reason_card.setStyleSheet("""
            QFrame {
                background-color: #FEF2F2;
                border: 1px solid #FECACA;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        r_layout = QVBoxLayout(reason_card)
        r_layout.setSpacing(6)

        r_title = QLabel("❌  Why Tally Rejected This Entry:")
        r_title.setStyleSheet("font-size: 13px; font-weight: 800; color: #991B1B;")
        r_layout.addWidget(r_title)

        reason_text = self.error_details.get("reason") or "Tally Prime encountered a validation exception while importing the voucher."
        r_desc = QLabel(reason_text)
        r_desc.setWordWrap(True)
        r_desc.setStyleSheet("font-size: 12px; color: #7F1D1D; line-height: 1.4;")
        r_layout.addWidget(r_desc)

        main_layout.addWidget(reason_card)

        action_card = QFrame()
        action_card.setStyleSheet("""
            QFrame {
                background-color: #EFF6FF;
                border: 1px solid #BFDBFE;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        a_layout = QVBoxLayout(action_card)
        a_layout.setSpacing(6)

        a_title = QLabel("💡  What You Need To Do To Fix It:")
        a_title.setStyleSheet("font-size: 13px; font-weight: 800; color: #1E40AF;")
        a_layout.addWidget(a_title)

        action_text = self.error_details.get("action") or "Please verify the voucher details in your web app and ensure the date, rate, and customer ledger are valid in Tally."
        a_desc = QLabel(action_text)
        a_desc.setWordWrap(True)
        a_desc.setStyleSheet("font-size: 12px; color: #1E3A8A; line-height: 1.4;")
        a_layout.addWidget(a_desc)

        main_layout.addWidget(action_card)

        tech_err = self.error_details.get("technical_error") or ""
        if tech_err and tech_err != reason_text:
            lbl_tech = QLabel(f"<b>Technical Details:</b> {tech_err}")
            lbl_tech.setWordWrap(True)
            lbl_tech.setStyleSheet("font-size: 10px; color: #94A3B8;")
            main_layout.addWidget(lbl_tech)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Dismiss")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 13px;
                padding: 8px 24px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            QPushButton:pressed {
                background-color: #1E40AF;
            }
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        main_layout.addLayout(btn_layout)

    @classmethod
    def show_error(cls, parent: Optional[QWidget], error_details: Dict[str, Any]) -> None:
        """Helper to create and display the error dialog modally."""
        try:
            dlg = cls(error_details, parent=parent)
            dlg.exec()
        except Exception as exc:
            from shared.logging_config import get_logger
            get_logger("app.ui.dialogs").error(f"Failed to display VoucherErrorDialog: {exc}")

