

import os
import socket
import subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QScrollArea
)
from PySide6.QtCore import Signal, Qt, QThread
from apps.desktop_app.ui.widgets.lk_header import CtrlBooksHeader
from apps.desktop_app.ui.widgets.lk_footer import CtrlBooksFooter
from apps.backend.adapters.tally.request_builder import build_company_list_xml
from apps.backend.adapters.tally.response_parser import parse_company_list
import httpx

class AutoDetectWorker(QThread):
    detected_signal = Signal(dict)

    def run(self):
        result = {
            "tally_ok": False,
            "tally_port": 9000,
            "tally_companies": [],
        }

        tally_ports = [9000, 9001, 9002, 9003, 9004]
        for p in tally_ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                res = s.connect_ex(("127.0.0.1", p))
                s.close()

                if res == 0:
                    result["tally_ok"] = True
                    result["tally_port"] = p
                    xml_req = build_company_list_xml()
                    r = httpx.post(f"http://127.0.0.1:{p}/", content=xml_req, headers={"Content-Type": "text/xml"}, timeout=2.5)
                    if r.status_code == 200:
                        comp_dicts = parse_company_list(r.text)
                        result["tally_companies"] = [c["name"] for c in comp_dicts if "name" in c]
                    break
            except Exception:
                continue

        self.detected_signal.emit(result)

