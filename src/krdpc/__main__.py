"""Start krdpc: `python -m krdpc` or the `krdpc` command."""

import signal
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from krdpc import __version__
from krdpc.icons import fill_missing_icons
from krdpc.mainwindow import MainWindow
from krdpc.store import ProfileStore


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("krdpc")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("krdpc")
    fill_missing_icons()
    # The installed icon if there is one, otherwise the copy shipped with the code.
    app.setWindowIcon(QIcon.fromTheme("krdpc", QIcon(str(Path(__file__).with_name("krdpc.svg")))))
    # With the tray icon the app must outlive its window; closing for real quits explicitly.
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(ProfileStore())
    if not window.starts_hidden():
        window.show()
    window.check_for_updates_at_start()

    # Ctrl+C in the terminal: end the connections and quit. Python only looks at
    # signals when it is running, so a timer wakes it up now and then.
    def interrupt(*_args) -> None:
        window.launcher.stop_all()
        app.quit()

    signal.signal(signal.SIGINT, interrupt)
    wake = QTimer()
    wake.timeout.connect(lambda: None)
    wake.start(100)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
