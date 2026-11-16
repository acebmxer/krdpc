"""krdpc's colours: the desktop's own, or a fixed light or dark set.

Without a desktop theme for Qt to follow (WSL, desktops without KDE) Qt falls back
to its plain light colours; Light and Dark let the user choose instead.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

# (stored value, label)
THEMES = (
    ("system", "Follow system"),
    ("light", "Light"),
    ("dark", "Dark"),
)

Role = QPalette.ColorRole
Group = QPalette.ColorGroup

# Breeze's light and dark colours, so a fixed choice still looks like KDE.
_COLOURS = {
    "light": {
        Role.Window: "#eff0f1",
        Role.WindowText: "#232629",
        Role.Base: "#ffffff",
        Role.AlternateBase: "#f7f7f7",
        Role.Button: "#fcfcfc",
        Role.ButtonText: "#232629",
        Role.Text: "#232629",
        Role.BrightText: "#ffffff",
        Role.ToolTipBase: "#f7f7f7",
        Role.ToolTipText: "#232629",
        Role.Highlight: "#3daee9",
        Role.HighlightedText: "#ffffff",
        Role.Link: "#2980b9",
        Role.LinkVisited: "#9b59b6",
        Role.PlaceholderText: "#707d8a",
    },
    "dark": {
        Role.Window: "#202326",
        Role.WindowText: "#fcfcfc",
        Role.Base: "#141618",
        Role.AlternateBase: "#1d1f22",
        Role.Button: "#292c30",
        Role.ButtonText: "#fcfcfc",
        Role.Text: "#fcfcfc",
        Role.BrightText: "#ffffff",
        Role.ToolTipBase: "#292c30",
        Role.ToolTipText: "#fcfcfc",
        Role.Highlight: "#3daee9",
        Role.HighlightedText: "#fcfcfc",
        Role.Link: "#1d99f3",
        Role.LinkVisited: "#9b59b6",
        Role.PlaceholderText: "#a1a9b1",
    },
}
_DISABLED_TEXT = {"light": "#a0a1a3", "dark": "#6e7175"}
_SCHEMES = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}


def palette(name: str) -> QPalette:
    """The fixed light or dark palette."""
    colours = _COLOURS[name]
    result = QPalette(QColor(colours[Role.Button]), QColor(colours[Role.Window]))
    for role, colour in colours.items():
        result.setColor(role, QColor(colour))
    disabled = QColor(_DISABLED_TEXT[name])
    for role in (Role.WindowText, Role.Text, Role.ButtonText, Role.HighlightedText):
        result.setColor(Group.Disabled, role, disabled)
    return result


def apply(name: str) -> None:
    """Use the chosen colours now; "system" (or anything unknown) gives the desktop's back."""
    app = QGuiApplication.instance()
    if app is None:
        return
    hints = app.styleHints()
    if name in _COLOURS:
        if hasattr(hints, "setColorScheme"):  # Qt 6.8 and newer
            hints.setColorScheme(_SCHEMES[name])
        app.setPalette(palette(name))
        return
    if hasattr(hints, "unsetColorScheme"):
        hints.unsetColorScheme()
    # An empty palette hands the colours back to the desktop, and keeps following its changes.
    app.setPalette(QPalette())
