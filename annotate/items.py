"""Movable text, arrow, and oval annotations.

Coordinates are image pixels. The view's zoom transform is separate, so a
handle that should stay about 7 screen pixels wide divides by the view scale.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsTextItem,
    QStyle,
    QStyleOptionGraphicsItem,
)

from annotate.colors import color_hex, contrasting_color
from annotate.commands import props_equal
from annotate.dragging import finish_move, select_on_press, start_move, update_move
from annotate.geometry import arrow_metrics, snap_angle

MIN_FONT = 8.0
MAX_FONT = 400.0
MIN_LENGTH = 16.0
MAX_LENGTH = 8000.0
MIN_SPAN = 16.0
MAX_SPAN = 8000.0
MIN_THICKNESS = 2.0
MAX_THICKNESS = 240.0


def view_scale_of(item) -> float:
    scene = item.scene()
    if scene is None or not scene.views():
        return 1.0
    return max(abs(scene.views()[0].transform().m11()), 0.05)


def build_arrow_path(length: float, thickness: float) -> QPainterPath:
    metrics = arrow_metrics(length, thickness)
    length = metrics["length"]
    half_shaft = metrics["thickness"] / 2.0
    head_len = metrics["head_len"]
    half_head = metrics["head_w"] / 2.0
    tail = -length / 2.0
    base = tail + (length - head_len)
    tip = length / 2.0
    path = QPainterPath()
    path.moveTo(tail, -half_shaft)
    path.lineTo(base, -half_shaft)
    path.lineTo(base, -half_head)
    path.lineTo(tip, 0.0)
    path.lineTo(base, half_head)
    path.lineTo(base, half_shaft)
    path.lineTo(tail, half_shaft)
    path.closeSubpath()
    return path


def build_double_arrow_path(length: float, thickness: float) -> QPainterPath:
    """Arrow with a head at each end. Both heads stay inside the length."""

    metrics = arrow_metrics(length, thickness, heads=2)
    length = metrics["length"]
    half_shaft = metrics["thickness"] / 2.0
    head_len = min(metrics["head_len"], length * 0.45)
    half_head = metrics["head_w"] / 2.0
    left_tip = -length / 2.0
    right_tip = length / 2.0
    left_base = left_tip + head_len
    right_base = right_tip - head_len
    path = QPainterPath()
    path.moveTo(left_tip, 0.0)
    path.lineTo(left_base, -half_head)
    path.lineTo(left_base, -half_shaft)
    path.lineTo(right_base, -half_shaft)
    path.lineTo(right_base, -half_head)
    path.lineTo(right_tip, 0.0)
    path.lineTo(right_base, half_head)
    path.lineTo(right_base, half_shaft)
    path.lineTo(left_base, half_shaft)
    path.lineTo(left_base, half_head)
    path.closeSubpath()
    return path


def _show_chrome(item) -> bool:
    if not item.isSelected():
        return False
    scene = item.scene()
    if scene is not None and getattr(scene, "exporting", False):
        return False
    return True


def _emit_live(item) -> None:
    scene = item.scene()
    if scene is not None and hasattr(scene, "interactive_changed"):
        scene.interactive_changed.emit()


def _commit_properties(item, old, text: str) -> None:
    new = item.properties()
    if props_equal(old, new):
        return
    scene = item.scene()
    if scene is not None:
        scene.push_properties([(item, old, new)], text)


class AnnotationTextItem(QGraphicsTextItem):
    def __init__(
        self,
        text: str = "Text",
        font_size: float = 32,
        color: QColor | str = "#000000",
        outline: bool = True,
        font_family: str = "Sans Serif",
    ):
        super().__init__()
        self._font_size = float(font_size)
        self._color = QColor(color)
        self._outline = bool(outline)
        self._font_family = font_family
        self._editing = False
        self._text_before = text
        self._drag = None
        self._start_props = None
        self._start_font = self._font_size
        self._press_scene = QPointF()
        self._move_origins = {}
        self.document().setDocumentMargin(6)
        self.setPlainText(text)
        self._apply_style()
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.document().setUndoRedoEnabled(False)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def is_editing(self) -> bool:
        return self._editing

    def font_size(self) -> float:
        return self._font_size

    def color(self) -> QColor:
        return QColor(self._color)

    def outline_enabled(self) -> bool:
        return self._outline

    def properties(self) -> dict:
        return {
            "pos": (float(self.pos().x()), float(self.pos().y())),
            "text": self.toPlainText(),
            "font_size": float(self._font_size),
            "color": color_hex(self._color),
            "outline": bool(self._outline),
        }

    def apply_properties(self, props: dict) -> None:
        if "text" in props and props["text"] != self.toPlainText():
            self.setPlainText(props["text"])
        if "font_size" in props:
            self._font_size = float(props["font_size"])
        if "color" in props:
            self._color = QColor(props["color"])
        if "outline" in props:
            self._outline = bool(props["outline"])
        self._apply_style()
        if "pos" in props:
            x, y = props["pos"]
            self.setPos(float(x), float(y))
        self.update()

    def set_color(self, color: QColor | str) -> None:
        self._color = QColor(color)
        self._apply_style()

    def set_outline(self, enabled: bool) -> None:
        self._outline = bool(enabled)
        self._apply_style()

    def set_font_size(self, size: float) -> None:
        size = float(max(MIN_FONT, min(MAX_FONT, size)))
        if abs(size - self._font_size) < 0.04:
            return
        self.prepareGeometryChange()
        self._font_size = size
        self._apply_style()

    def scale_with_image(self, sx: float, sy: float) -> None:
        props = self.properties()
        x, y = props["pos"]
        props["pos"] = (x * sx, y * sy)
        props["font_size"] = max(MIN_FONT, min(MAX_FONT, self._font_size * ((sx + sy) / 2.0)))
        self.apply_properties(props)

    def wheel_resize(self, steps: int) -> None:
        old = self.properties()
        self.set_font_size(self._font_size + steps * 2)
        scene = self.scene()
        if scene is not None:
            scene.push_properties([(self, old, self.properties())], "Text size", merge_key=("font", id(self)))

    def begin_edit(self) -> None:
        if self._editing:
            return
        self._editing = True
        self._drag = None
        self._text_before = self.toPlainText()
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.document().setUndoRedoEnabled(True)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.setTextCursor(cursor)
        self.update()

    def end_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.document().setUndoRedoEnabled(False)
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        text = self.toPlainText()
        if not text.strip():
            self.setPlainText(self._text_before or "Text")
            self._apply_style()
            text = self.toPlainText()
        if text != self._text_before:
            new = self.properties()
            old = dict(new)
            old["text"] = self._text_before
            scene = self.scene()
            if scene is not None:
                scene.push_properties([(self, old, new)], "Edit text")
        self.update()

    def cancel_edit(self) -> None:
        if not self._editing:
            return
        self.setPlainText(self._text_before or "Text")
        self._apply_style()
        self._editing = False
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.document().setUndoRedoEnabled(False)
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self.clearFocus()
        self.update()

    def boundingRect(self) -> QRectF:
        rect = QGraphicsTextItem.boundingRect(self)
        if self._show_chrome():
            radius = self._handle_radius()
            rect = rect.adjusted(-2, -2, radius * 2.4, radius * 2.4)
        return rect

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        opt = QStyleOptionGraphicsItem(option)
        opt.state = opt.state & ~QStyle.StateFlag.State_Selected
        QGraphicsTextItem.paint(self, painter, opt, widget)
        if self._show_chrome():
            self._paint_chrome(painter)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.prepareGeometryChange()
            if bool(value):
                scene = self.scene()
                if scene is not None and hasattr(scene, "raise_annotation"):
                    scene.raise_annotation(self)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._hit_resize_handle(event.pos()):
            self.begin_edit()
            super().mouseDoubleClickEvent(event)
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            self.setTextCursor(cursor)
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._editing:
            QGraphicsTextItem.mousePressEvent(self, event)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        if self.isSelected() and self._hit_resize_handle(event.pos()):
            self._drag = "resize"
            self._press_scene = QPointF(event.scenePos())
            self._start_props = self.properties()
            self._start_font = self._font_size
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        if not select_on_press(self, event):
            event.accept()
            return
        self._drag = "move"
        start_move(self, event)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._editing:
            QGraphicsTextItem.mouseMoveEvent(self, event)
            return
        if self._drag == "resize":
            self._apply_font_drag(event.scenePos())
            _emit_live(self)
            event.accept()
            return
        if self._drag == "move":
            update_move(self, event)
            _emit_live(self)
            event.accept()
            return
        event.ignore()

    def mouseReleaseEvent(self, event) -> None:
        if self._editing:
            QGraphicsTextItem.mouseReleaseEvent(self, event)
            return
        drag = self._drag
        self._drag = None
        if drag == "resize":
            _commit_properties(self, self._start_props, "Text size")
            event.accept()
            return
        if drag == "move":
            finish_move(self)
            event.accept()
            return
        event.accept()

    def hoverMoveEvent(self, event) -> None:
        if self._show_chrome() and self._hit_resize_handle(event.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif not self._editing:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        event.accept()

    def focusOutEvent(self, event) -> None:
        self.end_edit()
        super().focusOutEvent(event)

    def _apply_style(self) -> None:
        font = QFont(self._font_family)
        font.setPointSizeF(max(MIN_FONT, self._font_size))
        cursor_pos = None
        cursor_anchor = None
        if self._editing:
            current = self.textCursor()
            cursor_pos = current.position()
            cursor_anchor = current.anchor()
        self.setFont(font)
        self.document().setDefaultFont(font)
        self.setDefaultTextColor(self._color)
        fmt = QTextCharFormat()
        fmt.setFont(font)
        fmt.setForeground(QBrush(self._color))
        if self._outline:
            pen = QPen(contrasting_color(self._color))
            pen.setWidthF(max(1.15, self._font_size / 16.0))
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            fmt.setTextOutline(pen)
        else:
            fmt.setTextOutline(QPen(Qt.PenStyle.NoPen))
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.setCharFormat(fmt)
        if self._editing and cursor_pos is not None:
            restored = self.textCursor()
            restored.setPosition(cursor_anchor)
            restored.setPosition(cursor_pos, QTextCursor.MoveMode.KeepAnchor)
            restored.setCharFormat(fmt)
            self.setTextCursor(restored)
        else:
            restored = self.textCursor()
            restored.clearSelection()
            restored.setCharFormat(fmt)
            self.setTextCursor(restored)
        self.update()

    def _show_chrome(self) -> bool:
        return _show_chrome(self) and not self._editing

    def _handle_radius(self) -> float:
        return 7.0 / view_scale_of(self)

    def _resize_handle_center(self) -> QPointF:
        rect = QGraphicsTextItem.boundingRect(self)
        return QPointF(rect.right(), rect.bottom())

    def _hit_resize_handle(self, pos: QPointF) -> bool:
        if not self._show_chrome():
            return False
        center = self._resize_handle_center()
        radius = self._handle_radius() * 1.8
        return abs(pos.x() - center.x()) <= radius and abs(pos.y() - center.y()) <= radius

    def _apply_font_drag(self, scene_pos: QPointF) -> None:
        scale = view_scale_of(self)
        screen_dx = (scene_pos.x() - self._press_scene.x()) * scale
        screen_dy = (scene_pos.y() - self._press_scene.y()) * scale
        delta = screen_dy if abs(screen_dy) >= abs(screen_dx) else screen_dx
        self.set_font_size(self._start_font + delta * 0.28)

    def _paint_chrome(self, painter: QPainter) -> None:
        radius = self._handle_radius()
        body = QGraphicsTextItem.boundingRect(self)
        pen = QPen(QColor("#0067c0"))
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(body)
        center = self._resize_handle_center()
        painter.setPen(QPen(QColor("#0067c0")))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))


class ArrowItem(QGraphicsObject):
    def __init__(
        self,
        length: float = 170,
        thickness: float = 18,
        color: QColor | str = "#000000",
        outline: bool = True,
        rotation: float = 0,
    ):
        super().__init__()
        self._length = float(length)
        self._thickness = float(thickness)
        self._color = QColor(color)
        self._outline = bool(outline)
        self._path = self._make_path()
        self._drag = None
        self._start_props = None
        self._press_scene = QPointF()
        self._pointer_angle = 0.0
        self._start_rotation = 0.0
        self._drag_tail = QPointF()
        self._move_origins = {}
        self.setRotation(rotation)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def length(self) -> float:
        return self._length

    def thickness(self) -> float:
        return self._thickness

    def color(self) -> QColor:
        return QColor(self._color)

    def outline_enabled(self) -> bool:
        return self._outline

    def properties(self) -> dict:
        return {
            "pos": (float(self.pos().x()), float(self.pos().y())),
            "rotation": float(self.rotation()),
            "length": float(self._length),
            "thickness": float(self._thickness),
            "color": color_hex(self._color),
            "outline": bool(self._outline),
        }

    def apply_properties(self, props: dict) -> None:
        self.prepareGeometryChange()
        self._length = float(props["length"])
        self._thickness = float(props["thickness"])
        self._color = QColor(props["color"])
        self._outline = bool(props["outline"])
        self._path = self._make_path()
        self.setRotation(float(props["rotation"]))
        x, y = props["pos"]
        self.setPos(float(x), float(y))
        self.update()

    def set_color(self, color: QColor | str) -> None:
        self._color = QColor(color)
        self.update()

    def set_outline(self, enabled: bool) -> None:
        self.prepareGeometryChange()
        self._outline = bool(enabled)
        self.update()

    def set_angle(self, angle: float) -> None:
        self.setRotation(float(angle))
        self.update()

    def set_length(self, length: float, anchor: str = "center", tail_scene: QPointF | None = None) -> None:
        length = float(max(MIN_LENGTH, min(MAX_LENGTH, length)))
        tail = None
        if anchor == "tail":
            tail = (
                QPointF(tail_scene)
                if tail_scene is not None
                else self.mapToScene(QPointF(-self._length / 2.0, 0.0))
            )
        if anchor == "center" and abs(length - self._length) < 0.04:
            return
        self.prepareGeometryChange()
        self._length = length
        self._path = self._make_path()
        if tail is not None:
            current = self.mapToScene(QPointF(-self._length / 2.0, 0.0))
            delta = tail - current
            if abs(delta.x()) > 1e-4 or abs(delta.y()) > 1e-4:
                self.setPos(self.pos() + delta)
        self.update()

    def set_thickness(self, thickness: float) -> None:
        thickness = float(max(MIN_THICKNESS, min(MAX_THICKNESS, thickness)))
        if abs(thickness - self._thickness) < 0.04:
            return
        self.prepareGeometryChange()
        self._thickness = thickness
        self._path = self._make_path()
        self.update()

    def scale_with_image(self, sx: float, sy: float) -> None:
        tail = self.mapToScene(QPointF(-self._length / 2.0, 0.0))
        tip = self.mapToScene(QPointF(self._length / 2.0, 0.0))
        tail2 = QPointF(tail.x() * sx, tail.y() * sy)
        tip2 = QPointF(tip.x() * sx, tip.y() * sy)
        dx = tip2.x() - tail2.x()
        dy = tip2.y() - tail2.y()
        length = max(math.hypot(dx, dy), 8.0)
        angle = math.degrees(math.atan2(dy, dx))
        props = self.properties()
        props["pos"] = ((tail2.x() + tip2.x()) / 2.0, (tail2.y() + tip2.y()) / 2.0)
        props["length"] = max(MIN_LENGTH, min(MAX_LENGTH, length))
        props["rotation"] = angle
        props["thickness"] = max(MIN_THICKNESS, min(MAX_THICKNESS, self._thickness * ((sx + sy) / 2.0)))
        self.apply_properties(props)

    def wheel_resize(self, steps: int) -> None:
        old = self.properties()
        factor = 1.1 ** steps
        self.set_length(self._length * factor, anchor="center")
        self.set_thickness(self._thickness * factor)
        scene = self.scene()
        if scene is not None:
            scene.push_properties([(self, old, self.properties())], "Scale arrow", merge_key=("arrow", id(self)))

    def boundingRect(self) -> QRectF:
        extra = 4.0 if self._outline else 1.5
        rect = self._path.boundingRect().adjusted(-extra, -extra, extra, extra)
        if _show_chrome(self):
            radius = self._handle_radius()
            for center in self._handle_centers().values():
                rect = rect.united(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))
        return rect

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(12.0 / view_scale_of(self), self._thickness))
        path = stroker.createStroke(self._path)
        path.addPath(self._path)
        if _show_chrome(self):
            radius = self._handle_radius() * 1.8
            for center in self._handle_centers().values():
                path.addEllipse(center, radius, radius)
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._outline:
            pen = QPen(contrasting_color(self._color))
            pen.setWidthF(max(1.6, min(3.0, self._thickness * 0.12)))
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            pen.setMiterLimit(2.8)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawPath(self._path)
        if _show_chrome(self):
            self._paint_chrome(painter)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.prepareGeometryChange()
            if bool(value):
                scene = self.scene()
                if scene is not None and hasattr(scene, "raise_annotation"):
                    scene.raise_annotation(self)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        handle = self._hit_handle(event.pos()) if self.isSelected() else None
        if handle:
            self._drag = handle
            self._start_props = self.properties()
            self._press_scene = QPointF(event.scenePos())
            center = self.mapToScene(QPointF(0.0, 0.0))
            self._pointer_angle = math.degrees(
                math.atan2(event.scenePos().y() - center.y(), event.scenePos().x() - center.x())
            )
            self._start_rotation = self.rotation()
            self._drag_tail = self.mapToScene(QPointF(-self._length / 2.0, 0.0))
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        if not select_on_press(self, event):
            event.accept()
            return
        self._drag = "move"
        start_move(self, event)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag == "length":
            projected = self._projected_length(event.scenePos(), self._drag_tail)
            self.set_length(projected, anchor="tail", tail_scene=self._drag_tail)
            _emit_live(self)
            event.accept()
            return
        if self._drag == "thickness":
            gap = self._handle_radius() * 1.6
            self.set_thickness((abs(event.pos().y()) - gap) * 2.0)
            _emit_live(self)
            event.accept()
            return
        if self._drag == "rotate":
            self._apply_rotation(event.scenePos(), bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            _emit_live(self)
            event.accept()
            return
        if self._drag == "move":
            update_move(self, event)
            _emit_live(self)
            event.accept()
            return
        event.ignore()

    def mouseReleaseEvent(self, event) -> None:
        drag = self._drag
        self._drag = None
        labels = {
            "length": "Arrow length",
            "thickness": "Arrow thickness",
            "rotate": "Rotate",
        }
        if drag in labels:
            _commit_properties(self, self._start_props, labels[drag])
            event.accept()
            return
        if drag == "move":
            finish_move(self)
            event.accept()
            return
        event.accept()

    def hoverMoveEvent(self, event) -> None:
        handle = self._hit_handle(event.pos()) if self.isSelected() else None
        cursors = {
            "rotate": Qt.CursorShape.CrossCursor,
            "length": Qt.CursorShape.SizeHorCursor,
            "thickness": Qt.CursorShape.SizeVerCursor,
        }
        self.setCursor(cursors.get(handle, Qt.CursorShape.SizeAllCursor))
        event.accept()

    def _make_path(self) -> QPainterPath:
        return build_arrow_path(self._length, self._thickness)

    def _handle_radius(self) -> float:
        return 7.0 / view_scale_of(self)

    def _handle_centers(self) -> dict[str, QPointF]:
        radius = self._handle_radius()
        top = self._path.boundingRect().top()
        return {
            "length": QPointF(self._length / 2.0, 0.0),
            "thickness": QPointF(0.0, -(self._thickness / 2.0 + radius * 1.6)),
            "rotate": QPointF(0.0, top - radius * 3.2),
        }

    def _hit_handle(self, pos: QPointF) -> str | None:
        if not _show_chrome(self):
            return None
        radius = self._handle_radius() * 1.7
        # The rotation handle sits farthest out, so test it first.
        for name in ("rotate", "length", "thickness"):
            center = self._handle_centers()[name]
            if abs(pos.x() - center.x()) <= radius and abs(pos.y() - center.y()) <= radius:
                return name
        return None

    def _projected_length(self, scene_pos: QPointF, tail_scene: QPointF) -> float:
        tip = self.mapToScene(QPointF(self._length / 2.0, 0.0))
        axis_x = tip.x() - tail_scene.x()
        axis_y = tip.y() - tail_scene.y()
        magnitude = math.hypot(axis_x, axis_y)
        if magnitude < 1e-3:
            return self._length
        rel_x = scene_pos.x() - tail_scene.x()
        rel_y = scene_pos.y() - tail_scene.y()
        return (rel_x * axis_x + rel_y * axis_y) / magnitude

    def _apply_rotation(self, scene_pos: QPointF, snap: bool) -> None:
        center = self.mapToScene(QPointF(0.0, 0.0))
        pointer = math.degrees(math.atan2(scene_pos.y() - center.y(), scene_pos.x() - center.x()))
        delta = pointer - self._pointer_angle
        while delta > 180.0:
            delta -= 360.0
        while delta < -180.0:
            delta += 360.0
        angle = self._start_rotation + delta
        if snap:
            angle = snap_angle(angle, 15.0)
        self.setRotation(angle)

    def _paint_chrome(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = self._handle_radius()
        pen = QPen(QColor("#0067c0"))
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._path.boundingRect())
        centers = self._handle_centers()
        solid = QPen(QColor("#0067c0"))
        solid.setCosmetic(True)
        solid.setWidthF(1.25)
        painter.setPen(solid)
        painter.drawLine(QPointF(0.0, self._path.boundingRect().top()), centers["rotate"])
        painter.setBrush(QColor("#ffffff"))
        for center in centers.values():
            painter.drawEllipse(center, radius, radius)


class DoubleArrowItem(ArrowItem):
    """Same as an arrow, with a head at both ends."""

    def _make_path(self) -> QPainterPath:
        return build_double_arrow_path(self._length, self._thickness)


class EllipseItem(QGraphicsObject):
    """Unfilled oval. Width and height resize independently."""

    def __init__(
        self,
        width: float = 120,
        height: float = 120,
        thickness: float = 18,
        color: QColor | str = "#000000",
        outline: bool = True,
        rotation: float = 0,
    ):
        super().__init__()
        self._width = float(width)
        self._height = float(height)
        self._thickness = float(thickness)
        self._color = QColor(color)
        self._outline = bool(outline)
        self._drag = None
        self._start_props = None
        self._press_scene = QPointF()
        self._pointer_angle = 0.0
        self._start_rotation = 0.0
        self._drag_anchor = QPointF()
        self._move_origins = {}
        self.setRotation(rotation)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def width(self) -> float:
        return self._width

    def height(self) -> float:
        return self._height

    def thickness(self) -> float:
        return self._thickness

    def color(self) -> QColor:
        return QColor(self._color)

    def outline_enabled(self) -> bool:
        return self._outline

    def properties(self) -> dict:
        return {
            "pos": (float(self.pos().x()), float(self.pos().y())),
            "rotation": float(self.rotation()),
            "width": float(self._width),
            "height": float(self._height),
            "thickness": float(self._thickness),
            "color": color_hex(self._color),
            "outline": bool(self._outline),
        }

    def apply_properties(self, props: dict) -> None:
        self.prepareGeometryChange()
        self._width = float(props["width"])
        self._height = float(props["height"])
        self._thickness = float(props["thickness"])
        self._color = QColor(props["color"])
        self._outline = bool(props["outline"])
        self.setRotation(float(props["rotation"]))
        x, y = props["pos"]
        self.setPos(float(x), float(y))
        self.update()

    def set_color(self, color: QColor | str) -> None:
        self._color = QColor(color)
        self.update()

    def set_outline(self, enabled: bool) -> None:
        self.prepareGeometryChange()
        self._outline = bool(enabled)
        self.update()

    def set_angle(self, angle: float) -> None:
        self.setRotation(float(angle))
        self.update()

    def set_width(self, width: float, anchor: str = "center", edge_scene: QPointF | None = None) -> None:
        width = float(max(MIN_SPAN, min(MAX_SPAN, width)))
        edge = None
        if anchor == "left":
            edge = (
                QPointF(edge_scene)
                if edge_scene is not None
                else self.mapToScene(QPointF(-self._width / 2.0, 0.0))
            )
        if anchor == "center" and abs(width - self._width) < 0.04:
            return
        self.prepareGeometryChange()
        self._width = width
        if edge is not None:
            current = self.mapToScene(QPointF(-self._width / 2.0, 0.0))
            delta = edge - current
            if abs(delta.x()) > 1e-4 or abs(delta.y()) > 1e-4:
                self.setPos(self.pos() + delta)
        self.update()

    def set_height(self, height: float, anchor: str = "center", edge_scene: QPointF | None = None) -> None:
        height = float(max(MIN_SPAN, min(MAX_SPAN, height)))
        edge = None
        if anchor == "top":
            edge = (
                QPointF(edge_scene)
                if edge_scene is not None
                else self.mapToScene(QPointF(0.0, -self._height / 2.0))
            )
        if anchor == "center" and abs(height - self._height) < 0.04:
            return
        self.prepareGeometryChange()
        self._height = height
        if edge is not None:
            current = self.mapToScene(QPointF(0.0, -self._height / 2.0))
            delta = edge - current
            if abs(delta.x()) > 1e-4 or abs(delta.y()) > 1e-4:
                self.setPos(self.pos() + delta)
        self.update()

    def set_size(self, width: float, height: float) -> None:
        width = float(max(MIN_SPAN, min(MAX_SPAN, width)))
        height = float(max(MIN_SPAN, min(MAX_SPAN, height)))
        if abs(width - self._width) < 0.04 and abs(height - self._height) < 0.04:
            return
        self.prepareGeometryChange()
        self._width = width
        self._height = height
        self.update()

    def set_thickness(self, thickness: float) -> None:
        thickness = float(max(MIN_THICKNESS, min(MAX_THICKNESS, thickness)))
        if abs(thickness - self._thickness) < 0.04:
            return
        self.prepareGeometryChange()
        self._thickness = thickness
        self.update()

    def scale_with_image(self, sx: float, sy: float) -> None:
        center = self.mapToScene(QPointF(0.0, 0.0))
        right = self.mapToScene(QPointF(self._width / 2.0, 0.0))
        bottom = self.mapToScene(QPointF(0.0, self._height / 2.0))
        center2 = QPointF(center.x() * sx, center.y() * sy)
        right2 = QPointF(right.x() * sx, right.y() * sy)
        bottom2 = QPointF(bottom.x() * sx, bottom.y() * sy)
        vx = right2 - center2
        vy = bottom2 - center2
        props = self.properties()
        props["pos"] = (center2.x(), center2.y())
        props["width"] = max(MIN_SPAN, min(MAX_SPAN, 2.0 * math.hypot(vx.x(), vx.y())))
        props["height"] = max(MIN_SPAN, min(MAX_SPAN, 2.0 * math.hypot(vy.x(), vy.y())))
        props["rotation"] = math.degrees(math.atan2(vx.y(), vx.x()))
        props["thickness"] = max(MIN_THICKNESS, min(MAX_THICKNESS, self._thickness * ((sx + sy) / 2.0)))
        self.apply_properties(props)

    def wheel_resize(self, steps: int) -> None:
        old = self.properties()
        factor = 1.1 ** steps
        self.set_size(self._width * factor, self._height * factor)
        self.set_thickness(self._thickness * factor)
        scene = self.scene()
        if scene is not None:
            scene.push_properties([(self, old, self.properties())], "Scale oval", merge_key=("oval", id(self)))

    def boundingRect(self) -> QRectF:
        pad = self._stroke_pad()
        rect = self._local_rect().adjusted(-pad, -pad, pad, pad)
        if _show_chrome(self):
            radius = self._handle_radius()
            for center in self._handle_centers().values():
                rect = rect.united(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))
        return rect

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self._local_rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._thickness, 12.0 / view_scale_of(self)))
        path.addPath(stroker.createStroke(path))
        if _show_chrome(self):
            radius = self._handle_radius() * 1.8
            for center in self._handle_centers().values():
                path.addEllipse(center, radius, radius)
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = self._local_rect()
        if self._outline:
            halo = QPen(contrasting_color(self._color))
            halo.setWidthF(self._thickness + self._halo_extra() * 2.0)
            halo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            halo.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(halo)
            painter.drawEllipse(rect)
        pen = QPen(self._color)
        pen.setWidthF(self._thickness)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(rect)
        if _show_chrome(self):
            self._paint_chrome(painter)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.prepareGeometryChange()
            if bool(value):
                scene = self.scene()
                if scene is not None and hasattr(scene, "raise_annotation"):
                    scene.raise_annotation(self)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        handle = self._hit_handle(event.pos()) if self.isSelected() else None
        if handle:
            self._drag = handle
            self._start_props = self.properties()
            self._press_scene = QPointF(event.scenePos())
            center = self.mapToScene(QPointF(0.0, 0.0))
            self._pointer_angle = math.degrees(
                math.atan2(event.scenePos().y() - center.y(), event.scenePos().x() - center.x())
            )
            self._start_rotation = self.rotation()
            if handle == "width":
                self._drag_anchor = self.mapToScene(QPointF(-self._width / 2.0, 0.0))
            elif handle == "height":
                self._drag_anchor = self.mapToScene(QPointF(0.0, -self._height / 2.0))
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        if not select_on_press(self, event):
            event.accept()
            return
        self._drag = "move"
        start_move(self, event)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag == "width":
            far = self.mapToScene(QPointF(self._width / 2.0, 0.0))
            self.set_width(self._projected_span(event.scenePos(), self._drag_anchor, far), anchor="left", edge_scene=self._drag_anchor)
            _emit_live(self)
            event.accept()
            return
        if self._drag == "height":
            far = self.mapToScene(QPointF(0.0, self._height / 2.0))
            self.set_height(self._projected_span(event.scenePos(), self._drag_anchor, far), anchor="top", edge_scene=self._drag_anchor)
            _emit_live(self)
            event.accept()
            return
        if self._drag == "thickness":
            gap = self._handle_radius() * 1.6
            self.set_thickness((event.pos().x() - self._width / 2.0 - gap) * 2.0)
            _emit_live(self)
            event.accept()
            return
        if self._drag == "rotate":
            self._apply_rotation(event.scenePos(), bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            _emit_live(self)
            event.accept()
            return
        if self._drag == "move":
            update_move(self, event)
            _emit_live(self)
            event.accept()
            return
        event.ignore()

    def mouseReleaseEvent(self, event) -> None:
        drag = self._drag
        self._drag = None
        labels = {
            "width": "Oval width",
            "height": "Oval height",
            "thickness": "Oval thickness",
            "rotate": "Rotate",
        }
        if drag in labels:
            _commit_properties(self, self._start_props, labels[drag])
            event.accept()
            return
        if drag == "move":
            finish_move(self)
            event.accept()
            return
        event.accept()

    def hoverMoveEvent(self, event) -> None:
        handle = self._hit_handle(event.pos()) if self.isSelected() else None
        cursors = {
            "rotate": Qt.CursorShape.CrossCursor,
            "width": Qt.CursorShape.SizeHorCursor,
            "height": Qt.CursorShape.SizeVerCursor,
            "thickness": Qt.CursorShape.SizeHorCursor,
        }
        self.setCursor(cursors.get(handle, Qt.CursorShape.SizeAllCursor))
        event.accept()

    def _local_rect(self) -> QRectF:
        return QRectF(-self._width / 2.0, -self._height / 2.0, self._width, self._height)

    def _halo_extra(self) -> float:
        return max(1.6, min(3.0, self._thickness * 0.12))

    def _stroke_pad(self) -> float:
        extra = self._halo_extra() if self._outline else 0.0
        return self._thickness / 2.0 + extra + 1.5

    def _handle_radius(self) -> float:
        return 7.0 / view_scale_of(self)

    def _handle_centers(self) -> dict[str, QPointF]:
        radius = self._handle_radius()
        return {
            "width": QPointF(self._width / 2.0, 0.0),
            "height": QPointF(0.0, self._height / 2.0),
            "thickness": QPointF(self._width / 2.0 + self._thickness / 2.0 + radius * 1.6, 0.0),
            "rotate": QPointF(0.0, -self._height / 2.0 - radius * 3.2),
        }

    def _hit_handle(self, pos: QPointF) -> str | None:
        if not _show_chrome(self):
            return None
        radius = self._handle_radius() * 1.7
        for name in ("rotate", "thickness", "width", "height"):
            center = self._handle_centers()[name]
            if abs(pos.x() - center.x()) <= radius and abs(pos.y() - center.y()) <= radius:
                return name
        return None

    def _projected_span(self, scene_pos: QPointF, anchor: QPointF, far: QPointF) -> float:
        axis_x = far.x() - anchor.x()
        axis_y = far.y() - anchor.y()
        magnitude = math.hypot(axis_x, axis_y)
        if magnitude < 1e-3:
            return magnitude
        rel_x = scene_pos.x() - anchor.x()
        rel_y = scene_pos.y() - anchor.y()
        return (rel_x * axis_x + rel_y * axis_y) / magnitude

    def _apply_rotation(self, scene_pos: QPointF, snap: bool) -> None:
        center = self.mapToScene(QPointF(0.0, 0.0))
        pointer = math.degrees(math.atan2(scene_pos.y() - center.y(), scene_pos.x() - center.x()))
        delta = pointer - self._pointer_angle
        while delta > 180.0:
            delta -= 360.0
        while delta < -180.0:
            delta += 360.0
        angle = self._start_rotation + delta
        if snap:
            angle = snap_angle(angle, 15.0)
        self.setRotation(angle)

    def _paint_chrome(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = self._handle_radius()
        pen = QPen(QColor("#0067c0"))
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._local_rect())
        centers = self._handle_centers()
        solid = QPen(QColor("#0067c0"))
        solid.setCosmetic(True)
        solid.setWidthF(1.25)
        painter.setPen(solid)
        painter.drawLine(QPointF(0.0, -self._height / 2.0), centers["rotate"])
        painter.setBrush(QColor("#ffffff"))
        for center in centers.values():
            painter.drawEllipse(center, radius, radius)


def is_annotation(item) -> bool:
    return isinstance(item, (AnnotationTextItem, ArrowItem, EllipseItem))
