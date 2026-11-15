import os
import random

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from annotate.dialogs import ResizeImageDialog
from annotate.items import AnnotationTextItem, ArrowItem
from annotate.scene import AnnotationScene
from annotate.view import AnnotationView, is_image_path


def solid(width, height, color="#ffffff") -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.setDevicePixelRatio(1.0)
    image.fill(QColor(color))
    return image


def scene_with(width=240, height=160, color="#ffffff") -> AnnotationScene:
    scene = AnnotationScene()
    scene.replace_image(solid(width, height, color))
    return scene


def send_mouse(item, kind, scene_pos, modifiers=Qt.KeyboardModifier.NoModifier, buttons_down=True):
    event = QGraphicsSceneMouseEvent(kind)
    event.setScenePos(QPointF(scene_pos))
    event.setPos(item.mapFromScene(QPointF(scene_pos)))
    event.setButton(Qt.MouseButton.LeftButton)
    event.setButtons(Qt.MouseButton.LeftButton if buttons_down else Qt.MouseButton.NoButton)
    event.setModifiers(modifiers)
    if kind == QEvent.Type.GraphicsSceneMousePress:
        item.mousePressEvent(event)
    elif kind == QEvent.Type.GraphicsSceneMouseMove:
        item.mouseMoveEvent(event)
    else:
        item.mouseReleaseEvent(event)


def test_image_extensions():
    assert is_image_path("photo.JPG")
    assert is_image_path("scan.jpeg")
    assert is_image_path("icon.png")
    assert is_image_path("shot.bmp")
    assert not is_image_path("notes.txt")


def test_load_png_jpg_and_bmp(tmp_path):
    for fmt, name in (("PNG", "a.png"), ("JPEG", "b.jpg"), ("BMP", "c.bmp")):
        path = tmp_path / name
        assert solid(30, 20, "#224466").save(str(path), fmt)
        scene = AnnotationScene()
        assert scene.load_image(str(path))
        assert scene.image_size() == (30, 20)


def test_reject_unreadable_image(tmp_path):
    path = tmp_path / "nope.png"
    path.write_text("not an image", encoding="utf-8")
    scene = AnnotationScene()
    assert scene.load_image(str(path)) is False
    assert not scene.has_image()


def test_add_text_and_arrow_undo_redo():
    scene = scene_with()
    text = scene.add_text(QPointF(12, 16), text="Hello")
    arrow = scene.add_arrow(QPointF(80, 60), length=90, thickness=12, rotation=0)
    assert scene.annotation_items() == [text, arrow]
    scene.undo_stack.undo()
    assert scene.annotation_items() == [text]
    scene.undo_stack.undo()
    assert scene.annotation_items() == []
    scene.undo_stack.redo()
    scene.undo_stack.redo()
    assert len(scene.annotation_items()) == 2


def test_color_outline_and_font_undo():
    scene = scene_with()
    text = scene.add_text(QPointF(8, 8), color="#000000", outline=False)
    text.setSelected(True)
    scene.apply_color("#00a33a")
    scene.apply_outline(True)
    scene.apply_font_size(48)
    assert text.color().name().lower() == "#00a33a"
    assert text.outline_enabled() is True
    assert text.font_size() == pytest.approx(48)
    scene.undo_stack.undo()
    assert text.font_size() == pytest.approx(32)
    scene.undo_stack.undo()
    assert text.outline_enabled() is False
    scene.undo_stack.undo()
    assert text.color().name().lower() == "#000000"


def test_wheel_font_changes_merge_into_one_undo():
    scene = scene_with()
    text = scene.add_text(QPointF(4, 4))
    start = text.font_size()
    text.wheel_resize(1)
    text.wheel_resize(1)
    assert text.font_size() == pytest.approx(start + 4)
    assert scene.undo_stack.index() == 2
    scene.undo_stack.undo()
    assert text.font_size() == pytest.approx(start)
    assert len(scene.annotation_items()) == 1


def test_delete_undo_restores_the_item():
    scene = scene_with()
    arrow = scene.add_arrow(QPointF(40, 40))
    arrow.setSelected(True)
    scene.delete_selected()
    assert scene.annotation_items() == []
    scene.undo_stack.undo()
    assert scene.annotation_items() == [arrow]


def test_text_edit_undo():
    scene = scene_with()
    view = AnnotationView(scene)
    view.resize(320, 200)
    view.show()
    text = scene.add_text(QPointF(20, 20), text="Text")
    text.begin_edit()
    text.setPlainText("Hello")
    text.end_edit()
    assert text.toPlainText() == "Hello"
    scene.undo_stack.undo()
    assert text.toPlainText() == "Text"
    view.close()


