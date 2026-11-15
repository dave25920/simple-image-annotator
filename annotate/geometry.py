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


def arrow_metrics(length: float, thickness: float) -> dict[str, float]:
    """Shaft and head sizes for a straight arrow of the given length.

    The head is always shorter than the shaft-plus-head length and wider
    than the shaft, so the shape still reads as an arrow when it is short.
    """

    length = max(float(length), 8.0)
    thickness = max(float(thickness), 1.0)
    head_len = max(thickness * 2.4, min(length * 0.34, thickness * 5.0))
    head_len = min(head_len, length * 0.62)
    head_w = max(thickness * 2.8, thickness + 6.0)
    return {
        "length": length,
        "thickness": thickness,
        "head_len": head_len,
        "head_w": head_w,
        "shaft_len": length - head_len,
    }
