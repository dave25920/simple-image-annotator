"""Pure helpers for image resize math and arrow proportions.

These functions stay free of Qt so they can be tested without a display.
"""

from __future__ import annotations

import math


def linked_dimensions(
    orig_w: int,
    orig_h: int,
    changed: str,
    value: float,
    keep_aspect: bool,
    current_w: int | None = None,
    current_h: int | None = None,
) -> tuple[int, int]:
    """Return ``(width, height)`` after editing one resize field.

    ``changed`` is one of ``width_px``, ``height_px``, ``width_pct``, or
    ``height_pct``. Percentages are relative to the original image.
    When ``keep_aspect`` is set, the other side follows the original aspect
    ratio. Otherwise the side that was not edited stays at its current value.
    """

    orig_w = max(1, int(orig_w))
    orig_h = max(1, int(orig_h))
    current_w = orig_w if current_w is None else max(1, int(current_w))
    current_h = orig_h if current_h is None else max(1, int(current_h))

    if changed == "width_px":
        width = max(1, int(round(value)))
        height = (
            max(1, int(round(width * orig_h / orig_w))) if keep_aspect else current_h
        )
    elif changed == "height_px":
        height = max(1, int(round(value)))
        width = (
            max(1, int(round(height * orig_w / orig_h))) if keep_aspect else current_w
        )
    elif changed == "width_pct":
        width = max(1, int(round(orig_w * float(value) / 100.0)))
        height = (
            max(1, int(round(orig_h * float(value) / 100.0)))
            if keep_aspect
            else current_h
        )
    elif changed == "height_pct":
        height = max(1, int(round(orig_h * float(value) / 100.0)))
        width = (
            max(1, int(round(orig_w * float(value) / 100.0)))
            if keep_aspect
            else current_w
        )
    else:
        raise ValueError(f"Unknown resize field: {changed}")
    return width, height


def snap_angle(angle: float, step: float = 15.0) -> float:
    """Snap ``angle`` to the nearest multiple of ``step`` degrees."""

    if step <= 0:
        return float(angle)
    return math.floor(float(angle) / step + 0.5) * step


def normalize_angle(angle: float) -> float:
    """Wrap degrees into the half-open range ``(-180, 180]``."""

    value = float(angle) % 360.0
    if value > 180.0:
        value -= 360.0
    if value <= -180.0:
        value += 360.0
    return value


def arrow_metrics(length: float, thickness: float, heads: int = 1) -> dict[str, float]:
    """Shaft and head sizes for a straight arrow of the given length.

    The head is always shorter than the shaft-plus-head length and wider
    than the shaft, so the shape still reads as an arrow when it is short.
    ``heads`` is 1 for a normal arrow and 2 for a double-headed arrow.
    Two heads are shortened so both fit on the shaft.
    """

    length = max(float(length), 8.0)
    thickness = max(float(thickness), 1.0)
    head_count = 2 if int(heads) >= 2 else 1
    head_len = max(thickness * 2.4, min(length * 0.34, thickness * 5.0))
    head_len = min(head_len, length * 0.62)
    if head_count == 2:
        head_len = min(head_len, length * 0.42)
    head_w = max(thickness * 2.8, thickness + 6.0)
    return {
        "length": length,
        "thickness": thickness,
        "head_len": head_len,
        "head_w": head_w,
        "shaft_len": length - head_len * head_count,
    }


def ellipse_box(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    constrain: bool = False,
    min_size: float = 16.0,
    default_width: float = 120.0,
    default_height: float = 120.0,
) -> tuple[float, float, float, float]:
    """Return ``(center_x, center_y, width, height)`` for an oval drag.

    A short drag drops the default size, centered on the press point.
    A longer drag uses the press and release as opposite corners.
    ``constrain`` forces a circle whose diameter is the longer side.
    """

    dx = float(x1) - float(x0)
    dy = float(y1) - float(y0)
    if math.hypot(dx, dy) < 10.0:
        return (float(x0), float(y0), float(default_width), float(default_height))
    if constrain:
        side = max(abs(dx), abs(dy), float(min_size))
        dx = math.copysign(side, dx) if dx != 0.0 else side
        dy = math.copysign(side, dy) if dy != 0.0 else side
    width = max(abs(dx), float(min_size))
    height = max(abs(dy), float(min_size))
    return (float(x0) + dx / 2.0, float(y0) + dy / 2.0, width, height)
