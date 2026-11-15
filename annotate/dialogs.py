"""Resize and JPEG quality dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from annotate.geometry import linked_dimensions

PIXEL_CAP = 16000


class ResizeImageDialog(QDialog):
    """Edit width and height in pixels or as a percent of the current image."""

    def __init__(self, width: int, height: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resize image")
        self._orig_w = max(1, int(width))
        self._orig_h = max(1, int(height))
        self._block = False
        self._px_cap = max(PIXEL_CAP, self._orig_w, self._orig_h)

        self.width_px = QSpinBox()
        self.height_px = QSpinBox()
        self.width_pct = QDoubleSpinBox()
        self.height_pct = QDoubleSpinBox()
        for box in (self.width_px, self.height_px):
            box.setRange(1, self._px_cap)
            box.setSuffix(" px")
            box.setKeyboardTracking(False)
            box.setAccelerated(True)
        for box in (self.width_pct, self.height_pct):
            box.setRange(1.0, 800.0)
            box.setDecimals(1)
            box.setSuffix(" %")
            box.setSingleStep(1.0)
            box.setKeyboardTracking(False)

        self.keep = QCheckBox("Keep aspect ratio")
        self.keep.setChecked(True)

        self._block = True
        self.width_px.setValue(self._orig_w)
        self.height_px.setValue(self._orig_h)
        self.width_pct.setValue(100.0)
        self.height_pct.setValue(100.0)
        self._block = False

        self.width_px.valueChanged.connect(self._on_width_px)
        self.height_px.valueChanged.connect(self._on_height_px)
        self.width_pct.valueChanged.connect(self._on_width_pct)
        self.height_pct.valueChanged.connect(self._on_height_pct)
        self.keep.toggled.connect(self._on_keep_toggled)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self._width_row = self._pair(self.width_px, self.width_pct)
        self._height_row = self._pair(self.height_px, self.height_pct)
        form.addRow("Width", self._width_row)
        form.addRow("Height", self._height_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Resize")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        current = QLabel(f"Current size: {self._orig_w} × {self._orig_h} px")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)
        layout.addWidget(current)
        layout.addLayout(form)
        layout.addWidget(self.keep)
        layout.addWidget(buttons)
        self.setMinimumWidth(420)

    def result_size(self) -> tuple[int, int]:
        return self.width_px.value(), self.height_px.value()

    def _pair(self, pixels: QSpinBox, percent: QDoubleSpinBox) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(pixels)
        row.addWidget(percent)
        return row

    def _on_width_px(self, value: int) -> None:
        self._apply("width_px", value)

    def _on_height_px(self, value: int) -> None:
        self._apply("height_px", value)

    def _on_width_pct(self, value: float) -> None:
        self._apply("width_pct", value)

    def _on_height_pct(self, value: float) -> None:
        self._apply("height_pct", value)

    def _on_keep_toggled(self, checked: bool) -> None:
        if checked:
            self._apply("width_px", self.width_px.value())

    def _apply(self, changed: str, value: float) -> None:
        if self._block:
            return
        width, height = linked_dimensions(
            self._orig_w,
            self._orig_h,
            changed,
            value,
            self.keep.isChecked(),
            current_w=self.width_px.value(),
            current_h=self.height_px.value(),
        )
        self._set_all(width, height)

    def _set_all(self, width: int, height: int) -> None:
        width = min(self._px_cap, max(1, int(width)))
        height = min(self._px_cap, max(1, int(height)))
        self._block = True
        self.width_px.setValue(width)
        self.height_px.setValue(height)
        self.width_pct.setValue(width / self._orig_w * 100.0)
        self.height_pct.setValue(height / self._orig_h * 100.0)
        self._block = False


class JpegQualityDialog(QDialog):
    def __init__(self, parent=None, quality: int = 92):
        super().__init__(parent)
        self.setWindowTitle("JPEG quality")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(40, 100)
        self.slider.setValue(int(quality))
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(10)
        self.readout = QLabel()
        self.slider.valueChanged.connect(self._update_readout)
        self._update_readout(self.slider.value())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Higher quality keeps more detail and writes a larger file."))
        layout.addWidget(self.slider)
        layout.addWidget(self.readout)
        layout.addWidget(buttons)
        self.setMinimumWidth(380)

    def quality(self) -> int:
        return int(self.slider.value())

    def _update_readout(self, value: int) -> None:
        self.readout.setText(f"Quality: {value}")
