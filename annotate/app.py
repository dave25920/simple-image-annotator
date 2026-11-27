"""Application entry point."""

from __future__ import annotations

import os
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from annotate import APP_NAME, __version__
from annotate.main_window import MainWindow
from annotate.style import APP_STYLESHEET, app_font_family
from annotate.view import is_image_path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    app = QApplication(args)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    font = QFont(app_font_family())
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    if len(args) > 1 and os.path.isfile(args[1]) and is_image_path(args[1]):
        window.open_path(args[1], confirm=False)
    window.show()
    return app.exec()
