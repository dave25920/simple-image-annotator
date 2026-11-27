"""Graphics scene: the image in pixel coordinates, plus the annotations on it."""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QUndoStack
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene

from annotate.colors import color_hex
from annotate.commands import (
    AddCommand,
    DeleteCommand,
    MoveCommand,
    PropertyCommand,
    ResizeImageCommand,
    props_equal,
)
from annotate.geometry import ellipse_box
from annotate.items import (
    MIN_LENGTH,
    MIN_SPAN,
    AnnotationTextItem,
    ArrowItem,
    DoubleArrowItem,
    EllipseItem,
    is_annotation,
)
from annotate.style import app_font_family


class AnnotationScene(QGraphicsScene):
    image_changed = Signal()
    annotation_changed = Signal()
    interactive_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(30)
        self.exporting = False
        self._image = QImage()
        self._items: list = []
        self._z = 1
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._pixmap_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._pixmap_item.setZValue(0)
        self.addItem(self._pixmap_item)
        self.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        self.default_color = QColor("#000000")
        self.default_outline = True
        self.default_font_size = 32.0
        self.default_arrow_length = 170.0
        self.default_arrow_thickness = 18.0
        self.default_ellipse_width = 120.0
        self.default_ellipse_height = 120.0
        self.font_family = app_font_family()

    def has_image(self) -> bool:
        return not self._image.isNull()

    def image_size(self) -> tuple[int, int]:
        if self._image.isNull():
            return (0, 0)
        return (self._image.width(), self._image.height())

    def image(self) -> QImage:
        return self._image

    def annotation_items(self) -> list:
        return list(self._items)

    def selected_annotations(self) -> list:
        return [item for item in self.selectedItems() if is_annotation(item)]

    def next_z(self) -> float:
        self._z += 1
        return float(self._z)

    def raise_annotation(self, item) -> None:
        item.setZValue(self.next_z())

    def attach_annotation(self, item) -> None:
        if item.scene() is not self:
            self.addItem(item)
        if item not in self._items:
            self._items.append(item)
        if item.zValue() <= 0:
            item.setZValue(self.next_z())
        self.annotation_changed.emit()

    def detach_annotation(self, item) -> None:
        if item.scene() is self:
            self.removeItem(item)
        if item in self._items:
            self._items.remove(item)
        self.annotation_changed.emit()

    def load_image(self, path: str) -> bool:
        image = QImage(path)
        if image.isNull():
            return False
        self.replace_image(image)
        return True

    def replace_image(self, image: QImage) -> None:
        converted = image.convertToFormat(QImage.Format.Format_ARGB32)
        converted.setDevicePixelRatio(1.0)
        for item in list(self.items()):
            if item is self._pixmap_item:
                continue
            self.removeItem(item)
        self._items.clear()
        self.clearSelection()
        self.clearFocus()
        self.undo_stack.clear()
        self.install_image(converted)
        self.annotation_changed.emit()

    def install_image(self, image: QImage) -> None:
        self._image = image
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(1.0)
        self._pixmap_item.setPixmap(pixmap)
        width = max(1, image.width())
        height = max(1, image.height())
        self.setSceneRect(0, 0, width, height)
        self.image_changed.emit()

    def add_text(
        self,
        pos: QPointF,
        text: str = "Text",
        font_size: float | None = None,
        color=None,
        outline: bool | None = None,
    ) -> AnnotationTextItem:
        item = AnnotationTextItem(
            text=text,
            font_size=self.default_font_size if font_size is None else font_size,
            color=self.default_color if color is None else color,
            outline=self.default_outline if outline is None else outline,
            font_family=self.font_family,
        )
        item.setPos(pos)
        self.undo_stack.push(AddCommand(self, item, "Add text"))
        return item

    def add_arrow(
        self,
        center: QPointF,
        length: float | None = None,
        thickness: float | None = None,
        rotation: float = 0.0,
        color=None,
        outline: bool | None = None,
    ) -> ArrowItem:
        item = ArrowItem(
            length=self.default_arrow_length if length is None else length,
            thickness=self.default_arrow_thickness if thickness is None else thickness,
            color=self.default_color if color is None else color,
            outline=self.default_outline if outline is None else outline,
            rotation=rotation,
        )
        item.setPos(center)
        self.undo_stack.push(AddCommand(self, item, "Add arrow"))
        return item

    def add_double_arrow(
        self,
        center: QPointF,
        length: float | None = None,
        thickness: float | None = None,
        rotation: float = 0.0,
        color=None,
        outline: bool | None = None,
    ) -> DoubleArrowItem:
        item = DoubleArrowItem(
            length=self.default_arrow_length if length is None else length,
            thickness=self.default_arrow_thickness if thickness is None else thickness,
            color=self.default_color if color is None else color,
            outline=self.default_outline if outline is None else outline,
            rotation=rotation,
        )
        item.setPos(center)
        self.undo_stack.push(AddCommand(self, item, "Add double arrow"))
        return item

    def add_ellipse(
        self,
        center: QPointF,
        width: float | None = None,
        height: float | None = None,
        thickness: float | None = None,
        rotation: float = 0.0,
        color=None,
        outline: bool | None = None,
    ) -> EllipseItem:
        item = EllipseItem(
            width=self.default_ellipse_width if width is None else width,
            height=self.default_ellipse_height if height is None else height,
            thickness=self.default_arrow_thickness if thickness is None else thickness,
            color=self.default_color if color is None else color,
            outline=self.default_outline if outline is None else outline,
            rotation=rotation,
        )
        item.setPos(center)
        self.undo_stack.push(AddCommand(self, item, "Add oval"))
        return item

    def add_arrow_between(self, start: QPointF, end: QPointF) -> ArrowItem:
        distance = math.hypot(end.x() - start.x(), end.y() - start.y())
        if distance < 10.0:
            return self.add_arrow(start, rotation=-32.0)
        center = QPointF((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
        rotation = math.degrees(math.atan2(end.y() - start.y(), end.x() - start.x()))
        return self.add_arrow(center, length=max(distance, MIN_LENGTH), rotation=rotation)

    def add_double_arrow_between(self, start: QPointF, end: QPointF) -> DoubleArrowItem:
        distance = math.hypot(end.x() - start.x(), end.y() - start.y())
        if distance < 10.0:
            return self.add_double_arrow(start, rotation=-32.0)
        center = QPointF((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
        rotation = math.degrees(math.atan2(end.y() - start.y(), end.x() - start.x()))
        return self.add_double_arrow(center, length=max(distance, MIN_LENGTH), rotation=rotation)

    def add_ellipse_between(self, start: QPointF, end: QPointF, constrain: bool = False) -> EllipseItem:
        center_x, center_y, width, height = ellipse_box(
            start.x(),
            start.y(),
            end.x(),
            end.y(),
            constrain=constrain,
            min_size=MIN_SPAN,
            default_width=self.default_ellipse_width,
            default_height=self.default_ellipse_height,
        )
        return self.add_ellipse(QPointF(center_x, center_y), width=width, height=height)

    def delete_selected(self) -> None:
        for item in self.selected_annotations():
            if isinstance(item, AnnotationTextItem) and item.is_editing():
                item.cancel_edit()
        items = self.selected_annotations()
        if not items:
            return
        self.undo_stack.push(DeleteCommand(self, items))

    def finish_text_edits(self) -> None:
        for item in list(self._items):
            if isinstance(item, AnnotationTextItem):
                item.end_edit()

    def nudge_selected(self, dx: float, dy: float) -> bool:
        items = [
            item
            for item in self.selected_annotations()
            if item.flags() & QGraphicsItemFlagMovable()
        ]
        if not items:
            return False
        changes = []
        for item in items:
            old = item.pos()
            item.setPos(old.x() + dx, old.y() + dy)
            changes.append((item, old, item.pos()))
        self.undo_stack.push(MoveCommand(changes))
        return True

    def push_properties(self, changes: list, text: str, merge_key=None) -> None:
        meaningful = []
        for item, old, new in changes:
            if not props_equal(old, new):
                meaningful.append((item, old, new))
        if not meaningful:
            return
        stack = self.undo_stack
        if merge_key is not None and stack.count() > 0 and stack.index() == stack.count():
            current = stack.command(stack.index() - 1)
            if isinstance(current, PropertyCommand) and current.can_merge(merge_key, meaningful):
                current.absorb(meaningful)
                self.interactive_changed.emit()
                return
        stack.push(PropertyCommand(meaningful, text, merge_key))

    def apply_color(self, color) -> None:
        self.default_color = QColor(color)
        target = color_hex(self.default_color)
        changes = []
        for item in self.selected_annotations():
            old = item.properties()
            if old.get("color") == target:
                continue
            item.set_color(self.default_color)
            changes.append((item, old, item.properties()))
        self.push_properties(changes, "Color")

    def apply_outline(self, enabled: bool) -> None:
        self.default_outline = bool(enabled)
        changes = []
        for item in self.selected_annotations():
            old = item.properties()
            if bool(old.get("outline")) == self.default_outline:
                continue
            item.set_outline(self.default_outline)
            changes.append((item, old, item.properties()))
        self.push_properties(changes, "Outline")

    def apply_font_size(self, size: float) -> None:
        self.default_font_size = float(size)
        changes = []
        for item in self.selected_annotations():
            if not isinstance(item, AnnotationTextItem):
                continue
            old = item.properties()
            item.set_font_size(size)
            changes.append((item, old, item.properties()))
        self.push_properties(changes, "Text size", merge_key=("font-spin", self._ids(changes)))

    def apply_rotation(self, angle: float) -> None:
        changes = []
        for item in self.selected_annotations():
            if not isinstance(item, (ArrowItem, EllipseItem)):
                continue
            old = item.properties()
            item.set_angle(angle)
            changes.append((item, old, item.properties()))
        self.push_properties(changes, "Rotate", merge_key=("angle-spin", self._ids(changes)))

    def apply_length(self, length: float) -> None:
        arrows = [item for item in self.selected_annotations() if isinstance(item, ArrowItem)]
        ellipses = [item for item in self.selected_annotations() if isinstance(item, EllipseItem)]
        changes = []
        if arrows or not ellipses:
            self.default_arrow_length = float(length)
        if ellipses and not arrows:
            self.default_ellipse_width = float(length)
        for item in arrows:
            old = item.properties()
            item.set_length(length, anchor="center")
            changes.append((item, old, item.properties()))
        if not arrows:
            for item in ellipses:
                old = item.properties()
                item.set_width(length, anchor="center")
                changes.append((item, old, item.properties()))
        label = "Oval width" if ellipses and not arrows else "Arrow length"
        self.push_properties(changes, label, merge_key=("length-spin", self._ids(changes)))

    def apply_height(self, height: float) -> None:
        self.default_ellipse_height = float(height)
        changes = []
        for item in self.selected_annotations():
            if not isinstance(item, EllipseItem):
                continue
            old = item.properties()
            item.set_height(height, anchor="center")
            changes.append((item, old, item.properties()))
        self.push_properties(changes, "Oval height", merge_key=("height-spin", self._ids(changes)))

    def apply_thickness(self, thickness: float) -> None:
        self.default_arrow_thickness = float(thickness)
        changes = []
        for item in self.selected_annotations():
            if not isinstance(item, (ArrowItem, EllipseItem)):
                continue
            old = item.properties()
            item.set_thickness(thickness)
            changes.append((item, old, item.properties()))
        label = "Oval thickness" if any(isinstance(item, EllipseItem) for item, _old, _new in changes) and not any(
            isinstance(item, ArrowItem) for item, _old, _new in changes
        ) else "Arrow thickness"
        self.push_properties(changes, label, merge_key=("thick-spin", self._ids(changes)))

    def resize_image(self, width: int, height: int) -> bool:
        if self._image.isNull():
            return False
        width = int(max(1, min(20000, round(width))))
        height = int(max(1, min(20000, round(height))))
        if width == self._image.width() and height == self._image.height():
            return False
        self.finish_text_edits()
        before = self.snapshot_annotations()
        old_image = self._image.copy()
        sx = width / old_image.width()
        sy = height / old_image.height()
        for item in self._items:
            item.scale_with_image(sx, sy)
        after = self.snapshot_annotations()
        self.restore_snapshots(before)
        new_image = old_image.scaled(
            width,
            height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        new_image.setDevicePixelRatio(1.0)
        self.undo_stack.push(ResizeImageCommand(self, old_image, new_image, before, after))
        return True

    def snapshot_annotations(self) -> list:
        return [(item, item.properties()) for item in self._items]

    def restore_snapshots(self, snaps: list) -> None:
        for item, props in snaps:
            item.apply_properties(props)

    def refresh_handles(self) -> None:
        for item in self._items:
            item.prepareGeometryChange()
            item.update()

    def render_image(self) -> QImage:
        if self._image.isNull():
            return QImage()
        self.finish_text_edits()
        selected = list(self.selectedItems())
        focus = self.focusItem()
        self.exporting = True
        self.clearSelection()
        self.clearFocus()
        width = self._image.width()
        height = self._image.height()
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.setDevicePixelRatio(1.0)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            self.render(painter, QRectF(0, 0, width, height), QRectF(0, 0, width, height))
        finally:
            painter.end()
            self.exporting = False
            for item in selected:
                if item.scene() is self:
                    item.setSelected(True)
            if focus is not None and focus.scene() is self:
                focus.setFocus()
        return image

    def export_file(self, path: str, jpg_quality: int = 92) -> bool:
        rendered = self.render_image()
        if rendered.isNull():
            return False
        ext = os.path.splitext(path)[1].lower()
        if ext in {".jpg", ".jpeg"}:
            flat = QImage(rendered.size(), QImage.Format.Format_RGB32)
            flat.setDevicePixelRatio(1.0)
            flat.fill(Qt.GlobalColor.white)
            painter = QPainter(flat)
            painter.drawImage(0, 0, rendered)
            painter.end()
            quality = int(max(1, min(100, jpg_quality)))
            return flat.save(path, "JPEG", quality)
        return rendered.save(path, "PNG")

    @staticmethod
    def _ids(changes: list):
        return tuple(id(item) for item, _old, _new in changes)


def QGraphicsItemFlagMovable():
    from PySide6.QtWidgets import QGraphicsItem

    return QGraphicsItem.GraphicsItemFlag.ItemIsMovable
