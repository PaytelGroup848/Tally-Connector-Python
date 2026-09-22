

from apps.desktop_app.styles.colors import Colors

def get_application_stylesheet() -> str:
    return f"""
    /* Global Reset & Windows Typography */
    QWidget {{
        font-family: 'Segoe UI', 'Arial', -apple-system, sans-serif;
        font-size: 12.5px;
        color: {Colors.TEXT_PRIMARY};
        background-color: {Colors.BG_MAIN};
    }}

    #HeaderWidget {{
        background-color: {Colors.BG_HEADER};
        border-bottom: 1px solid {Colors.BORDER_LIGHT};
    }}

    #FooterWidget {{
        background-color: {Colors.BG_FOOTER};
        border-top: 1px solid {Colors.BORDER_LIGHT};
    }}

    /* Compact White Panels with Thin Border */
    .QFrame[class="card"] {{
        background-color: {Colors.BG_CARD};
        border: 1px solid {Colors.BORDER_MEDIUM};
        border-radius: 6px;
    }}

    /* Buttons */
    QPushButton {{
        background-color: {Colors.PRIMARY};
        color: #FFFFFF;
        font-weight: 600;
        font-size: 12.5px;
        padding: 6px 16px;
        border-radius: 4px;
        border: 1px solid {Colors.PRIMARY};
    }}
    QPushButton:hover {{
        background-color: {Colors.PRIMARY_HOVER};
        border-color: {Colors.PRIMARY_HOVER};
    }}
    QPushButton:pressed {{
        background-color: {Colors.PRIMARY_ACTIVE};
    }}
    QPushButton:disabled {{
        background-color: {Colors.BORDER_LIGHT};
        color: {Colors.TEXT_MUTED};
        border-color: {Colors.BORDER_LIGHT};
    }}

    QPushButton[class="secondary"] {{
        background-color: {Colors.BG_CARD};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_MEDIUM};
    }}
    QPushButton[class="secondary"]:hover {{
        background-color: {Colors.BG_MUTED};
    }}

    QPushButton[class="danger"] {{
        background-color: {Colors.NOT_OK_FG};
        color: #FFFFFF;
        border: 1px solid {Colors.NOT_OK_FG};
    }}
    QPushButton[class="danger"]:hover {{
        background-color: #B91C1C;
    }}

    /* Form Inputs */
    QLineEdit, QComboBox, QSpinBox {{
        background-color: {Colors.BG_CARD};
        border: 1px solid {Colors.BORDER_MEDIUM};
        border-radius: 4px;
        padding: 6px 10px;
        color: {Colors.TEXT_PRIMARY};
    }}
    QLineEdit:focus, QComboBox:focus {{
        border: 1.5px solid {Colors.PRIMARY};
    }}
    QLineEdit[required_error="true"] {{
        border: 1.5px solid {Colors.NOT_OK_FG};
        background-color: {Colors.NOT_OK_BG};
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        border: none;
        background: {Colors.BG_CANVAS};
        width: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {Colors.BORDER_MEDIUM};
        border-radius: 4px;
    }}

    /* Refresh Link Button */
    QPushButton[class="refresh-btn"] {{
        background: transparent;
        color: {Colors.BLUE_LINK};
        font-weight: 700;
        font-size: 13px;
        border: none;
        padding: 4px 8px;
    }}
    QPushButton[class="refresh-btn"]:hover {{
        text-decoration: underline;
    }}
    """
