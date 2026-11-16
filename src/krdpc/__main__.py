"""Start krdpc: `python -m krdpc` or the `krdpc` command."""

import signal
import sys

from PySide6.QtCore import QTimer
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
