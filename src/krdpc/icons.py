"""Theme icons that stay visible on any colour scheme.

Breeze's action icons are one dark colour, and KDE's own icon library recolours
them to match the theme. A Python app gets plain Qt, which does not, so on a dark
theme they come out dark on dark. Here they are painted in the palette's text
colour instead.

Without a desktop theme for Qt to follow (WSL, desktops without KDE) Qt looks only
in `hicolor`, which has none of these icons; an installed theme fills the gaps.
"""

from PySide6.QtCore import QFile, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap

SIZES = (16, 22, 32, 48)

# Icon themes that have krdpc's icons, tried in this order when the desktop names none.
FALLBACK_THEMES = ("breeze", "Adwaita")


def installed_theme(names=FALLBACK_THEMES) -> str:
    """The first of `names` installed on this system, or "" if none is."""
    for name in names:
        for path in QIcon.themeSearchPaths():
            if QFile.exists(f"{path}/{name}/index.theme"):
                return name
    return ""


def fill_missing_icons() -> None:
    """Take icons the desktop's theme lacks from an installed theme (Breeze, then Adwaita).

    Only Qt's fallback theme changes, so the desktop's own icon theme still comes first.
    A fallback the desktop already set (anything but hicolor) is kept.
    """
    if QIcon.fallbackThemeName() not in ("", "hicolor"):
        return
    name = installed_theme()
    if name:
        QIcon.setFallbackThemeName(name)


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
