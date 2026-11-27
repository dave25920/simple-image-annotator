"""The canvas. Wheel zoom never resamples the image."""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsItem, QGraphicsView, QLabel

from annotate.geometry import ellipse_box
from annotate.items import AnnotationTextItem, ArrowItem, DoubleArrowItem, EllipseItem, is_annotation

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def is_image_path(path: str) -> bool:
    import os

    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def image_path_from_mime(mime) -> str | None:
    if mime is None or not mime.hasUrls():
        return None
    for url in mime.urls():
        if url.isLocalFile() and is_image_path(url.toLocalFile()):
            return url.toLocalFile()
    return None


class AnnotationView(QGraphicsView):
    zoom_changed = Signal(float)
    place_text = Signal(QPointF)
    place_arrow = Signal(QPointF, QPointF)
    place_double_arrow = Signal(QPointF, QPointF)
    place_ellipse = Signal(QPointF, QPointF, bool)
    tool_requested = Signal(str)
    file_dropped = Signal(str)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._tool = "select"
        self._zoom = 1.0
        self._fit_pending = False
        self._drawing = False
        self._draw_start = QPointF()
        self._preview: ArrowItem | EllipseItem | None = None
        self._suppress_release = False
        self._panning = False
        self._pan_pos = QPoint()
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setBackgroundBrush(QColor("#d9d9d9"))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.viewport().installEventFilter(self)
        self.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._empty_hint = QLabel(
            "Drop an image here\nPNG, JPG, or BMP\n\nFile  →  Open",
            self.viewport(),
        )
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._empty_hint.setStyleSheet(
            "QLabel {"
            " background: rgba(255, 255, 255, 225);"
            " border: 1.5px dashed #b0b0b0;"
            " border-radius: 14px;"
            " color: #3a3a3a;"
            " padding: 24px;"
            "}"
        )
        scene.image_changed.connect(self._on_image_changed)
        self._position_empty_hint()

    def tool(self) -> str:
        return self._tool

    def set_tool(self, tool: str) -> None:
        if tool != self._tool:
            self.cancel_preview()
        self._tool = tool
        if tool == "select":
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        elif tool == "text":
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def zoom_factor(self) -> float:
        return self._zoom

    def zoom_by(self, factor: float, anchor: str = "mouse") -> None:
        if anchor == "center":
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        else:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        current = abs(self.transform().m11()) or 1.0
        target = max(0.05, min(16.0, current * factor))
        applied = target / current
        self.scale(applied, applied)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._remember_zoom()

    def actual_size(self) -> None:
        self.resetTransform()
        self._remember_zoom()

    def fit_image(self) -> None:
        scene = self.scene()
        if scene is None or not scene.has_image():
            return
        self.resetTransform()
        rect = scene.sceneRect()
        pad = max(rect.width(), rect.height()) * 0.03
        self.fitInView(rect.adjusted(-pad, -pad, pad, pad), Qt.AspectRatioMode.KeepAspectRatio)
        self._remember_zoom()

    def request_fit(self) -> None:
        if self.viewport().width() > 80 and self.viewport().height() > 80:
            self._fit_pending = False
            self.fit_image()
        else:
            self._fit_pending = True

    def cancel_preview(self) -> None:
        self._drawing = False
        preview = self._preview
        self._preview = None
        if preview is not None and preview.scene() is not None:
            preview.scene().removeItem(preview)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride and self._editing_text():
            # Let the text editor receive the key instead of a window shortcut.
            event.accept()
            return True
        return super().event(event)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.viewport() and event.type() in {
            QEvent.Type.DragEnter,
            QEvent.Type.DragMove,
            QEvent.Type.Drop,
        }:
            path = image_path_from_mime(event.mimeData())
            if path:
                event.acceptProposedAction()
                if event.type() == QEvent.Type.Drop:
                    self.file_dropped.emit(path)
                return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_pending:
            self._fit_pending = False
            self.fit_image()
        self._position_empty_hint()

    def _position_empty_hint(self) -> None:
        scene = self.scene()
        visible = scene is None or not scene.has_image()
        self._empty_hint.setVisible(visible)
        if not visible:
            return
        bounds = self.viewport().rect()
        width = min(420, max(220, bounds.width() - 96))
        height = 168
        self._empty_hint.setFixedSize(width, height)
        self._empty_hint.move(
            max(0, bounds.center().x() - width // 2),
            max(0, bounds.center().y() - height // 2),
        )

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y() or event.angleDelta().x()
            if delta == 0:
                event.ignore()
                return
            steps = 1 if delta > 0 else -1
            item = self._annotation_at(event.position().toPoint())
            if item is not None and item.isSelected():
                item.wheel_resize(steps)
                event.accept()
                return
            self.zoom_by(1.12 if steps > 0 else 1 / 1.12, anchor="mouse")
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_pos = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._tool == "text":
            pos = self._scene_pos(event)
            if self._over_image(pos):
                self.place_text.emit(pos)
                self._suppress_release = True
                event.accept()
                return
        if event.button() == Qt.MouseButton.LeftButton and self._tool in {"arrow", "double", "circle"}:
            pos = self._scene_pos(event)
            if self._over_image(pos):
                self._drawing = True
                self._draw_start = pos
                self._update_preview(pos, bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if getattr(self, "_panning", False):
            pos = event.position().toPoint()
            delta = pos - self._pan_pos
            self._pan_pos = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        if self._drawing:
            self._update_preview(
                self._scene_pos(event),
                bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier),
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and getattr(self, "_panning", False):
            self._panning = False
            self.set_tool(self._tool)
            event.accept()
            return
        if self._suppress_release and event.button() == Qt.MouseButton.LeftButton:
            self._suppress_release = False
            event.accept()
            return
        if self._drawing and event.button() == Qt.MouseButton.LeftButton:
            end = self._scene_pos(event)
            start = QPointF(self._draw_start)
            tool = self._tool
            constrain = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.cancel_preview()
            if self._over_image(start):
                if tool == "double":
                    self.place_double_arrow.emit(start, end)
                elif tool == "circle":
                    self.place_ellipse.emit(start, end, constrain)
                else:
                    self.place_arrow.emit(start, end)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if self._drawing and event.key() == Qt.Key.Key_Escape:
            self.cancel_preview()
            event.accept()
            return
        if self._editing_text():
            if event.key() == Qt.Key.Key_Escape and not event.modifiers():
                item = self.scene().focusItem()
                if isinstance(item, AnnotationTextItem):
                    item.cancel_edit()
                event.accept()
                return
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape:
            self.tool_requested.emit("select")
            scene = self.scene()
            if scene is not None:
                scene.clearSelection()
            event.accept()
            return
        if (
            event.key() == Qt.Key.Key_Backspace
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
            and self.scene() is not None
        ):
            self.scene().delete_selected()
            event.accept()
            return
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            nudge = {
                Qt.Key.Key_Left: (-step, 0),
                Qt.Key.Key_Right: (step, 0),
                Qt.Key.Key_Up: (0, -step),
                Qt.Key.Key_Down: (0, step),
            }.get(event.key())
            if nudge and self.scene() is not None and self.scene().nudge_selected(*nudge):
                event.accept()
                return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        from PySide6.QtWidgets import QMenu

        scene = self.scene()
        if scene is None or not scene.has_image():
            return
        pos = self.mapToScene(event.pos())
        target = None
        for item in scene.items(pos):
            if is_annotation(item):
                target = item
                break
        if target is None:
            return
        if not target.isSelected():
            scene.clearSelection()
            target.setSelected(True)
        menu = QMenu(self)
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(scene.delete_selected)
        menu.exec(event.globalPos())

    def _remember_zoom(self) -> None:
        self._zoom = abs(self.transform().m11()) or 1.0
        self.zoom_changed.emit(self._zoom)
        scene = self.scene()
        if scene is not None:
            scene.refresh_handles()

    def _on_image_changed(self) -> None:
        if self._preview is not None and self._preview.scene() is None:
            self._preview = None
            self._drawing = False
        self._position_empty_hint()

    def _editing_text(self) -> bool:
        scene = self.scene()
        if scene is None:
            return False
        item = scene.focusItem()
        return isinstance(item, AnnotationTextItem) and item.is_editing()

    def _scene_pos(self, event) -> QPointF:
        point = event.position().toPoint() if hasattr(event, "position") else event.pos()
        return self.mapToScene(point)

    def _over_image(self, scene_pos: QPointF) -> bool:
        scene = self.scene()
        return bool(scene is not None and scene.has_image() and scene.sceneRect().contains(scene_pos))

    def _annotation_at(self, view_pos):
        scene = self.scene()
        if scene is None:
            return None
        for item in scene.items(self.mapToScene(view_pos)):
            if is_annotation(item):
                return item
        return None

    def _update_preview(self, end: QPointF, constrain: bool = False) -> None:
        scene = self.scene()
        if scene is None:
            return
        if self._preview is None:
            self._preview = self._make_preview(scene)
            scene.addItem(self._preview)
        start = self._draw_start
        if self._tool == "circle" and isinstance(self._preview, EllipseItem):
            center_x, center_y, width, height = ellipse_box(
                start.x(),
                start.y(),
                end.x(),
                end.y(),
                constrain=constrain,
                default_width=scene.default_ellipse_width,
                default_height=scene.default_ellipse_height,
            )
            self._preview.set_size(width, height)
            self._preview.setRotation(0.0)
            self._preview.setPos(center_x, center_y)
        else:
            distance = math.hypot(end.x() - start.x(), end.y() - start.y())
            if distance < 10.0:
                self._preview.set_length(scene.default_arrow_length, anchor="center")
                self._preview.setRotation(-32.0)
                self._preview.setPos(start)
            else:
                self._preview.set_length(max(distance, 16.0), anchor="center")
                self._preview.setRotation(math.degrees(math.atan2(end.y() - start.y(), end.x() - start.x())))
                self._preview.setPos((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
        self._preview.update()

    def _make_preview(self, scene):
        if self._tool == "circle":
            item = EllipseItem(
                width=40,
                height=40,
                thickness=scene.default_arrow_thickness,
                color=scene.default_color,
                outline=scene.default_outline,
            )
        elif self._tool == "double":
            item = DoubleArrowItem(
                length=40,
                thickness=scene.default_arrow_thickness,
                color=scene.default_color,
                outline=scene.default_outline,
            )
        else:
            item = ArrowItem(
                length=40,
                thickness=scene.default_arrow_thickness,
                color=scene.default_color,
                outline=scene.default_outline,
            )
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        item.setZValue(scene.next_z())
        return item
