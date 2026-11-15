# Annotate

A small desktop editor for pointing at things in a picture. Open an image, drop arrows and short notes on it, and export a flattened PNG or JPEG.

Annotations are real objects: select them, drag them, and use the handles to resize or rotate.

## Run

Python 3.10 or newer.

```bash
python -m pip install -r requirements.txt
python main.py
```

You can also pass an image path: `python main.py photo.png`.

## Use

| Action | How |
| --- | --- |
| Open | File → Open, or drop a PNG, JPG/JPEG, BMP, or WebP onto the window |
| Text | Text tool (T), then click the image. Double-click existing text to edit it. |
| Arrow | Arrow tool (A). Click to drop one, or drag to aim it. |
| Move | Select tool (V), then drag. Arrow keys nudge the selection; Shift nudges by 10 px. |
| Text size | Font box, the corner handle, or Ctrl+wheel while the pointer is over the selected text |
| Arrow length and thickness | Length and Thick boxes, or the handles on the tip and the side of the shaft |
| Rotate | Angle box, or the round handle above the arrow. Hold Shift to snap to 15°. |
| Color | Black, White, or Green. The choice applies to the selection and to the next object. |
| Outline | Thin contrasting edge so marks stay readable. On by default. |
| View zoom | Ctrl+wheel over empty canvas, or Zoom in / Zoom out. Fit is Ctrl+0. Actual pixels is Ctrl+1. Zoom does not change the file. |
| Resize the image | File → Resize image (Ctrl+Shift+R). Set pixels or a percent of the original size. Keep aspect ratio is on by default. Annotations scale with the picture. |
| Delete | Delete or Backspace |
| Undo / redo | Ctrl+Z, Ctrl+Y (or Ctrl+Shift+Z) |
| Export | File → Export (Ctrl+E). PNG or JPEG at the image’s real pixel size, with no selection handles. JPEG asks for a quality setting. |

While you are typing in a text box, Ctrl+Z undoes the typing. Click away, then Ctrl+Z undoes the annotation itself.

## Tests

```bash
python -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest
```

On Windows PowerShell:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest
```

## Build a Windows app

PyInstaller builds an executable for the operating system it runs on, so this step is done on Windows.

```bat
build.bat
```

That installs the app and PyInstaller, then runs `annotate.spec`. The result is a single file: `dist\Annotate.exe`.

A one-folder build, which starts a little faster, is:

```bat
python -m PyInstaller --noconfirm --clean --windowed --name Annotate main.py
```

The program is `dist\Annotate\Annotate.exe`.

## Layout

```
main.py                 starts the app
annotate/               window, scene, text and arrow items, undo
tests/                  headless tests
annotate.spec           PyInstaller one-file spec
build.bat               Windows build script
```

## Limits

- There is no separate project file. Annotations live until you export; the export is a flat image.
- Colors are black, white, and green.
- Resizing the image keeps a copy of the bitmap on the undo stack, so a very large photo can use a lot of memory. The resize dialog caps a side at 16000 pixels, or the current size if that is already larger.
- The `.exe` has to be built on Windows.
