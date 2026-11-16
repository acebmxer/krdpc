"""Start krdpc: `python -m krdpc` or the `krdpc` command."""

import sys

from PySide6.QtWidgets import QApplication

from krdpc import __version__
from krdpc.mainwindow import MainWindow
from krdpc.store import ProfileStore


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("krdpc")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("krdpc")
    window = MainWindow(ProfileStore())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
