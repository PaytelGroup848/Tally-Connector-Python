"""
CtrlBooks - Desktop Application Main Launcher
--------------------------------------------------------
Main executable entry point for ctrlbooks.exe
Initializes the PySide6 QApplication, application icon, and ConnectorMainWindow shell.
"""

import sys
import ctypes
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "shared").exists():
    ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.desktop_app.ui.main_window import ConnectorMainWindow

import signal

def main():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ctrlbooks.desktop.1.0")
    except Exception:
        pass

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("CtrlBooks")
    app.setOrganizationName("CtrlBooks")
    app.setStyle("Fusion")

    # Enforce clean palette and base styling so Windows Dark Mode cannot invert/break colors
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F1F5F9"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1E293B"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#0F172A"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#DC2626"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#059669"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#10B981"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)

    app.setStyleSheet("""
        QWidget {
            color: #0F172A;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        }
        QMainWindow, QDialog {
            background-color: #F8FAFC;
        }
        QMenu {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            padding: 4px;
        }
        QMenu::item {
            background-color: transparent;
            color: #0F172A;
            padding: 6px 20px;
            border-radius: 4px;
        }
        QMenu::item:selected {
            background-color: #ECFDF5;
            color: #059669;
        }
        QMenu::separator {
            height: 1px;
            background-color: #E2E8F0;
            margin: 4px 8px;
        }
        QTableWidget {
            background-color: #FFFFFF;
            color: #0F172A;
            gridline-color: #E2E8F0;
        }
        QTableWidget::item {
            color: #0F172A;
        }
        QHeaderView::section {
            background-color: #F8FAFC;
            color: #475569;
            border: none;
            padding: 4px;
        }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
            background-color: #FFFFFF;
            color: #0F172A;
        }
        QToolTip {
            background-color: #1E293B;
            color: #FFFFFF;
            border: 1px solid #334155;
            border-radius: 4px;
            padding: 4px 8px;
        }
    """)

    def global_excepthook(exc_type, exc_value, exc_traceback):
        import traceback
        from shared.logging_config import get_logger
        logger = get_logger("app.crash_handler")
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.error(f"Unhandled exception prevented from crashing app: {exc_value}\n{tb_str}")

    sys.excepthook = global_excepthook

    from apps.desktop_app.ui.asset_helper import get_asset_path
    icon_path = get_asset_path("app_icon.ico")
    if not icon_path.exists():
        icon_path = get_asset_path("app_icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = ConnectorMainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()

