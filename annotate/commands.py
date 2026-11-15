"""Undo commands for annotations and image resize.

Items are applied by the caller before a property command is pushed, and
``redo`` writes the same values again. ``AnnotationScene.push_properties``
folds rapid repeats (spin boxes, mouse wheel) into the previous command.
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtGui import QImage, QUndoCommand


Props = dict[str, Any]


def copy_props(props: Props) -> Props:
    copied: Props = {}
    for key, value in props.items():
        if isinstance(value, tuple):
            copied[key] = tuple(value)
        else:
            copied[key] = value
    return copied


def props_equal(left: Props, right: Props, eps: float = 0.05) -> bool:
    if left.keys() != right.keys():
        return False
    for key in left:
        a = left[key]
        b = right[key]
        if isinstance(a, bool) or isinstance(b, bool):
            if a != b:
                return False
            continue
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if abs(float(a) - float(b)) > eps:
                return False
            continue
        if isinstance(a, tuple) and isinstance(b, tuple):
            if len(a) != len(b):
                return False
            for part_a, part_b in zip(a, b):
                if isinstance(part_a, (int, float)) and isinstance(part_b, (int, float)):
                    if abs(float(part_a) - float(part_b)) > eps:
                        return False
                elif part_a != part_b:
                    return False
            continue
        if a != b:
            return False
    return True


class PropertyCommand(QUndoCommand):
    def __init__(self, changes: list[tuple[Any, Props, Props]], text: str, merge_key=None):
        super().__init__(text)
        self.changes = [
            (item, copy_props(old), copy_props(new)) for item, old, new in changes
        ]
        self.merge_key = merge_key
        self.timestamp = time.monotonic()

    def _apply(self, which: str) -> None:
        for item, old, new in self.changes:
            item.apply_properties(old if which == "old" else new)

    def undo(self) -> None:
        self._apply("old")

    def redo(self) -> None:
        self._apply("new")

    def can_merge(self, merge_key, changes: list[tuple[Any, Props, Props]]) -> bool:
        if self.merge_key is None or merge_key != self.merge_key:
            return False
        if time.monotonic() - self.timestamp > 1.2:
            return False
        current_items = [item for item, _old, _new in self.changes]
        incoming_items = [item for item, _old, _new in changes]
        return current_items == incoming_items

    def absorb(self, changes: list[tuple[Any, Props, Props]]) -> None:
        self.changes = [
            (item, old, copy_props(new))
            for (item, old, _previous), (_item, _old, new) in zip(self.changes, changes)
        ]
        self.timestamp = time.monotonic()


class AddCommand(QUndoCommand):
    def __init__(self, scene, item, text: str):
        super().__init__(text)
        self.scene = scene
        self.item = item

    def redo(self) -> None:
        self.scene.attach_annotation(self.item)

    def undo(self) -> None:
        self.scene.detach_annotation(self.item)


class DeleteCommand(QUndoCommand):
    def __init__(self, scene, items: list):
        label = "Delete" if len(items) == 1 else f"Delete {len(items)} items"
        super().__init__(label)
        self.scene = scene
        self.items = list(items)

    def redo(self) -> None:
        for item in self.items:
            self.scene.detach_annotation(item)

    def undo(self) -> None:
        for item in self.items:
            self.scene.attach_annotation(item)


class MoveCommand(QUndoCommand):
    def __init__(self, changes: list[tuple[Any, Any, Any]]):
        label = "Move" if len(changes) == 1 else f"Move {len(changes)} items"
        super().__init__(label)
        self.changes = []
        for item, old, new in changes:
            self.changes.append((item, (float(old.x()), float(old.y())), (float(new.x()), float(new.y()))))

    def _apply(self, index: int) -> None:
        for item, old, new in self.changes:
            x, y = old if index == 0 else new
            item.setPos(x, y)

    def undo(self) -> None:
        self._apply(0)

    def redo(self) -> None:
        self._apply(1)


class ResizeImageCommand(QUndoCommand):
    def __init__(self, scene, old_image: QImage, new_image: QImage, before: list, after: list):
        super().__init__("Resize image")
        self.scene = scene
        self.old_image = old_image
        self.new_image = new_image
        self.before = [(item, copy_props(props)) for item, props in before]
        self.after = [(item, copy_props(props)) for item, props in after]

    def undo(self) -> None:
        self.scene.install_image(self.old_image)
        self.scene.restore_snapshots(self.before)

    def redo(self) -> None:
        self.scene.install_image(self.new_image)
        self.scene.restore_snapshots(self.after)
