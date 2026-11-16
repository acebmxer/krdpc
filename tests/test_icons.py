from PySide6.QtGui import QColor, QIcon, QPalette, QPixmap

from krdpc.icons import fill_missing_icons, installed_theme, symbolic_icon, tint


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


class FallbackTheme:
    """Stands in for Qt's fallback icon theme, so a test never changes the real one."""

    def __init__(self, monkeypatch, name):
        self.name = name
        monkeypatch.setattr(QIcon, "fallbackThemeName", lambda: self.name)
        monkeypatch.setattr(QIcon, "setFallbackThemeName", lambda name: setattr(self, "name", name))


def icon_themes(monkeypatch, tmp_path, *names):
    for name in names:
        (tmp_path / name).mkdir()
        (tmp_path / name / "index.theme").write_text("[Icon Theme]\n")
    monkeypatch.setattr(QIcon, "themeSearchPaths", lambda: [str(tmp_path)])


def test_installed_theme_prefers_breeze(qapp, monkeypatch, tmp_path):
    icon_themes(monkeypatch, tmp_path, "Adwaita", "breeze")
    assert installed_theme() == "breeze"


def test_installed_theme_falls_back_to_adwaita(qapp, monkeypatch, tmp_path):
    icon_themes(monkeypatch, tmp_path, "Adwaita")
    assert installed_theme() == "Adwaita"


def test_installed_theme_ignores_a_folder_without_index_theme(qapp, monkeypatch, tmp_path):
    icon_themes(monkeypatch, tmp_path)
    (tmp_path / "breeze").mkdir()
    assert installed_theme() == ""


def test_without_a_desktop_theme_breeze_fills_the_gaps(qapp, monkeypatch, tmp_path):
    icon_themes(monkeypatch, tmp_path, "breeze")
    fallback = FallbackTheme(monkeypatch, "hicolor")
    fill_missing_icons()
    assert fallback.name == "breeze"


def test_a_fallback_the_desktop_set_is_kept(qapp, monkeypatch, tmp_path):
    icon_themes(monkeypatch, tmp_path, "breeze")
    fallback = FallbackTheme(monkeypatch, "oxygen")
    fill_missing_icons()
    assert fallback.name == "oxygen"


def test_with_no_theme_installed_the_fallback_stays(qapp, monkeypatch, tmp_path):
    icon_themes(monkeypatch, tmp_path)
    fallback = FallbackTheme(monkeypatch, "hicolor")
    fill_missing_icons()
    assert fallback.name == "hicolor"
