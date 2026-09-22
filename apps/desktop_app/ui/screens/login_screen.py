
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame, QStackedWidget, QGraphicsDropShadowEffect, QSizePolicy
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor

from apps.desktop_app.ui.widgets.lk_footer import CtrlBooksFooter
from shared.auth.cloud_auth_service import cloud_auth_service
from shared.logging_config import get_logger

logger = get_logger("app.ui.login")

class LoginScreen(QWidget):
    login_successful = Signal(str)
    otp_sent = Signal(bool, str, str)
    otp_verified = Signal(bool, str, str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_email = ""
        self.otp_sent.connect(self._on_otp_sent)
        self.otp_verified.connect(self._on_otp_verified)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        class DummyHeader:
            def __init__(self):
                self.refresh_btn = None
                self.sync_now_btn = None
                self.auto_detect_btn = None
                self.status_pulse = None
                self.last_sync_lbl = None
                self.menu_btn = None

        self.header = DummyHeader()

        body = QWidget()
        body.setStyleSheet("background-color: #F8FAFC;")
        body_layout = QVBoxLayout(body)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_layout.setContentsMargins(20, 20, 20, 20)

        card = QFrame()
        card.setFixedWidth(420)
        card.setStyleSheet("""
            QFrame#LoginCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 16px;
            }
            QLabel {
                background: transparent;
                border: none;
            }
        """)
        card.setObjectName("LoginCard")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(15, 23, 42, 16))
        shadow.setOffset(0, 6)
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 26, 30, 26)
        card_layout.setSpacing(14)

        emblem_box = QHBoxLayout()
        logo_lbl = QLabel()
        logo_lbl.setStyleSheet("background: transparent; border: none;")
        from PySide6.QtGui import QPixmap
        from apps.desktop_app.ui.asset_helper import get_asset_path
        logo_path = get_asset_path("ctrlbooks_logo.png")
        if logo_path.exists():
            pix = QPixmap(str(logo_path)).scaledToHeight(48, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            logo_lbl.setText("CtrlBooks")
            logo_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #0F172A;")
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emblem_box.addWidget(logo_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addLayout(emblem_box)

        sub_lbl = QLabel("SECURE CLOUD AUTHENTICATION")
        sub_lbl.setStyleSheet("font-size: 10px; font-weight: 800; color: #10B981; letter-spacing: 1.5px; border: none; background: transparent; margin-top: 2px;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(sub_lbl)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #E2E8F0; border: none; max-height: 1px;")
        card_layout.addWidget(divider)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("border: none; background: transparent;")
        self.stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        step1_w = QWidget()
        step1_w.setStyleSheet("background: transparent;")
        step1_layout = QVBoxLayout(step1_w)
        step1_layout.setContentsMargins(0, 0, 0, 0)
        step1_layout.setSpacing(6)

        input_title = QLabel("Sign in with Registered Email")
        input_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155; border: none; background: transparent;")
        input_title.setFixedHeight(18)
        step1_layout.addWidget(input_title)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Enter your email (e.g. user@cloudata.in)")
        self.email_input.setFixedHeight(38)
        self.email_input.setStyleSheet("""
            QLineEdit {
                border: 1.5px solid #CBD5E1;
                border-radius: 8px;
                padding: 0 12px;
                font-size: 13px;
                background-color: #FFFFFF;
                color: #0F172A;
            }
            QLineEdit:focus {
                border: 1.5px solid #10B981;
                background-color: #FFFFFF;
            }
        """)
        self.email_input.returnPressed.connect(self.handle_send_otp)
        step1_layout.addWidget(self.email_input)
        step1_layout.addSpacing(6)

        self.send_otp_btn = QPushButton("Send Cloud OTP  ➔")
        self.send_otp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_otp_btn.setFixedHeight(40)
        self.send_otp_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
            }
            QPushButton:pressed {
                background-color: #047857;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
                color: #E2E8F0;
            }
        """)
        self.send_otp_btn.clicked.connect(self.handle_send_otp)
        step1_layout.addWidget(self.send_otp_btn)

        self.stack.addWidget(step1_w)

        step2_w = QWidget()
        step2_w.setStyleSheet("background: transparent;")
        step2_layout = QVBoxLayout(step2_w)
        step2_layout.setContentsMargins(0, 0, 0, 0)
        step2_layout.setSpacing(6)

        self.otp_title = QLabel("Enter Verification Code")
        self.otp_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155; border: none; background: transparent;")
        self.otp_title.setFixedHeight(18)
        step2_layout.addWidget(self.otp_title)

        self.otp_sub = QLabel("OTP sent to your email address")
        self.otp_sub.setStyleSheet("font-size: 10px; color: #10B981; font-weight: 600; border: none; background: transparent;")
        self.otp_sub.setWordWrap(True)
        self.otp_sub.setFixedHeight(16)
        step2_layout.addWidget(self.otp_sub)

        self.otp_input = QLineEdit()
        self.otp_input.setPlaceholderText("Enter 6-Digit OTP")
        self.otp_input.setMaxLength(8)
        self.otp_input.setFixedHeight(38)
        self.otp_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.otp_input.setStyleSheet("""
            QLineEdit {
                border: 1.5px solid #CBD5E1;
                border-radius: 8px;
                padding: 0 10px;
                font-size: 16px;
                font-weight: bold;
                letter-spacing: 6px;
                background-color: #FFFFFF;
                color: #0F172A;
            }
            QLineEdit:focus {
                border: 1.5px solid #10B981;
                background-color: #FFFFFF;
            }
        """)
        self.otp_input.returnPressed.connect(self.handle_verify_otp)
        step2_layout.addWidget(self.otp_input)
        step2_layout.addSpacing(6)

        self.verify_btn = QPushButton("Verify OTP && Login  ➔")
        self.verify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.verify_btn.setFixedHeight(40)
        self.verify_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
            }
            QPushButton:pressed {
                background-color: #047857;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
                color: #E2E8F0;
            }
        """)
        self.verify_btn.clicked.connect(self.handle_verify_otp)
        step2_layout.addWidget(self.verify_btn)

        back_row = QHBoxLayout()
        back_row.setContentsMargins(2, 4, 2, 2)
        change_email_btn = QPushButton("← Change Email")
        change_email_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_email_btn.setStyleSheet("border: none; background: transparent; color: #64748B; font-size: 11px; font-weight: 600;")
        change_email_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        back_row.addWidget(change_email_btn)
        back_row.addStretch()

        resend_btn = QPushButton("Resend OTP 🔄")
        resend_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        resend_btn.setStyleSheet("border: none; background: transparent; color: #10B981; font-size: 11px; font-weight: 700;")
        resend_btn.clicked.connect(self.handle_send_otp)
        back_row.addWidget(resend_btn)
        step2_layout.addLayout(back_row)

        self.stack.addWidget(step2_w)
        card_layout.addWidget(self.stack)

        self.msg_lbl = QLabel("")
        self.msg_lbl.setStyleSheet("font-size: 11px; color: transparent; border: none; background: transparent; padding: 2px;")
        self.msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.hide()
        card_layout.addWidget(self.msg_lbl)

        sec_note = QLabel("🔒 Instant access to Tally & Cloud Synchronization")
        sec_note.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 500; border: none; background: transparent;")
        sec_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(sec_note)

        body_layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(body, stretch=1)

        self.footer = CtrlBooksFooter()
        layout.addWidget(self.footer)

    def _show_message(self, text: str, is_error: bool = False):
        self.msg_lbl.setText(text)
        if is_error:
            self.msg_lbl.setStyleSheet("""
                QLabel {
                    background-color: #FEF2F2;
                    border: 1px solid #FECACA;
                    color: #991B1B;
                    font-size: 11px;
                    font-weight: 600;
                    border-radius: 8px;
                    padding: 8px 12px;
                }
            """)
        else:
            self.msg_lbl.setStyleSheet("""
                QLabel {
                    background-color: #ECFDF5;
                    border: 1px solid #A7F3D0;
                    color: #065F46;
                    font-size: 11px;
                    font-weight: 600;
                    border-radius: 8px;
                    padding: 8px 12px;
                }
            """)
        self.msg_lbl.show()

    def handle_send_otp(self):
        email = self.email_input.text().strip()
        if not email or "@" not in email:
            self._show_message("Please enter a valid email address.", is_error=True)
            return

        self.current_email = email
        self._show_message("Connecting to authentication server...", is_error=False)
        self.send_otp_btn.setEnabled(False)

        import threading
        def _bg_send():
            try:
                ok, msg = cloud_auth_service.send_otp(email)
                self.otp_sent.emit(ok, msg, email)
            except Exception as exc:
                self.otp_sent.emit(False, f"Authentication error: {exc}", email)

        threading.Thread(target=_bg_send, daemon=True, name="SendOTPThread").start()

    def _on_otp_sent(self, ok: bool, msg: str, email: str):
        self.send_otp_btn.setEnabled(True)
        if ok:
            self._show_message(msg, is_error=False)
            self.otp_sub.setText(f"OTP sent to {email}")
            self.otp_input.clear()
            self.stack.setCurrentIndex(1)
            self.otp_input.setFocus()
        else:
            self._show_message(msg, is_error=True)

    def handle_verify_otp(self):
        otp = self.otp_input.text().strip()
        if not otp:
            self._show_message("Please enter the OTP code sent to your email.", is_error=True)
            return

        email = self.current_email or self.email_input.text().strip()
        self._show_message("Verifying code...", is_error=False)
        self.verify_btn.setEnabled(False)

        import threading
        def _bg_verify():
            try:
                ok, msg, user_data = cloud_auth_service.verify_otp(email, otp)
                self.otp_verified.emit(ok, msg, email, user_data or {})
            except Exception as exc:
                self.otp_verified.emit(False, f"Verification error: {exc}", email, {})

        threading.Thread(target=_bg_verify, daemon=True, name="VerifyOTPThread").start()

    def _on_otp_verified(self, ok: bool, msg: str, email: str, user_data: dict):
        self.verify_btn.setEnabled(True)
        if ok:
            self._show_message("Login successful! Redirecting...", is_error=False)
            self.login_successful.emit(email)
        else:
            self._show_message(msg, is_error=True)

