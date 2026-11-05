"""
CtrlBooks - Sync Progress & Buffering Modal Dialog
---------------------------------------------------
Displays an animated buffering & progress dialog with background blur
when the user manually triggers a company data sync.
Counts percentage smoothly 1% by 1% and updates live extraction steps.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QFrame, QGraphicsDropShadowEffect, QGraphicsBlurEffect
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont


class SyncProgressDialog(QDialog):
    """
    Modern modal sync dialog featuring:
    - Background blur on parent window
    - Smooth 1-by-1 percentage counting animation
    - Live extracting/pushing status steps
    - Animated buffering state and auto-dismiss on completion
    """

    def __init__(
        self,
        company_name: str,
        source: str = "TALLY",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.company_name = company_name or "All Companies"
        self.source = source
        self.from_date = from_date
        self.to_date = to_date
        self.parent_window = parent.window() if parent and hasattr(parent, "window") else parent

        self._target_pct = 5
        self._current_pct = 0
        self._is_completed = False
        self._is_failed = False
        self._spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_idx = 0

        self.setWindowTitle("Syncing Data - CtrlBooks")
        self.setFixedWidth(460)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._setup_background_blur()
        self._init_ui()
        self._start_animation_timers()

    def _setup_background_blur(self):
        """Applies a smooth frosted-glass blur effect to the background content without blurring the dialog itself."""
        if self.parent_window:
            try:
                target = getattr(self.parent_window, "centralWidget", lambda: None)() or self.parent_window
                self._blur_target = target
                self._blur = QGraphicsBlurEffect(target)
                self._blur.setBlurRadius(10.0)
                target.setGraphicsEffect(self._blur)
            except Exception:
                self._blur = None
                self._blur_target = None
        else:
            self._blur = None
            self._blur_target = None

    def _remove_background_blur(self):
        """Removes the blur effect from the background when dialog closes."""
        if hasattr(self, "_blur_target") and self._blur_target:
            try:
                self._blur_target.setGraphicsEffect(None)
            except Exception:
                pass
        elif self.parent_window:
            try:
                self.parent_window.setGraphicsEffect(None)
            except Exception:
                pass

    def center_on_parent(self):
        """Positions the dialog in the exact center of the parent window or screen."""
        try:
            if self.parent_window and self.parent_window.isVisible():
                geo = self.parent_window.geometry()
                x = geo.x() + (geo.width() - self.width()) // 2
                y = geo.y() + (geo.height() - self.height()) // 2
                self.move(max(20, x), max(20, y))
            else:
                from PySide6.QtGui import QGuiApplication
                screen = QGuiApplication.primaryScreen()
                if screen:
                    screen_geo = screen.availableGeometry()
                    x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
                    y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
                    self.move(max(20, x), max(20, y))
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.center_on_parent()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)

        # Card container with rounded corners and border
        self.card = QFrame(self)
        self.card.setObjectName("SyncProgressCard")
        self.card.setStyleSheet("""
            QFrame#SyncProgressCard {
                background-color: #FFFFFF;
                border-radius: 18px;
                border: 1.5px solid #E2E8F0;
            }
        """)

        # Drop shadow effect
        try:
            shadow = QGraphicsDropShadowEffect(self.card)
            shadow.setBlurRadius(32)
            shadow.setColor(QColor(15, 23, 42, 65))
            shadow.setOffset(0, 8)
            self.card.setGraphicsEffect(shadow)
        except Exception:
            pass

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(14)

        # 1. Header layout (Icon + Title + Subtitle)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        self.icon_badge = QLabel("⚡")
        self.icon_badge.setFixedSize(44, 44)
        self.icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_badge.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ECFDF5, stop:1 #D1FAE5);
                color: #059669;
                font-size: 22px;
                border-radius: 22px;
                border: 1.5px solid #A7F3D0;
            }
        """)
        header_layout.addWidget(self.icon_badge)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        self.title_lbl = QLabel(f"Syncing {self.company_name}")
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #0F172A;")
        title_vbox.addWidget(self.title_lbl)

        date_suffix = f" • {self.from_date} to {self.to_date}" if self.from_date and self.to_date else ""
        self.sub_lbl = QLabel(f"Tally Prime (Live Extractor){date_suffix}")
        self.sub_lbl.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
        title_vbox.addWidget(self.sub_lbl)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()

        card_layout.addLayout(header_layout)

        # Subtle divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #F1F5F9; border: none; max-height: 1px;")
        card_layout.addWidget(divider)

        # 2. Percentage display & buffering spinner
        pct_layout = QHBoxLayout()
        pct_layout.setContentsMargins(0, 6, 0, 4)

        self.pct_lbl = QLabel("0%")
        self.pct_lbl.setStyleSheet("font-size: 38px; font-weight: 900; color: #10B981;")
        pct_layout.addWidget(self.pct_lbl)

        pct_layout.addStretch()

        self.spinner_lbl = QLabel("⠋ Buffering...")
        self.spinner_lbl.setStyleSheet("""
            QLabel {
                background-color: #F8FAFC;
                color: #059669;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 12px;
                border-radius: 8px;
                border: 1px solid #E2E8F0;
            }
        """)
        pct_layout.addWidget(self.spinner_lbl)

        card_layout.addLayout(pct_layout)

        # 3. Progress Bar (Modern rounded styled emerald chunk)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 5px;
                background-color: #F1F5F9;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                border-radius: 5px;
            }
        """)
        card_layout.addWidget(self.progress_bar)

        # 4. Live status step label
        self.status_lbl = QLabel("Initializing data sync with Tally Prime...")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #334155; min-height: 22px;")
        card_layout.addWidget(self.status_lbl)

        # Helper hint
        self.hint_lbl = QLabel("⚡ Please keep Tally Prime open until sync finishes")
        self.hint_lbl.setStyleSheet("font-size: 11px; color: #94A3B8; font-weight: 500;")
        card_layout.addWidget(self.hint_lbl)

        # 5. Action / Close button (initially hidden, shown on finish/error)
        self.btn_layout = QHBoxLayout()
        self.btn_layout.addStretch()

        self.action_btn = QPushButton("Done")
        self.action_btn.setVisible(False)
        self.action_btn.setFixedSize(110, 36)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 700;
                border-radius: 10px;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.action_btn.clicked.connect(self.accept)
        self.btn_layout.addWidget(self.action_btn)

        card_layout.addLayout(self.btn_layout)

        root_layout.addWidget(self.card)

    def _start_animation_timers(self):
        """Starts the smooth 1-by-1 counter timer and spinner animation timer."""
        # Fast counter timer: increments _current_pct 1% by 1% toward _target_pct
        self._counter_timer = QTimer(self)
        self._counter_timer.timeout.connect(self._step_counter)
        self._counter_timer.start(25)  # 25ms per tick for smooth animation

        # Spinner text rotation timer
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._step_spinner)
        self._spinner_timer.start(80)

    def _step_counter(self):
        """Smoothly steps the visible percentage 1% by 1%."""
        if self._current_pct < self._target_pct:
            self._current_pct += 1
            self.progress_bar.setValue(self._current_pct)
            self.pct_lbl.setText(f"{self._current_pct}%")

        if self._current_pct >= 100 and self._is_completed:
            self._counter_timer.stop()
            self._spinner_timer.stop()
            self._on_all_finished()

    def _step_spinner(self):
        """Updates the animated spinner character."""
        if not self._is_completed and not self._is_failed:
            self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
            frame = self._spinner_frames[self._spinner_idx]
            self.spinner_lbl.setText(f"{frame} Syncing...")

    # --- Worker Signal Connectors ---
    def on_progress_changed(self, val: int, text: str):
        """Slot connected to worker.progress_changed(int, str)."""
        safe_val = max(1, min(100, int(val or 0)))
        if safe_val > self._target_pct:
            self._target_pct = safe_val

        clean_text = str(text or "").strip()
        if clean_text:
            self.status_lbl.setText(clean_text)

    def on_sync_completed(self, msg: str):
        """Slot connected to worker.sync_completed(str)."""
        self._is_completed = True
        self._target_pct = 100
        # If counter already reached 100%, finalize immediately
        if self._current_pct >= 100:
            self._on_all_finished()

    def on_sync_failed(self, err_msg: str):
        """Slot connected to worker.sync_failed(str)."""
        self._is_failed = True
        self._counter_timer.stop()
        self._spinner_timer.stop()

        self.icon_badge.setText("⚠️")
        self.icon_badge.setStyleSheet("""
            QLabel {
                background: #FEF2F2;
                color: #DC2626;
                font-size: 22px;
                border-radius: 22px;
                border: 1.5px solid #FECACA;
            }
        """)
        self.title_lbl.setText("Sync Incomplete")
        self.spinner_lbl.setText("Failed")
        self.spinner_lbl.setStyleSheet("""
            QLabel {
                background-color: #FEF2F2;
                color: #DC2626;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 12px;
                border-radius: 8px;
                border: 1px solid #FECACA;
            }
        """)
        self.status_lbl.setText(f"Notice: {err_msg}")
        self.status_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #DC2626;")
        self.hint_lbl.setText("Check your Tally Prime connection or network and try again.")
        self.action_btn.setText("Close")
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #64748B;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 700;
                border-radius: 10px;
                border: none;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)
        self.action_btn.setVisible(True)

    def _on_all_finished(self):
        """Called when 100% is reached and worker confirmed completion."""
        self.icon_badge.setText("✅")
        self.icon_badge.setStyleSheet("""
            QLabel {
                background: #ECFDF5;
                color: #059669;
                font-size: 22px;
                border-radius: 22px;
                border: 1.5px solid #A7F3D0;
            }
        """)
        self.title_lbl.setText("Sync Complete!")
        self.spinner_lbl.setText("✓ 100% Synced")
        self.spinner_lbl.setStyleSheet("""
            QLabel {
                background-color: #ECFDF5;
                color: #059669;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 12px;
                border-radius: 8px;
                border: 1px solid #A7F3D0;
            }
        """)
        self.status_lbl.setText("All records successfully synchronized with Cloud!")
        self.status_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #059669;")
        self.hint_lbl.setText("Closing in 1 second...")

        # Auto-dismiss smoothly after 1.2 seconds
        QTimer.singleShot(1200, self.accept)

    def done(self, r: int):
        """Ensures background blur is always removed when dialog closes."""
        self._remove_background_blur()
        super().done(r)

    def closeEvent(self, event):
        """Ensures background blur is removed if dialog is closed."""
        self._remove_background_blur()
        super().closeEvent(event)

