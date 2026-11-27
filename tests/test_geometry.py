import pytest

from annotate.geometry import arrow_metrics, ellipse_box, linked_dimensions, normalize_angle, snap_angle


def test_percent_keeps_aspect_ratio():
    assert linked_dimensions(1000, 500, "width_pct", 50, True) == (500, 250)
    assert linked_dimensions(1000, 500, "height_pct", 200, True) == (2000, 1000)


def test_pixel_edit_keeps_original_aspect():
    assert linked_dimensions(1000, 500, "width_px", 200, True) == (200, 100)
    assert linked_dimensions(101, 50, "width_px", 50, True) == (50, 25)


def test_unlocked_edit_keeps_the_other_side():
    assert linked_dimensions(
        1000, 500, "width_px", 800, False, current_w=1000, current_h=320
    ) == (800, 320)
    assert linked_dimensions(
        200, 100, "height_pct", 50, False, current_w=180, current_h=100
    ) == (180, 50)


def test_dimensions_never_drop_below_one_pixel():
    assert linked_dimensions(20, 10, "width_pct", 0, True) == (1, 1)


def test_unknown_field_is_rejected():
    with pytest.raises(ValueError):
        linked_dimensions(10, 10, "diagonal", 1, True)


def test_snap_angle_steps_by_fifteen_degrees():
    assert snap_angle(0) == 0
    assert snap_angle(7) == 0
    assert snap_angle(8) == 15
    assert snap_angle(22) == 15
    assert snap_angle(23) == 30
    assert snap_angle(-8) == -15
    assert snap_angle(90) == 90


def test_normalize_angle_wraps_to_signed_range():
    assert normalize_angle(0) == 0
    assert normalize_angle(180) == 180
    assert normalize_angle(190) == pytest.approx(-170)
    assert normalize_angle(-30) == pytest.approx(-30)
    assert normalize_angle(360) == pytest.approx(0)


def test_arrow_head_is_shorter_than_the_shaft_and_wider():
    metrics = arrow_metrics(120, 10)
    assert metrics["head_len"] < metrics["length"]
    assert metrics["shaft_len"] > 0
    assert metrics["head_w"] > metrics["thickness"]
    short = arrow_metrics(18, 8)
    assert short["head_len"] <= short["length"] * 0.62 + 0.01


def test_double_arrow_heads_both_fit():
    metrics = arrow_metrics(40, 16, heads=2)
    assert metrics["head_len"] * 2 <= metrics["length"] + 0.01
    assert metrics["shaft_len"] >= 0
    long = arrow_metrics(200, 12, heads=2)
    assert long["head_w"] > long["thickness"]
    assert long["shaft_len"] > 0


def test_ellipse_box_click_drops_the_default_and_drag_sets_corners():
    assert ellipse_box(10, 20, 14, 22) == (10, 20, 120, 120)
    center_x, center_y, width, height = ellipse_box(10, 20, 110, 80, default_width=50, default_height=40)
    assert center_x == pytest.approx(60)
    assert center_y == pytest.approx(50)
    assert width == pytest.approx(100)
    assert height == pytest.approx(60)


def test_ellipse_box_shift_keeps_a_circle():
    center_x, center_y, width, height = ellipse_box(0, 0, 40, 100, constrain=True)
    assert width == pytest.approx(height)
    assert width == pytest.approx(100)
    assert center_x == pytest.approx(50)
    assert center_y == pytest.approx(50)
