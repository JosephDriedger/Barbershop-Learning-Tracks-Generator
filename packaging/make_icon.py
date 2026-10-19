"""Draw BLT's application icon (original artwork, drawn in code) and write ``blt.ico``.

Four note heads on stems, one for each voice, on a rounded blue square. The ICO holds PNG images
of 16 to 256 pixels (supported since Windows Vista); ``blt.icns`` (macOS) holds PNG images of 16 to
1024 pixels. Run: ``python packaging/make_icon.py``.
"""

import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QImageWriter, QPainter, QPen

SIZES = (16, 24, 32, 48, 64, 128, 256)
# the PNG-carrying icon types of an .icns file: type code -> pixel size
ICNS_TYPES = (
    (b"icp4", 16),
    (b"icp5", 32),
    (b"icp6", 64),
    (b"ic07", 128),
    (b"ic08", 256),
    (b"ic09", 512),
    (b"ic10", 1024),
)


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    unit = size / 100.0
    painter.setBrush(QBrush(QColor("#1f4e8c")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(4 * unit, 4 * unit, 92 * unit, 92 * unit), 18 * unit, 18 * unit)
    painter.setBrush(QBrush(QColor("#f4f7fb")))
    pen = QPen(QColor("#f4f7fb"))
    pen.setWidthF(max(1.0, 3.2 * unit))
    # four voices: noteheads at different heights (Bass lowest), stems up
    heads = ((24, 62), (41, 46), (58, 56), (75, 70))
    for x, y in heads:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(x * unit, y * unit), 7.5 * unit, 5.5 * unit)
        painter.setPen(pen)
        painter.drawLine(
            QPointF((x + 6.6) * unit, (y - 1) * unit), QPointF((x + 6.6) * unit, (y - 30) * unit)
        )
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    QImageWriter(buffer, QByteArray(b"PNG")).write(image)
    buffer.close()
    return bytes(data.data())


def main() -> None:
    app = QGuiApplication([])  # noqa: F841 - needed for QImage text/painting setup
    pngs = [png_bytes(draw(size)) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries = b""
    for size, png in zip(SIZES, pngs, strict=True):
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,
            0 if size >= 256 else size,
            0,
            0,
            1,
            32,
            len(png),
            offset,
        )
        offset += len(png)
    target = Path(__file__).with_name("blt.ico")
    target.write_bytes(header + entries + b"".join(pngs))
    print(f"wrote {target} ({target.stat().st_size} bytes)")
    chunks = b""
    for code, size in ICNS_TYPES:
        png = png_bytes(draw(size))
        chunks += code + struct.pack(">I", 8 + len(png)) + png
    icns = Path(__file__).with_name("blt.icns")
    icns.write_bytes(b"icns" + struct.pack(">I", 8 + len(chunks)) + chunks)
    print(f"wrote {icns} ({icns.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
