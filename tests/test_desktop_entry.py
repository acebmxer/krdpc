import configparser
from pathlib import Path

from PySide6.QtGui import QIcon

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "data" / "krdpc.desktop"
ICON = ROOT / "src" / "krdpc" / "krdpc.svg"


def read_entry():
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(ENTRY, encoding="utf-8")
    return parser["Desktop Entry"]


def test_the_entry_starts_the_installed_command():
    entry = read_entry()
    assert entry["Type"] == "Application"
    assert entry["Exec"] == "krdpc"
    assert entry["Terminal"] == "false"
    assert entry["Name"] == "krdpc"


def test_the_entry_is_filed_under_network():
    categories = read_entry()["Categories"].split(";")
    assert {"Network", "RemoteAccess"} <= set(categories)
    assert read_entry()["Categories"].endswith(";")


def test_the_entry_and_the_window_agree_on_the_name():
    # The window reports this name to the desktop (QGuiApplication.setDesktopFileName).
    assert 'setDesktopFileName("krdpc")' in (ROOT / "src" / "krdpc" / "__main__.py").read_text()
    assert read_entry()["Icon"] == ICON.stem
    assert ENTRY.stem == "krdpc"


def test_the_icon_loads(qapp):
    assert ICON.is_file()
    assert not QIcon(str(ICON)).isNull()
    assert not QIcon(str(ICON)).pixmap(32, 32).isNull()


def test_the_command_in_the_entry_exists_in_the_package_metadata():
    text = (ROOT / "pyproject.toml").read_text()
    assert 'krdpc = "krdpc.__main__:main"' in text
    assert 'krdpc = ["krdpc.svg"]' in text
