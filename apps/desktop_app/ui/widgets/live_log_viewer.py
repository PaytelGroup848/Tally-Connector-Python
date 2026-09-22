import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QComboBox, QCheckBox
)
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextCursor, QFont, QGuiApplication

class QtLogEmitter(QObject):
    log_emitted = Signal(str, str, str)

class QtLogHandler(logging.Handler):
    """
    Custom logging.Handler that emits Qt Signals for safe cross-thread UI updates.
    """
    def __init__(self, emitter: QtLogEmitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord):
        try:
            logger_name = getattr(record, "name", "")
            if logger_name.startswith(("httpx", "httpcore", "urllib3", "uvicorn")):
                return

            msg = self.format(record)
            if "HTTP Request:" in msg or "/extract/companies" in msg or "/api/connector/commands" in msg:
                return

            timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            level_name = record.levelname.upper()
            self.emitter.log_emitted.emit(timestamp, level_name, msg)
        except Exception:
            self.handleError(record)

class LiveLogViewerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.emitter = QtLogEmitter()
        self.emitter.log_emitted.connect(self.append_log)

        for noisy in ["httpx", "httpcore", "urllib3", "uvicorn", "uvicorn.access"]:
            logging.getLogger(noisy).setLevel(logging.WARNING)

        self.handler = QtLogHandler(self.emitter)
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(self.handler)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        ctrl_layout = QHBoxLayout()

        title_lbl = QLabel("Live Sync Console")
        title_lbl.setStyleSheet("font-weight: bold; color: #1E293B; font-size: 12px;")

        self.level_combo = QComboBox()
        self.level_combo.addItems(["ALL", "INFO", "WARNING", "ERROR"])
        self.level_combo.setStyleSheet("padding: 2px 6px; font-size: 11px; border: 1px solid #CBD5E1; border-radius: 3px;")

        self.auto_scroll_chk = QCheckBox("Auto-scroll")
        self.auto_scroll_chk.setChecked(True)
        self.auto_scroll_chk.setStyleSheet("font-size: 11px; color: #475569;")

        self.copy_btn = QPushButton("Copy Logs")
        self.copy_btn.setFixedSize(80, 24)
        self.copy_btn.setStyleSheet(
            "QPushButton { background-color: #0284C7; color: white; border-radius: 3px; font-size: 11px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #0369A1; }"
        )
        self.copy_btn.clicked.connect(self.copy_to_clipboard)

        self.clear_btn = QPushButton("Clear Logs")
        self.clear_btn.setFixedSize(80, 24)
        self.clear_btn.setStyleSheet(
            "QPushButton { background-color: #64748B; color: white; border-radius: 3px; font-size: 11px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.clear_btn.clicked.connect(self.clear_logs)

        ctrl_layout.addWidget(title_lbl)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(QLabel("Level:"))
        ctrl_layout.addWidget(self.level_combo)
        ctrl_layout.addWidget(self.auto_scroll_chk)
        ctrl_layout.addWidget(self.copy_btn)
        ctrl_layout.addWidget(self.clear_btn)
        layout.addLayout(ctrl_layout)

        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumBlockCount(1000)
        font = QFont("Consolas" if os_is_windows() else "Courier", 10)
        self.log_display.setFont(font)
        self.log_display.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0F172A;
                color: #38BDF8;
                border: 1px solid #1E293B;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        layout.addWidget(self.log_display, stretch=1)

    def append_log(self, timestamp: str, level: str, message: str):
        filter_level = self.level_combo.currentText().upper()
        if filter_level != "ALL" and filter_level != level:
            return

        if level == "ERROR":
            color = "#F87171"
        elif level == "WARNING":
            color = "#FBBF24"
        else:
            color = "#38BDF8"

        formatted_html = f'<span style="color: #64748B;">[{timestamp}]</span> <span style="color: {color}; font-weight: bold;">[{level}]</span> <span style="color: #F8FAFC;">{escape_html(message)}</span>'
        self.log_display.appendHtml(formatted_html)

        if self.auto_scroll_chk.isChecked():
            self.log_display.moveCursor(QTextCursor.End)

    def clear_logs(self):
        self.log_display.clear()

    def copy_to_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(self.log_display.toPlainText())

def escape_html(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def os_is_windows() -> bool:
    import os
    return os.name == "nt"
