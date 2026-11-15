"""The three annotation colors and the contrasting halo that sits behind them."""

from __future__ import annotations

from PySide6.QtGui import QColor

PALETTE: tuple[tuple[str, str], ...] = (
    ("Black", "#000000"),
    ("White", "#ffffff"),
    ("Green", "#00a33a"),
)


def color_hex(color: QColor | str) -> str:
    return QColor(color).name(QColor.NameFormat.HexArgb)


def contrasting_color(color: QColor | str) -> QColor:
    """White against dark ink, near-black against light ink."""

    qcolor = QColor(color)
    luminance = (
        0.2126 * qcolor.redF() + 0.7152 * qcolor.greenF() + 0.0722 * qcolor.blueF()
    )
    if luminance > 0.62:
        return QColor("#111111")
    return QColor("#ffffff")