def test_arrow_points_along_the_drag():
    scene = scene_with(300, 200)
    right = scene.add_arrow_between(QPointF(10, 40), QPointF(110, 40))
    tip = right.mapToScene(QPointF(right.length() / 2.0, 0))
    assert tip.x() == pytest.approx(110, abs=1.5)
    assert tip.y() == pytest.approx(40, abs=1.5)

    down = scene.add_arrow_between(QPointF(50, 10), QPointF(50, 130))
    tip = down.mapToScene(QPointF(down.length() / 2.0, 0))
    assert tip.x() == pytest.approx(50, abs=1.5)
    assert tip.y() == pytest.approx(130, abs=1.5)


def test_length_handle_math_keeps_the_tail_put():
    scene = scene_with()
    arrow = scene.add_arrow(QPointF(100, 80), length=100, thickness=10, rotation=0)
    tail_before = arrow.mapToScene(QPointF(-50, 0))
    arrow.set_length(160, anchor="tail")
    tail_after = arrow.mapToScene(QPointF(-80, 0))
    assert tail_after.x() == pytest.approx(tail_before.x(), abs=0.6)
    assert tail_after.y() == pytest.approx(tail_before.y(), abs=0.6)
    assert arrow.length() == pytest.approx(160)


def test_drag_moves_selected_group_and_undoes_together():
    scene = scene_with()
    arrow = scene.add_arrow(QPointF(80, 70), length=60, thickness=16, rotation=0)
    text = scene.add_text(QPointF(20, 20), text="Note")
    arrow.setSelected(True)
    text.setSelected(True)
    origin_arrow = QPointF(arrow.pos())
    origin_text = QPointF(text.pos())
    send_mouse(arrow, QEvent.Type.GraphicsSceneMousePress, arrow.pos())
    send_mouse(arrow, QEvent.Type.GraphicsSceneMouseMove, arrow.pos() + QPointF(30, -12))
    send_mouse(
        arrow,
        QEvent.Type.GraphicsSceneMouseRelease,
        arrow.pos() + QPointF(30, -12),
        buttons_down=False,
    )
    assert arrow.pos().x() == pytest.approx(origin_arrow.x() + 30, abs=0.6)
    assert arrow.pos().y() == pytest.approx(origin_arrow.y() - 12, abs=0.6)
    assert text.pos().x() == pytest.approx(origin_text.x() + 30, abs=0.6)
    assert text.pos().y() == pytest.approx(origin_text.y() - 12, abs=0.6)
    scene.undo_stack.undo()
    assert arrow.pos().x() == pytest.approx(origin_arrow.x(), abs=0.6)
    assert text.pos().x() == pytest.approx(origin_text.x(), abs=0.6)


def test_shift_drag_on_rotation_handle_snaps():
    scene = scene_with(360, 280)
    arrow = scene.add_arrow(QPointF(180, 140), length=80, thickness=14, rotation=10)
    arrow.setSelected(True)
    handle = arrow.mapToScene(arrow._handle_centers()["rotate"])
    send_mouse(arrow, QEvent.Type.GraphicsSceneMousePress, handle)
    target = QPointF(arrow.pos().x() + 90, arrow.pos().y())
    send_mouse(
        arrow,
        QEvent.Type.GraphicsSceneMouseMove,
        target,
        modifiers=Qt.KeyboardModifier.ShiftModifier,
    )
    send_mouse(
        arrow,
        QEvent.Type.GraphicsSceneMouseRelease,
        target,
        modifiers=Qt.KeyboardModifier.ShiftModifier,
        buttons_down=False,
    )
    assert arrow.rotation() % 15 == pytest.approx(0, abs=0.05)
    assert abs(arrow.rotation() - 10) > 1


