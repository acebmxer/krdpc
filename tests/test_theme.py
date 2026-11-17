import pytest
from PySide6.QtGui import QPalette

from krdpc import theme

Role = QPalette.ColorRole


@pytest.fixture
def app(qapp):
    yield qapp
    theme.apply("system")  # every test hands the desktop's colours back


def window_colour(app):
    return app.palette().color(Role.Window).name()


def test_light_and_dark_change_the_colours(app):
    theme.apply("dark")
    assert window_colour(app) == "#202326"
    assert app.palette().color(Role.Text).name() == "#fcfcfc"
    theme.apply("light")
    assert window_colour(app) == "#eff0f1"
    assert app.palette().color(Role.Text).name() == "#232629"


def test_follow_system_gives_the_desktops_colours_back(app):
    desktop = window_colour(app)
    theme.apply("dark")
    assert window_colour(app) != desktop
    theme.apply("system")
    assert window_colour(app) == desktop
    assert app.palette().resolveMask() == 0  # not pinned: later desktop changes still show


def test_an_unknown_name_follows_the_system(app):
    desktop = window_colour(app)
    theme.apply("purple")
    assert window_colour(app) == desktop


def test_dark_text_is_readable_when_disabled(app):
    dark = theme.palette("dark")
    disabled = dark.color(QPalette.ColorGroup.Disabled, Role.Text)
    assert disabled.lightness() > dark.color(Role.Base).lightness()
