"""App-wide settings, kept in `krdpc.conf` next to the computers."""

import dataclasses
import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

from krdpc.theme import THEMES

# (stored value, label, pixels)
ICON_SIZES = (
    ("small", "Small (16 px)", 16),
    ("medium", "Medium (24 px)", 24),
    ("large", "Large (32 px)", 32),
)


@dataclass
class Preferences:
    icon_size: str = "medium"
    confirm_delete: bool = True
    remember_window: bool = True
    xfreerdp_path: str = ""  # empty: find xfreerdp (or sdl-freerdp without X11) on the PATH
    show_tray: bool = False
    close_to_tray: bool = False  # only with the tray icon
    start_minimised: bool = False  # only with the tray icon
    start_at_login: bool = False
    theme: str = "system"  # "system", "light" or "dark"; see krdpc.theme
    check_updates: bool = True  # look for a newer release when krdpc starts
    include_betas: bool = False  # offer beta (pre-release) versions too

    def normalised(self) -> "Preferences":
        """Closing to the tray and starting hidden make no sense without the tray icon."""
        if self.show_tray:
            return self
        return dataclasses.replace(self, close_to_tray=False, start_minimised=False)

    def icon_pixels(self) -> int:
        return {name: pixels for name, _label, pixels in ICON_SIZES}.get(self.icon_size, 24)


def is_program(path: str) -> bool:
    """True if `path` is a file this user may run."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _as_bool(value, default: bool) -> bool:
    """A stored yes/no; anything else is read as the default."""
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


class PreferencesStore:
    def __init__(self, directory: Path) -> None:
        self._path = Path(directory) / "krdpc.conf"

    def _settings(self) -> QSettings:
        return QSettings(str(self._path), QSettings.Format.IniFormat)

    def load(self) -> Preferences:
        settings = self._settings()
        defaults = Preferences()
        size = str(settings.value("icon_size", defaults.icon_size))
        if size not in {name for name, _label, _pixels in ICON_SIZES}:
            size = defaults.icon_size
        theme = str(settings.value("theme", defaults.theme))
        if theme not in {name for name, _label in THEMES}:
            theme = defaults.theme
        return Preferences(
            icon_size=size,
            confirm_delete=_as_bool(settings.value("confirm_delete"), defaults.confirm_delete),
            remember_window=_as_bool(settings.value("remember_window"), defaults.remember_window),
            xfreerdp_path=str(settings.value("xfreerdp_path", "")).strip(),
            show_tray=_as_bool(settings.value("show_tray"), defaults.show_tray),
            close_to_tray=_as_bool(settings.value("close_to_tray"), defaults.close_to_tray),
            start_minimised=_as_bool(settings.value("start_minimised"), defaults.start_minimised),
            start_at_login=_as_bool(settings.value("start_at_login"), defaults.start_at_login),
            theme=theme,
            check_updates=_as_bool(settings.value("check_updates"), defaults.check_updates),
            include_betas=_as_bool(settings.value("include_betas"), defaults.include_betas),
        ).normalised()

    def save(self, preferences: Preferences) -> None:
        settings = self._settings()
        settings.setValue("icon_size", preferences.icon_size)
        settings.setValue("confirm_delete", preferences.confirm_delete)
        settings.setValue("remember_window", preferences.remember_window)
        settings.setValue("xfreerdp_path", preferences.xfreerdp_path)
        settings.setValue("show_tray", preferences.show_tray)
        settings.setValue("close_to_tray", preferences.close_to_tray)
        settings.setValue("start_minimised", preferences.start_minimised)
        settings.setValue("start_at_login", preferences.start_at_login)
        settings.setValue("theme", preferences.theme)
        settings.setValue("check_updates", preferences.check_updates)
        settings.setValue("include_betas", preferences.include_betas)
        settings.sync()

    def save_window(self, geometry: QByteArray, columns: QByteArray) -> None:
        settings = self._settings()
        settings.setValue("window/geometry", geometry)
        settings.setValue("window/columns", columns)
        settings.sync()

    def window(self) -> tuple[QByteArray, QByteArray] | None:
        """The remembered window geometry and column layout, or None if there are none."""
        settings = self._settings()
        geometry = settings.value("window/geometry")
        columns = settings.value("window/columns")
        if not isinstance(geometry, QByteArray) or not isinstance(columns, QByteArray):
            return None
        return geometry, columns
