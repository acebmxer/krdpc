"""Starting krdpc when the user logs in: a `.desktop` file in the autostart folder."""

import os
import shutil
from pathlib import Path


def autostart_file() -> Path:
    """`$XDG_CONFIG_HOME/autostart/krdpc.desktop`."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / "krdpc.desktop"


def _exec_line() -> str:
    command = shutil.which("krdpc") or "krdpc"
    return f'"{command}"' if " " in command else command


def entry_text() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=krdpc\n"
        "Comment=Open your saved remote computers with FreeRDP\n"
        f"Exec={_exec_line()}\n"
        "Icon=krdpc\n"
        "Terminal=false\n"
        "X-KDE-autostart-after=panel\n"
    )


def is_enabled() -> bool:
    return autostart_file().is_file()


def set_enabled(enabled: bool) -> None:
    """Add or remove krdpc from the programs started at login. Raises OSError on failure."""
    path = autostart_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(entry_text(), encoding="utf-8")
    os.replace(temporary, path)
