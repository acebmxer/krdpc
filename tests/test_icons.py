from PySide6.QtGui import QColor, QIcon, QPalette, QPixmap

from krdpc.icons import symbolic_icon, tint


def dark_square():
    pixmap = QPixmap(22, 22)
    pixmap.fill(QColor("#232629"))
    return QIcon(pixmap)


def test_tint_paints_visible_pixels_in_the_given_colour(qapp):
    pixmaps = tint(dark_square(), QColor("#eff0f1"))
    assert pixmaps
    assert pixmaps[0].toImage().pixelColor(5, 5).name() == "#eff0f1"


def test_tint_keeps_transparent_pixels_transparent(qapp):
    pixmap = QPixmap(22, 22)
    pixmap.fill(QColor(0, 0, 0, 0))
    assert tint(QIcon(pixmap), QColor("white"))[0].toImage().pixelColor(5, 5).alpha() == 0


def test_missing_icon_gives_a_null_icon(qapp):
    assert symbolic_icon("no-such-icon-name", QPalette()).isNull()


def test_symbolic_icon_uses_the_palette_colour(qapp, monkeypatch):
    monkeypatch.setattr(QIcon, "fromTheme", lambda name, *a: dark_square())
    palette = QPalette()
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor("#eff0f1"))
    icon = symbolic_icon("anything", palette)
    assert icon.pixmap(22, 22).toImage().pixelColor(5, 5).name() == "#eff0f1"
