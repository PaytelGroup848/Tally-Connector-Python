"""
CtrlBooks - Sync Date Range Dialog
-----------------------------------
Allows selecting and configuring the Financial Year / Date Range for a company's data sync.
Supports quick FY presets (e.g. FY 2024-25, FY 2025-26, All Time) as well as custom date pickers.
"""

from typing import Optional, Tuple
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDateEdit, QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor


class SyncDateDialog(QDialog):
    def __init__(
        self,
        company_name: str,
        initial_from_date: Optional[str] = None,
        initial_to_date: Optional[str] = None,
        is_change_mode: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.company_name = company_name
        self.is_change_mode = is_change_mode
        self._block_signals = False

        self.setWindowTitle("Sync Financial Year & Date Range")
        self.setFixedWidth(430)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #FFFFFF;
                border-radius: 12px;
            }
        """)

        # Drop shadow effect
        try:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(20)
            shadow.setColor(QColor(15, 23, 42, 40))
            shadow.setOffset(0, 4)
            self.setGraphicsEffect(shadow)
        except Exception:
            pass

        self.init_ui(initial_from_date, initial_to_date)

    def init_ui(self, initial_from: Optional[str], initial_to: Optional[str]):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        # Header Title
        title_text = "📅 Change Sync Date Range" if self.is_change_mode else "📅 Select Sync Financial Year"
        lbl_title = QLabel(title_text)
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #0F172A;")
        layout.addWidget(lbl_title)

        # Subtitle with company name
        lbl_sub = QLabel(f"Company: <b style='color: #059669;'>{self.company_name}</b>")
        lbl_sub.setStyleSheet("font-size: 12px; color: #475569;")
        layout.addWidget(lbl_sub)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #E2E8F0; border: none; max-height: 1px;")
        layout.addWidget(divider)

        # Preset Dropdown Label
        lbl_preset = QLabel("Financial Year Preset:")
        lbl_preset.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        layout.addWidget(lbl_preset)

        self.combo_presets = QComboBox()
        self.combo_presets.addItems([
            "FY 2025-2026 (01-Apr-2025 to 31-Mar-2026)",
            "FY 2024-2025 (01-Apr-2024 to 31-Mar-2025)",
            "FY 2023-2024 (01-Apr-2023 to 31-Mar-2024)",
            "FY 2022-2023 (01-Apr-2022 to 31-Mar-2023)",
            "All Records (Complete Data)",
            "Custom Date Range",
        ])
        self.combo_presets.setFixedHeight(36)
        self.combo_presets.setStyleSheet("""
            QComboBox {
                border: 1.5px solid #CBD5E1;
                border-radius: 8px;
                padding: 0 10px;
                font-size: 12px;
                font-weight: 600;
                color: #0F172A;
                background-color: #F8FAFC;
            }
            QComboBox:focus {
                border-color: #10B981;
                background-color: #FFFFFF;
            }
        """)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        layout.addWidget(self.combo_presets)

        # Dates Container
        dates_row = QHBoxLayout()
        dates_row.setSpacing(12)

        # From Date
        v_from = QVBoxLayout()
        v_from.setSpacing(4)
        lbl_from = QLabel("From Date:")
        lbl_from.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd-MM-yyyy")
        self.date_from.setFixedHeight(34)
        self.date_from.setStyleSheet("""
            QDateEdit {
                border: 1.5px solid #CBD5E1;
                border-radius: 8px;
                padding: 0 8px;
                font-size: 11px;
                font-weight: 600;
                color: #0F172A;
                background-color: #FFFFFF;
            }
            QDateEdit:focus {
                border-color: #10B981;
            }
        """)
        self.date_from.dateChanged.connect(self._on_date_manually_changed)
        v_from.addWidget(lbl_from)
        v_from.addWidget(self.date_from)
        dates_row.addLayout(v_from)

        # To Date
        v_to = QVBoxLayout()
        v_to.setSpacing(4)
        lbl_to = QLabel("To Date:")
        lbl_to.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd-MM-yyyy")
        self.date_to.setFixedHeight(34)
        self.date_to.setStyleSheet("""
            QDateEdit {
                border: 1.5px solid #CBD5E1;
                border-radius: 8px;
                padding: 0 8px;
                font-size: 11px;
                font-weight: 600;
                color: #0F172A;
                background-color: #FFFFFF;
            }
            QDateEdit:focus {
                border-color: #10B981;
            }
        """)
        self.date_to.dateChanged.connect(self._on_date_manually_changed)
        v_to.addWidget(lbl_to)
        v_to.addWidget(self.date_to)
        dates_row.addLayout(v_to)

        layout.addLayout(dates_row)

        # Explanatory tip
        lbl_info = QLabel("ℹ️ Tally Prime se sirf is date range ka data sync hoga.")
        lbl_info.setStyleSheet("font-size: 11px; color: #64748B; font-style: italic;")
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(38)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
                color: #1E293B;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)

        save_label = "Save && Resync" if self.is_change_mode else "Save && Sync Now"
        self.btn_save = QPushButton(save_label)
        self.btn_save.setFixedHeight(38)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 800;
                padding: 0 20px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.btn_save.clicked.connect(self.accept)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        layout.addLayout(btn_row)

        # Set initial values
        self._apply_initial_dates(initial_from, initial_to)

    def _apply_initial_dates(self, initial_from: Optional[str], initial_to: Optional[str]):
        self._block_signals = True
        try:
            if initial_from and initial_to:
                df = self._parse_qdate(initial_from)
                dt = self._parse_qdate(initial_to)
                self.date_from.setDate(df)
                self.date_to.setDate(dt)

                # Match preset if possible
                matched = False
                for idx in range(self.combo_presets.count()):
                    txt = self.combo_presets.itemText(idx)
                    p_from, p_to, _ = self._get_preset_dates(idx)
                    if p_from == df and p_to == dt:
                        self.combo_presets.setCurrentIndex(idx)
                        matched = True
                        break
                if not matched:
                    # Select Custom
                    self.combo_presets.setCurrentIndex(5)
            else:
                # Default to FY 2024-2025
                self.combo_presets.setCurrentIndex(1)
                p_from, p_to, _ = self._get_preset_dates(1)
                self.date_from.setDate(p_from)
                self.date_to.setDate(p_to)
        finally:
            self._block_signals = False

    def _parse_qdate(self, s: str) -> QDate:
        clean = str(s).strip()
        for fmt in ("yyyy-MM-dd", "dd-MM-yyyy", "yyyyMMdd"):
            qd = QDate.fromString(clean, fmt)
            if qd.isValid():
                return qd
        return QDate.currentDate()

    def _get_preset_dates(self, idx: int) -> Tuple[QDate, QDate, str]:
        if idx == 0:  # FY 2025-26
            return QDate(2025, 4, 1), QDate(2026, 3, 31), "FY 2025-2026"
        elif idx == 1:  # FY 2024-25
            return QDate(2024, 4, 1), QDate(2025, 3, 31), "FY 2024-2025"
        elif idx == 2:  # FY 2023-24
            return QDate(2023, 4, 1), QDate(2024, 3, 31), "FY 2023-2024"
        elif idx == 3:  # FY 2022-23
            return QDate(2022, 4, 1), QDate(2023, 3, 31), "FY 2022-2023"
        elif idx == 4:  # All Records
            return QDate(2000, 1, 1), QDate(2099, 12, 31), "All Records"
        else:
            return self.date_from.date(), self.date_to.date(), "Custom"

    def _on_preset_changed(self, idx: int):
        if self._block_signals:
            return
        if idx == 5:  # Custom
            return
        p_from, p_to, _ = self._get_preset_dates(idx)
        self._block_signals = True
        try:
            self.date_from.setDate(p_from)
            self.date_to.setDate(p_to)
        finally:
            self._block_signals = False

    def _on_date_manually_changed(self):
        if self._block_signals:
            return
        # If dates don't match selected preset, switch preset to Custom
        curr_idx = self.combo_presets.currentIndex()
        if curr_idx != 5:
            p_from, p_to, _ = self._get_preset_dates(curr_idx)
            if self.date_from.date() != p_from or self.date_to.date() != p_to:
                self._block_signals = True
                try:
                    self.combo_presets.setCurrentIndex(5)  # Custom
                finally:
                    self._block_signals = False

    def get_dates(self) -> Tuple[str, str, str]:
        """Returns (from_date_iso, to_date_iso, fy_label) formatted as YYYY-MM-DD."""
        f_str = self.date_from.date().toString("yyyy-MM-dd")
        t_str = self.date_to.date().toString("yyyy-MM-dd")
        preset_idx = self.combo_presets.currentIndex()
        if preset_idx < 5:
            _, _, fy_label = self._get_preset_dates(preset_idx)
        else:
            fy_label = f"{f_str} to {t_str}"
        return f_str, t_str, fy_label

