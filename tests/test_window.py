from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from annotate import APP_NAME
from annotate.items import AnnotationTextItem
from annotate.main_window import MainWindow


def _save_image(path, width=140, height=90):
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#556677"))
    assert image.save(str(path))


def test_window_opens_image_and_places_marks(qapp, tmp_path):
    path = tmp_path / "plate.png"
    _save_image(path)
    window = MainWindow()
    assert window.windowTitle() == APP_NAME
    window.resize(1000, 700)
    window.show()
    qapp.processEvents()
    assert window.open_path(str(path), confirm=False)
    assert window.scene.image_size() == (140, 90)
    assert window.windowTitle() == f"{APP_NAME} — plate.png"
    assert window.about_action.text() == f"About {APP_NAME}"

    window.view.place_text.emit(QPointF(18, 16))
    qapp.processEvents()
    texts = [item for item in window.scene.annotation_items() if isinstance(item, AnnotationTextItem)]
    assert len(texts) == 1
    assert texts[0].is_editing()
    assert window.view.tool() == "select"

    window.view.place_arrow.emit(QPointF(30, 60), QPointF(110, 40))
    qapp.processEvents()
    assert len(window.scene.annotation_items()) == 2
    assert window.view.tool() == "select"
    window.close()
    qapp.processEvents()


def test_ctrl_z_while_typing_does_not_remove_the_text_item(qapp, tmp_path):
    path = tmp_path / "plate.png"
    _save_image(path)
    window = MainWindow()
    window.resize(900, 640)
    window.show()
    qapp.processEvents()
    window.open_path(str(path), confirm=False)
    window.view.place_text.emit(QPointF(12, 12))
    qapp.processEvents()
    text = window.scene.annotation_items()[0]
    assert text.is_editing()
    cursor = text.textCursor()
    from PySide6.QtGui import QTextCursor

    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText("!")
    text.setTextCursor(cursor)
    assert text.toPlainText().endswith("!")
    stack_index = window.scene.undo_stack.index()
    window.view.setFocus()
    qapp.processEvents()
    QTest.keyClick(window.view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    qapp.processEvents()
    assert text.scene() is window.scene
    assert window.scene.undo_stack.index() == stack_index
    assert not text.toPlainText().endswith("!")
    window.close()
    qapp.processEvents()
    # Keep the application object referenced so the fixture stays alive.
    assert QApplication.instance() is qapp