class ConnectionProbeScreen(QWidget):
    connection_established = Signal()
    connection_established_for_source = Signal(str)
    nav_requested = Signal(str)
    auto_detected = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tally_connected = False
        self._is_detecting = False
        self.auto_detected.connect(self.on_detected_result)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = CtrlBooksHeader()
        self.header.refresh_clicked.connect(self.check_connection)
        self.header.auto_detect_clicked.connect(self.run_auto_detect)
        self.header.nav_requested.connect(self.nav_requested.emit)
        layout.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #F8FAFC; }")

        body = QWidget()
        body.setStyleSheet("background-color: #F8FAFC;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 14, 18, 14)
        body_layout.setSpacing(14)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Central Elevated Card
        self.central_card = QFrame()
        self.central_card.setStyleSheet("""
            QFrame#CentralCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 16px;
            }
        """)
        self.central_card.setObjectName("CentralCard")

        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect(self.central_card)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(15, 23, 42, 14))
        shadow.setOffset(0, 3)
        self.central_card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.central_card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(14)

        # Header Row inside Card
        card_hdr_row = QHBoxLayout()
        card_hdr_row.setSpacing(8)

        tally_badge = QLabel("Tally")
        tally_badge.setFixedSize(38, 26)
        tally_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tally_badge.setStyleSheet("""
            QLabel {
                background-color: #F1F5F9;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                color: #DC2626;
                font-size: 11px;
                font-weight: 900;
                font-style: italic;
            }
        """)
        card_hdr_row.addWidget(tally_badge)

        title_lbl = QLabel("Tally Connection Probing")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        card_hdr_row.addWidget(title_lbl)

        card_hdr_row.addStretch()

        self.tally_status_lbl = QLabel("Checking Port 9000...")
        self.tally_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tally_status_lbl.setStyleSheet("""
            QLabel {
                background-color: #ECFDF5;
                color: #059669;
                font-size: 10px;
                font-weight: 700;
                padding: 3px 8px;
                border-radius: 10px;
                border: 1px solid #A7F3D0;
            }
        """)
        card_hdr_row.addWidget(self.tally_status_lbl)
        card_layout.addLayout(card_hdr_row)

        sub_lbl = QLabel("Connect Tally Prime to sync company ledgers, vouchers, and metadata.")
        sub_lbl.setStyleSheet("font-size: 11px; color: #64748B; border: none; background: transparent;")
        sub_lbl.setWordWrap(True)
        card_layout.addWidget(sub_lbl)

        # Section 1: Tally Prime Box
        self.tally_card = QFrame()
        self.tally_card.setStyleSheet("""
            QFrame {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
                padding: 8px;
            }
        """)
        t_card_layout = QVBoxLayout(self.tally_card)
        t_card_layout.setContentsMargins(14, 12, 14, 12)
        t_card_layout.setSpacing(12)

        t_info_row = QHBoxLayout()
        t_info_row.setSpacing(12)

        db_icon = QLabel("🗄️")
        db_icon.setFixedSize(38, 38)
        db_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        db_icon.setStyleSheet("""
            QLabel {
                background-color: #E0F2FE;
                border: 1px solid #BAE6FD;
                border-radius: 10px;
                font-size: 18px;
            }
        """)
        t_info_row.addWidget(db_icon)

        t_text_box = QVBoxLayout()
        t_text_box.setSpacing(2)
        t_title = QLabel("Tally Prime")
        t_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        self.tally_desc = QLabel("HTTP Interface (Port 9000 / 9001) • TDL Data Export")
        self.tally_desc.setStyleSheet("font-size: 11px; color: #64748B; border: none; background: transparent;")
        self.tally_desc.setWordWrap(True)
        t_text_box.addWidget(t_title)
        t_text_box.addWidget(self.tally_desc)
        t_info_row.addLayout(t_text_box)

        t_info_row.addStretch()

        chev_down = QLabel("⌄")
        chev_down.setStyleSheet("font-size: 16px; font-weight: bold; color: #94A3B8; border: none; background: transparent;")
        t_info_row.addWidget(chev_down)
        t_card_layout.addLayout(t_info_row)

        t_btn_row = QHBoxLayout()
        t_btn_row.setSpacing(8)
        self.btn_sync_tally = QPushButton("🔄  Connect & Sync Data")
        self.btn_sync_tally.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sync_tally.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                font-weight: 800;
                font-size: 11px;
                padding: 7px 12px;
                border-radius: 7px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
            }
        """)
        self.btn_sync_tally.clicked.connect(lambda: self.on_source_connect_clicked("TALLY"))

        self.btn_open_tally = QPushButton("↗  Open Tally")
        self.btn_open_tally.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_tally.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #0284C7;
                font-weight: 700;
                font-size: 11px;
                padding: 6px 12px;
                border-radius: 7px;
                border: 1px solid #CBD5E1;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
                border-color: #0284C7;
            }
        """)
        self.btn_open_tally.clicked.connect(self.launch_tally)

        t_btn_row.addWidget(self.btn_sync_tally)
        t_btn_row.addWidget(self.btn_open_tally)
        t_btn_row.addStretch()
        t_card_layout.addLayout(t_btn_row)

        card_layout.addWidget(self.tally_card)

        # Section 2: Auto Detect Tally Port Box
        self.detect_card = QFrame()
        self.detect_card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detect_card.setStyleSheet("""
            QFrame {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
            QFrame:hover {
                background-color: #F1F5F9;
                border-color: #BAE6FD;
            }
        """)
        det_layout = QHBoxLayout(self.detect_card)
        det_layout.setContentsMargins(14, 12, 14, 12)
        det_layout.setSpacing(12)

        search_icon = QLabel("🔍")
        search_icon.setFixedSize(38, 38)
        search_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        search_icon.setStyleSheet("""
            QLabel {
                background-color: #E0F2FE;
                border: 1px solid #BAE6FD;
                border-radius: 10px;
                font-size: 16px;
            }
        """)
        det_layout.addWidget(search_icon)

        det_texts = QVBoxLayout()
        det_texts.setSpacing(2)
        det_title = QLabel("Auto Detect Tally Port")
        det_title.setStyleSheet("font-size: 13px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        det_sub = QLabel("Find Tally Prime automatically")
        det_sub.setStyleSheet("font-size: 11px; color: #64748B; border: none; background: transparent;")
        det_texts.addWidget(det_title)
        det_texts.addWidget(det_sub)
        det_layout.addLayout(det_texts)

        det_layout.addStretch()

        chev_right = QLabel("›")
        chev_right.setStyleSheet("font-size: 18px; font-weight: bold; color: #0284C7; border: none; background: transparent;")
        det_layout.addWidget(chev_right)

        self.btn_auto_detect = QPushButton()
        self.btn_auto_detect.setVisible(False)
        self.detect_card.mousePressEvent = lambda e: self.run_auto_detect()

        card_layout.addWidget(self.detect_card)
        body_layout.addWidget(self.central_card)

        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)
        self.footer = CtrlBooksFooter()
        layout.addWidget(self.footer)

        self.check_connection()

    def check_connection(self):
        self.run_auto_detect()

    def run_auto_detect(self):
        if getattr(self, "_is_detecting", False):
            return

        self._is_detecting = True
        self.btn_auto_detect.setEnabled(False)
        self.tally_status_lbl.setText("🟡 Scanning 9000...")
        self.tally_status_lbl.setStyleSheet("""
            QLabel {
                background-color: #FFFBEB;
                color: #D97706;
                font-size: 10px;
                font-weight: 700;
                padding: 3px 8px;
                border-radius: 10px;
                border: 1px solid #FDE68A;
            }
        """)

        import threading
        def _bg_scan():
            result = {
                "tally_ok": False,
                "tally_port": 9000,
                "tally_companies": [],
            }
            try:
                tally_ports = [9000, 9001, 9002, 9003, 9004]
                for p in tally_ports:
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(0.5)
                        res = s.connect_ex(("127.0.0.1", p))
                        s.close()

                        if res == 0:
                            result["tally_ok"] = True
                            result["tally_port"] = p
                            xml_req = build_company_list_xml()
                            r = httpx.post(f"http://127.0.0.1:{p}/", content=xml_req, headers={"Content-Type": "text/xml"}, timeout=1.5)
                            if r.status_code == 200:
                                comp_dicts = parse_company_list(r.text)
                                result["tally_companies"] = [c["name"] for c in comp_dicts if "name" in c]
                            break
                    except Exception:
                        continue
            finally:
                self._is_detecting = False
            self.auto_detected.emit(result)

        threading.Thread(target=_bg_scan, daemon=True, name="AutoDetectThread").start()

    def on_detected_result(self, res: dict):
        self.btn_auto_detect.setEnabled(True)

        if res.get("tally_ok"):
            self.tally_connected = True
            comps = res.get("tally_companies", [])
            port = res.get("tally_port", 9000)
            if comps:
                self.tally_status_lbl.setText(f"🟢 Port {port} ({len(comps)} Co.)")
            else:
                self.tally_status_lbl.setText(f"🟢 Port {port}")
            self.tally_status_lbl.setStyleSheet("""
                QLabel {
                    background-color: #ECFDF5;
                    color: #059669;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 3px 8px;
                    border-radius: 10px;
                    border: 1px solid #A7F3D0;
                }
            """)
            self.tally_card.setStyleSheet("""
                QFrame {
                    background-color: #F8FAFC;
                    border: 1px solid #A7F3D0;
                    border-radius: 12px;
                }
            """)
            self.header.update_connection_status(True, "Tally Prime", res.get("tally_port", 9000))
        else:
            self.tally_connected = False
            self.tally_status_lbl.setText("🔴 Disconnected")
            self.tally_status_lbl.setStyleSheet("""
                QLabel {
                    background-color: #FEF2F2;
                    color: #DC2626;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 3px 8px;
                    border-radius: 10px;
                    border: 1px solid #FECACA;
                }
            """)
            self.tally_card.setStyleSheet("""
                QFrame {
                    background-color: #F8FAFC;
                    border: 1px solid #FECACA;
                    border-radius: 12px;
                }
            """)
            self.header.update_connection_status(False)

    def on_source_connect_clicked(self, source_type: str):
        self.connection_established_for_source.emit(source_type)
        self.connection_established.emit()

    def launch_tally(self):
        possible_paths = [
            "C:\\Program Files\\TallyPrime\\tally.exe",
            "C:\\TallyPrime\\tally.exe",
            "C:\\Tally.ERP9\\tally.exe"
        ]
        for p in possible_paths:
            if os.path.exists(p):
                try:
                    subprocess.Popen([p])
                    break
                except Exception:
                    pass
        self.check_connection()
