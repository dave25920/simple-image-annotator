"""Main window: menus, toolbars, and the annotation canvas."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from shiboken6 import isValid
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QToolBar,
    QToolButton,
    QWidget,
)

from annotate import APP_NAME
from annotate.colors import PALETTE
from annotate.dialogs import JpegQualityDialog, ResizeImageDialog
from annotate.geometry import normalize_angle
from annotate.items import ArrowItem, AnnotationTextItem, build_arrow_path
from annotate.scene import AnnotationScene
from annotate.view import AnnotationView, is_image_path

OPEN_FILTER = (
    "Images (*.png *.jpg *.jpeg *.bmp *.webp);;"
    "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;All files (*.*)"
)
SAVE_FILTER = "PNG (*.png);;JPEG (*.jpg *.jpeg)"


class ColorSwatch(QToolButton):
    def __init__(self, color: QColor, name: str, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setCheckable(True)
        self.setFixedSize(QSize(32, 32))
        self.setToolTip(name)
        self.setAccessibleName(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.isChecked():
            painter.setBrush(QColor("#d6e9f8"))
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)
        elif self.underMouse():
            painter.setBrush(QColor("#f1f1f1"))
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)
        painter.setPen(QPen(QColor("#8d8d8d"), 1))
        painter.setBrush(self.color)
        painter.drawEllipse(7, 7, 18, 18)
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(_app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(880, 560)
        self._source_path = ""
        self._last_dir = ""
        self._tool = "select"
        self._syncing = False

        self.scene = AnnotationScene(self)
        self.view = AnnotationView(self.scene, self)
        self.setCentralWidget(self.view)
        self.setAcceptDrops(True)

        self._build_actions()
        self._build_toolbars()
        self._build_menus()
        self._build_status()
        self._connect()
        self.set_tool("select")
        self._sync_controls()
        self._refresh_actions()
        self._refresh_status()

    def open_path(self, path: str, confirm: bool = True) -> bool:
        if not path:
            return False
        if confirm and self.scene.annotation_items():
            answer = QMessageBox.question(
                self,
                "Open image",
                "Opening a new image clears the current annotations. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self.view.cancel_preview()
        if not self.scene.load_image(path):
            QMessageBox.warning(self, "Open image", "Could not read that file as an image.")
            return False
        self._source_path = path
        self._last_dir = os.path.dirname(path)
        self.setWindowTitle(f"{APP_NAME} — {os.path.basename(path)}")
        self.view.request_fit()
        self._refresh_status()
        self._refresh_actions()
        self._sync_controls()
        self.view.setFocus()
        return True

    def set_tool(self, tool: str) -> None:
        self._tool = tool
        self.view.set_tool(tool)
        action = {"select": self.select_action, "text": self.text_action, "arrow": self.arrow_action}[tool]
        if not action.isChecked():
            action.setChecked(True)
        self._refresh_hint()
        if not self._text_is_editing():
            self.view.setFocus()

    def closeEvent(self, event) -> None:
        if isValid(self.scene):
            self.scene.blockSignals(True)
            self.scene.undo_stack.blockSignals(True)
        super().closeEvent(event)

    def dragEnterEvent(self, event) -> None:
        if _dropped_path(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if _dropped_path(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        path = _dropped_path(event)
        if path:
            self.open_path(path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _build_actions(self) -> None:
        self.open_action = QAction("Open…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.setToolTip("Open a PNG, JPG, or BMP (Ctrl+O)")
        self.open_action.triggered.connect(self._open_dialog)

        self.resize_action = QAction("Resize image…", self)
        self.resize_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.resize_action.setToolTip("Scale the image pixels (Ctrl+Shift+R)")
        self.resize_action.triggered.connect(self._resize_dialog)

        self.export_action = QAction("Export…", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.setToolTip("Save a flattened PNG or JPG (Ctrl+E)")
        self.export_action.triggered.connect(self._export_dialog)

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.exit_action.triggered.connect(self.close)

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.scene.undo_stack.undo)
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcuts(
            [QKeySequence.StandardKey.Redo, QKeySequence("Ctrl+Y")]
        )
        self.redo_action.triggered.connect(self.scene.undo_stack.redo)

        self.delete_action = QAction("Delete", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.delete_action.triggered.connect(self.scene.delete_selected)
        self.view.addAction(self.delete_action)

        self.zoom_in_action = QAction("Zoom in", self)
        self.zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.zoom_in_action.triggered.connect(lambda: self.view.zoom_by(1.2, anchor="center"))

        self.zoom_out_action = QAction("Zoom out", self)
        self.zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.zoom_out_action.triggered.connect(lambda: self.view.zoom_by(1 / 1.2, anchor="center"))

        self.fit_action = QAction("Fit", self)
        self.fit_action.setShortcut(QKeySequence("Ctrl+0"))
        self.fit_action.setToolTip("Fit the image in the window (Ctrl+0)")
        self.fit_action.triggered.connect(self.view.fit_image)

        self.actual_action = QAction("100%", self)
        self.actual_action.setShortcut(QKeySequence("Ctrl+1"))
        self.actual_action.setToolTip("Show the image at its actual pixel size (Ctrl+1)")
        self.actual_action.triggered.connect(self.view.actual_size)

        self.select_action = QAction("Select", self)
        self.select_action.setCheckable(True)
        self.select_action.setShortcut(QKeySequence("V"))
        self.select_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.select_action.setToolTip("Move and resize annotations (V)")
        self.select_action.triggered.connect(lambda: self.set_tool("select"))

        self.text_action = QAction("Text", self)
        self.text_action.setCheckable(True)
        self.text_action.setShortcut(QKeySequence("T"))
        self.text_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.text_action.setToolTip("Click the image to place text (T)")
        self.text_action.triggered.connect(lambda: self.set_tool("text"))

        self.arrow_action = QAction("Arrow", self)
        self.arrow_action.setCheckable(True)
        self.arrow_action.setShortcut(QKeySequence("A"))
        self.arrow_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.arrow_action.setToolTip("Click to drop an arrow, or drag to aim it (A)")
        self.arrow_action.triggered.connect(lambda: self.set_tool("arrow"))

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        for action in (self.select_action, self.text_action, self.arrow_action):
            self.tool_group.addAction(action)
            self.view.addAction(action)
        self.select_action.setChecked(True)

        self.outline_action = QAction("Outline", self)
        self.outline_action.setCheckable(True)
        self.outline_action.setChecked(self.scene.default_outline)
        self.outline_action.setToolTip("Thin contrasting outline so marks stay readable")
        self.outline_action.toggled.connect(self._on_outline)

        self.about_action = QAction(f"About {APP_NAME}", self)
        self.about_action.triggered.connect(self._about)

    def _build_toolbars(self) -> None:
        file_bar = QToolBar("File", self)
        file_bar.setObjectName("fileBar")
        file_bar.setMovable(False)
        file_bar.setFloatable(False)
        for action in (
            self.open_action,
            self.resize_action,
            self.export_action,
            self.undo_action,
            self.redo_action,
        ):
            file_bar.addAction(action)
        file_bar.addSeparator()
        file_bar.addAction(self.zoom_out_action)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        file_bar.addWidget(self.zoom_label)
        file_bar.addAction(self.zoom_in_action)
        file_bar.addAction(self.fit_action)
        file_bar.addAction(self.actual_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, file_bar)

        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)

        prop = QToolBar("Properties", self)
        prop.setObjectName("propertyBar")
        prop.setMovable(False)
        prop.setFloatable(False)
        prop.addAction(self.select_action)
        prop.addAction(self.text_action)
        prop.addAction(self.arrow_action)
        prop.addSeparator()

        self._swatches: list[ColorSwatch] = []
        self._swatch_group = QButtonGroup(self)
        self._swatch_group.setExclusive(True)
        for name, hex_color in PALETTE:
            button = ColorSwatch(QColor(hex_color), name)
            button.clicked.connect(lambda _checked=False, color=hex_color: self._on_color(color))
            self._swatches.append(button)
            self._swatch_group.addButton(button)
            prop.addWidget(button)
        prop.addSeparator()
        prop.addAction(self.outline_action)
        prop.addSeparator()

        self.font_spin = self._spin(8, 400, " pt", "Font size of the selected text, or the default for new text")
        self.angle_spin = self._spin(-180, 180, "°", "Rotation of the selected arrow. Shift-drag the round handle to snap to 15°.")
        self.angle_spin.setWrapping(True)
        self.length_spin = self._spin(16, 4000, " px", "Arrow length in pixels")
        self.length_spin.setSingleStep(5)
        self.thickness_spin = self._spin(2, 240, " px", "Arrow shaft thickness in pixels")
        prop.addWidget(self._labeled("Font", self.font_spin))
        prop.addWidget(self._labeled("Angle", self.angle_spin))
        prop.addWidget(self._labeled("Length", self.length_spin))
        prop.addWidget(self._labeled("Thick", self.thickness_spin))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, prop)

        self.font_spin.valueChanged.connect(self._on_font)
        self.angle_spin.valueChanged.connect(self._on_angle)
        self.length_spin.valueChanged.connect(self._on_length)
        self.thickness_spin.valueChanged.connect(self._on_thickness)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.resize_action)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.delete_action)

        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.fit_action)
        view_menu.addAction(self.actual_action)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction(self.select_action)
        tools_menu.addAction(self.text_action)
        tools_menu.addAction(self.arrow_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.outline_action)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.about_action)

    def _build_status(self) -> None:
        self._hint = QLabel("Open an image to start annotating.")
        self._size_label = QLabel("No image")
        self.statusBar().addWidget(self._hint, 1)
        self.statusBar().addPermanentWidget(self._size_label)

    def _connect(self) -> None:
        self.view.place_text.connect(self._place_text)
        self.view.place_arrow.connect(self._place_arrow)
        self.view.tool_requested.connect(self.set_tool)
        self.view.file_dropped.connect(self.open_path)
        self.view.zoom_changed.connect(lambda _zoom: self._refresh_status())
        self.scene.image_changed.connect(self._refresh_status)
        self.scene.image_changed.connect(self._refresh_actions)
        self.scene.annotation_changed.connect(self._sync_controls)
        self.scene.annotation_changed.connect(self._refresh_status)
        self.scene.interactive_changed.connect(self._sync_controls)
        self.scene.selectionChanged.connect(self._sync_controls)
        self.scene.undo_stack.indexChanged.connect(lambda _index: self._sync_controls())
        self.scene.undo_stack.indexChanged.connect(lambda _index: self._refresh_actions())

    def _place_text(self, pos) -> None:
        item = self.scene.add_text(pos)
        self.scene.clearSelection()
        item.setSelected(True)
        self.set_tool("select")
        item.begin_edit()

    def _place_arrow(self, start, end) -> None:
        item = self.scene.add_arrow_between(start, end)
        self.scene.clearSelection()
        item.setSelected(True)
        self.set_tool("select")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"{APP_NAME}\n\n"
            "Point at things in a picture with arrows and short notes, "
            "then export a flattened PNG or JPEG.",
        )

    def _open_dialog(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(self, "Open image", self._last_dir, OPEN_FILTER)
        if path:
            self.open_path(path)

    def _resize_dialog(self) -> None:
        if not self.scene.has_image():
            QMessageBox.information(self, "Resize image", "Open an image first.")
            return
        width, height = self.scene.image_size()
        dialog = ResizeImageDialog(width, height, self)
        if dialog.exec() != QDialogCodeAccepted():
            return
        new_w, new_h = dialog.result_size()
        self.scene.resize_image(new_w, new_h)
        self._refresh_status()

    def _export_dialog(self) -> None:
        if not self.scene.has_image():
            QMessageBox.information(self, "Export", "Open an image first.")
            return
        self.scene.finish_text_edits()
        stem = "annotated"
        if self._source_path:
            stem = os.path.splitext(os.path.basename(self._source_path))[0] + "-annotated"
        suggested = os.path.join(self._last_dir, stem + ".png")
        path, selected = QFileDialog.getSaveFileName(self, "Export image", suggested, SAVE_FILTER)
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in {".png", ".jpg", ".jpeg"}:
            path += ".jpg" if "JPEG" in selected else ".png"
            ext = os.path.splitext(path)[1].lower()
        quality = 92
        if ext in {".jpg", ".jpeg"}:
            dialog = JpegQualityDialog(self, quality)
            if dialog.exec() != QDialogCodeAccepted():
                return
            quality = dialog.quality()
        if not self.scene.export_file(path, quality):
            QMessageBox.warning(self, "Export", "Could not write that file.")
            return
        self._last_dir = os.path.dirname(path)
        self.statusBar().showMessage(f"Exported {os.path.basename(path)}", 4000)

    def _on_color(self, hex_color: str) -> None:
        if self._syncing:
            return
        self.scene.apply_color(hex_color)
        self._check_color(QColor(hex_color))

    def _on_outline(self, checked: bool) -> None:
        if self._syncing:
            return
        self.scene.apply_outline(checked)

    def _on_font(self, value: int) -> None:
        if self._syncing:
            return
        self.scene.apply_font_size(value)

    def _on_angle(self, value: int) -> None:
        if self._syncing or not self.angle_spin.isEnabled():
            return
        self.scene.apply_rotation(value)

    def _on_length(self, value: int) -> None:
        if self._syncing or not self.length_spin.isEnabled():
            return
        self.scene.apply_length(value)

    def _on_thickness(self, value: int) -> None:
        if self._syncing or not self.thickness_spin.isEnabled():
            return
        self.scene.apply_thickness(value)

    def _sync_controls(self) -> None:
        if not isValid(self.scene):
            return
        self._syncing = True
        texts = [item for item in self.scene.selected_annotations() if isinstance(item, AnnotationTextItem)]
        arrows = [item for item in self.scene.selected_annotations() if isinstance(item, ArrowItem)]
        if texts:
            self.font_spin.setValue(int(round(texts[0].font_size())))
        else:
            self.font_spin.setValue(int(round(self.scene.default_font_size)))
        self.angle_spin.setEnabled(bool(arrows))
        self.length_spin.setEnabled(bool(arrows))
        self.thickness_spin.setEnabled(bool(arrows))
        if arrows:
            self.angle_spin.setValue(int(round(normalize_angle(arrows[0].rotation()))))
            self.length_spin.setValue(int(round(arrows[0].length())))
            self.thickness_spin.setValue(int(round(arrows[0].thickness())))
        else:
            self.angle_spin.setValue(0)
            self.length_spin.setValue(int(round(self.scene.default_arrow_length)))
            self.thickness_spin.setValue(int(round(self.scene.default_arrow_thickness)))
        selected = self.scene.selected_annotations()
        if selected:
            self._check_color(selected[0].color())
            self.outline_action.setChecked(selected[0].outline_enabled())
        else:
            self._check_color(self.scene.default_color)
            self.outline_action.setChecked(self.scene.default_outline)
        self._syncing = False
        self._refresh_hint()

    def _check_color(self, color: QColor) -> None:
        target = QColor(color).name().lower()
        for button in self._swatches:
            button.setChecked(button.color.name().lower() == target)

    def _refresh_actions(self) -> None:
        if not isValid(self.scene):
            return
        has_image = self.scene.has_image()
        self.resize_action.setEnabled(has_image)
        self.export_action.setEnabled(has_image)
        self.fit_action.setEnabled(has_image)
        self.actual_action.setEnabled(has_image)
        stack = self.scene.undo_stack
        self.undo_action.setEnabled(stack.canUndo())
        self.redo_action.setEnabled(stack.canRedo())
        self.undo_action.setToolTip(
            f"Undo {stack.undoText()} (Ctrl+Z)" if stack.canUndo() else "Undo (Ctrl+Z)"
        )
        self.redo_action.setToolTip(
            f"Redo {stack.redoText()} (Ctrl+Y)" if stack.canRedo() else "Redo (Ctrl+Y)"
        )

    def _refresh_status(self) -> None:
        if not isValid(self.scene):
            return
        if self.scene.has_image():
            width, height = self.scene.image_size()
            self._size_label.setText(f"{width} × {height} px")
        else:
            self._size_label.setText("No image")
        self.zoom_label.setText(f"{self.view.zoom_factor() * 100:.0f}%")
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        if not isValid(self.scene):
            return
        if not self.scene.has_image():
            self._hint.setText("Open an image, or drop a PNG, JPG, or BMP onto the window.")
            return
        hints = {
            "select": "Drag to move. Double-click text to edit. Delete removes the selection.",
            "text": "Click the image to place text.",
            "arrow": "Click to drop an arrow, or drag to aim it. Shift snaps rotation to 15°.",
        }
        count = len(self.scene.annotation_items())
        suffix = f"  ·  {count} annotation" + ("" if count == 1 else "s")
        self._hint.setText(hints.get(self._tool, "") + suffix)

    def _text_is_editing(self) -> bool:
        item = self.scene.focusItem()
        return isinstance(item, AnnotationTextItem) and item.is_editing()

    @staticmethod
    def _spin(low: int, high: int, suffix: str, tip: str) -> QSpinBox:
        box = QSpinBox()
        box.setRange(low, high)
        box.setSuffix(suffix)
        box.setKeyboardTracking(False)
        box.setToolTip(tip)
        box.setFixedWidth(88)
        return box

    @staticmethod
    def _labeled(text: str, widget: QWidget) -> QWidget:
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(6, 0, 2, 0)
        layout.setSpacing(4)
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        layout.addWidget(label)
        layout.addWidget(widget)
        return wrap


def _dropped_path(event) -> str:
    mime = event.mimeData()
    if mime is None or not mime.hasUrls():
        return ""
    for url in mime.urls():
        if url.isLocalFile() and is_image_path(url.toLocalFile()):
            return url.toLocalFile()
    return ""


def _app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#d5d5d5"), 2))
    painter.setBrush(QColor("#f7f7f7"))
    painter.drawRoundedRect(3, 3, 58, 58, 12, 12)
    painter.translate(32, 34)
    painter.rotate(-32)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#00a33a"))
    painter.drawPath(build_arrow_path(36, 8))
    painter.end()
    return QIcon(pixmap)


def QDialogCodeAccepted() -> int:
    from PySide6.QtWidgets import QDialog

    return int(QDialog.DialogCode.Accepted)