def test_resize_scales_annotations_and_undo_restores_pixels():
    scene = scene_with(200, 100)
    arrow = scene.add_arrow(QPointF(100, 40), length=80, thickness=10, rotation=0)
    text = scene.add_text(QPointF(20, 10), font_size=32)
    assert scene.resize_image(100, 50)
    assert scene.image_size() == (100, 50)
    assert arrow.pos().x() == pytest.approx(50, abs=0.8)
    assert arrow.pos().y() == pytest.approx(20, abs=0.8)
    assert arrow.length() == pytest.approx(40, abs=0.8)
    assert arrow.thickness() == pytest.approx(5, abs=0.3)
    assert arrow.rotation() == pytest.approx(0, abs=0.8)
    assert text.pos().x() == pytest.approx(10, abs=0.8)
    assert text.font_size() == pytest.approx(16, abs=0.4)
    scene.undo_stack.undo()
    assert scene.image_size() == (200, 100)
    assert arrow.pos().x() == pytest.approx(100, abs=0.8)
    assert arrow.length() == pytest.approx(80, abs=0.8)
    assert text.font_size() == pytest.approx(32, abs=0.4)


def test_view_zoom_does_not_resample_the_image():
    scene = scene_with(200, 100)
    view = AnnotationView(scene)
    view.resize(480, 320)
    before = scene.image_size()
    view.zoom_by(2.5)
    assert scene.image_size() == before
    assert view.zoom_factor() == pytest.approx(2.5, rel=0.02)
    view.actual_size()
    assert view.zoom_factor() == pytest.approx(1.0, abs=0.02)
    assert scene.image_size() == before


def test_export_matches_image_pixels_and_hides_handles(tmp_path):
    scene = scene_with(240, 160, "#ffffff")
    arrow = scene.add_arrow(
        QPointF(120, 80),
        length=120,
        thickness=30,
        rotation=0,
        color="#00a33a",
        outline=False,
    )
    arrow.setSelected(True)
    text = scene.add_text(QPointF(16, 16), text="HELLO", font_size=42, color="#ffffff", outline=True)
    scene.replace_image(solid(240, 160, "#203040"))
    # replace_image clears annotations; rebuild on the dark plate so white text is visible.
    arrow = scene.add_arrow(
        QPointF(120, 80),
        length=120,
        thickness=30,
        rotation=0,
        color="#00a33a",
        outline=False,
    )
    text = scene.add_text(QPointF(16, 18), text="HELLO", font_size=42, color="#ffffff", outline=False)
    arrow.setSelected(True)
    text.setSelected(True)

    exported = scene.render_image()
    assert exported.size() == scene.image().size()
    assert arrow.isSelected() and text.isSelected()
    center = exported.pixelColor(120, 80)
    assert center.green() > 120
    assert center.green() > center.red() + 40

    light = 0
    for y in range(10, 90):
        for x in range(10, 180):
            pixel = exported.pixelColor(x, y)
            if pixel.red() > 200 and pixel.green() > 200 and pixel.blue() > 200:
                light += 1
    assert light > 20

    chrome = QImage(240, 160, QImage.Format.Format_ARGB32)
    chrome.fill(QColor("#203040"))
    painter = QPainter(chrome)
    scene.exporting = False
    scene.render(painter, QRectF_scene(), QRectF_scene())
    painter.end()
    assert images_differ(exported, chrome)

    png = tmp_path / "out.png"
    jpg = tmp_path / "out.jpg"
    assert scene.export_file(str(png))
    assert scene.export_file(str(jpg), 90)
    assert QImage(str(png)).size() == exported.size()
    assert QImage(str(jpg)).size() == exported.size()


def test_jpeg_quality_changes_file_size(tmp_path):
    scene = AnnotationScene()
    image = QImage(160, 100, QImage.Format.Format_ARGB32)
    rng = random.Random(1)
    for y in range(image.height()):
        for x in range(image.width()):
            image.setPixelColor(x, y, QColor(rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    scene.replace_image(image)
    low = tmp_path / "low.jpg"
    high = tmp_path / "high.jpg"
    assert scene.export_file(str(low), 40)
    assert scene.export_file(str(high), 98)
    assert os.path.getsize(low) < os.path.getsize(high)


def test_resize_dialog_links_fields():
    dialog = ResizeImageDialog(1000, 500)
    dialog.width_px.setValue(500)
    assert dialog.result_size() == (500, 250)
    dialog.keep.setChecked(False)
    dialog.width_px.setValue(800)
    assert dialog.result_size() == (800, 250)
    percent = ResizeImageDialog(200, 100)
    percent.width_pct.setValue(50)
    assert percent.result_size() == (100, 50)


def QRectF_scene():
    from PySide6.QtCore import QRectF

    return QRectF(0, 0, 240, 160)


def images_differ(left: QImage, right: QImage) -> bool:
    if left.size() != right.size():
        return True
    for y in range(left.height()):
        for x in range(left.width()):
            if left.pixel(x, y) != right.pixel(x, y):
                return True
    return False
