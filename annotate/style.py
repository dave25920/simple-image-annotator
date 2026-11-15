"""Shared font choice and the application stylesheet."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

APP_STYLESHEET = """
QMainWindow, QDialog {
    background: #f3f3f3;
    color: #1c1c1c;
    font-size: 13px;
}
QMenuBar {
    background: #ffffff;
    border-bottom: 1px solid #e6e6e6;
    padding: 2px 4px;
}
QMenuBar::item {
    padding: 4px 10px;
    background: transparent;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background: #e8f1fb;
}
QMenu {
    background: #ffffff;
    border: 1px solid #e0e0e0;
    padding: 4px;
}
QMenu::item {
    padding: 6px 28px 6px 16px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: #e8f1fb;
}
QToolBar {
    background: #ffffff;
    border: none;
    border-bottom: 1px solid #e8e8e8;
    spacing: 2px;
    padding: 4px 8px;
}
QToolBar::separator {
    background: #e4e4e4;
    width: 1px;
    margin: 6px 8px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 10px;
    color: #1c1c1c;
}
QToolButton:hover {
    background: #f2f2f2;
}
QToolButton:checked {
    background: #e5f1fb;
    border-color: #8bb8e8;
    color: #0b4f8a;
}
QToolButton:pressed {
    background: #d7e8f8;
}
QStatusBar {
    background: #fafafa;
    border-top: 1px solid #e6e6e6;
    color: #444444;
}
QSpinBox, QDoubleSpinBox, QSlider {
    background: #ffffff;
}
QSpinBox, QDoubleSpinBox {
    border: 1px solid #d0d0d0;
    border-radius: 5px;
    padding: 2px 6px;
    min-height: 22px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #0067c0;
}
QLabel#fieldLabel {
    color: #333333;
}
"""

_family: str | None = None


def app_font_family() -> str:
    """Prefer Segoe UI on Windows and a metric-compatible face elsewhere."""

    global _family
    if _family:
        return _family
    families = set(QFontDatabase.families())
    for name in ("Segoe UI", "DejaVu Sans", "Noto Sans", "Liberation Sans", "Arial"):
        if name in families:
            _family = name
            return _family
    _family = QFont().family() or "Sans Serif"
    return _family
