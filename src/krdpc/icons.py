"""Theme icons that stay visible on any colour scheme.

Breeze's action icons are one dark colour, and KDE's own icon library recolours
them to match the theme. A Python app gets plain Qt, which does not, so on a dark
theme they come out dark on dark. Here they are painted in the palette's text
colour instead.
"""

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap

SIZES = (16, 22, 32, 48)


def tint(icon: QIcon, color: QColor) -> list[QPixmap]:
    """The icon's pixmaps with every visible pixel painted in `color`."""
    pixmaps = []
    for size in SIZES:
        pixmap = icon.pixmap(QSize(size, size))
        if pixmap.isNull():
            continue
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), color)
        painter.end()
        pixmaps.append(pixmap)
    return pixmaps


def symbolic_icon(name: str, palette: QPalette, fallback: str = "") -> QIcon:
    """The theme icon `name` (or `fallback`) painted in the palette's button-text colour."""
    base = QIcon.fromTheme(name)
    if base.isNull() and fallback:
        base = QIcon.fromTheme(fallback)
    if base.isNull():
        return base
    result = QIcon()
    states = (
        (QIcon.Mode.Normal, QPalette.ColorGroup.Active),
        (QIcon.Mode.Active, QPalette.ColorGroup.Active),
        (QIcon.Mode.Selected, QPalette.ColorGroup.Active),
        (QIcon.Mode.Disabled, QPalette.ColorGroup.Disabled),
    )
    for mode, group in states:
        for pixmap in tint(base, palette.color(group, QPalette.ColorRole.ButtonText)):
            result.addPixmap(pixmap, mode)
    return result
