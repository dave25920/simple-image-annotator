"""Selection and group-move helpers shared by text and arrows."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QGraphicsItem

from annotate.commands import MoveCommand


def _is_movable(item) -> bool:
    flags = item.flags()
    movable = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    return bool(flags & movable)


def select_on_press(item, event) -> bool:
    """Apply the usual click-to-select rules. Return whether ``item`` is selected."""

    scene = item.scene()
    mods = event.modifiers()
    ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
    shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
    if ctrl:
        item.setSelected(not item.isSelected())
    elif shift:
        item.setSelected(True)
    elif not item.isSelected():
        if scene is not None:
            scene.clearSelection()
        item.setSelected(True)
    return item.isSelected()


def begin_group_move(item) -> dict:
    origins = {}
    scene = item.scene()
    selected = []
    if scene is not None:
        selected = [other for other in scene.selectedItems() if _is_movable(other)]
    if item not in selected and _is_movable(item):
        selected.append(item)
    for other in selected:
        origins[other] = QPointF(other.pos())
    return origins


def start_move(item, event) -> None:
    item._press_scene = QPointF(event.scenePos())
    item._move_origins = begin_group_move(item)


def update_move(item, event) -> None:
    origins = getattr(item, "_move_origins", None)
    press = getattr(item, "_press_scene", None)
    if not origins or press is None:
        return
    delta = event.scenePos() - press
    for other, origin in origins.items():
        other.setPos(origin.x() + delta.x(), origin.y() + delta.y())


def finish_move(item) -> None:
    origins = getattr(item, "_move_origins", None) or {}
    item._move_origins = {}
    changes = []
    for other, origin in origins.items():
        if abs(other.pos().x() - origin.x()) > 0.51 or abs(other.pos().y() - origin.y()) > 0.51:
            changes.append((other, QPointF(origin), QPointF(other.pos())))
    if not changes:
        return
    scene = item.scene()
    if scene is not None:
        scene.undo_stack.push(MoveCommand(changes))
