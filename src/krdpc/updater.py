"""The update boxes: check for a newer release, download it, install it, restart.

The network work runs on a background thread so the window never freezes; the
results come back to the window through Qt signals. Installing runs the package
manager through pkexec, which shows the desktop's own admin password box.
"""

import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget

from krdpc import updates
from krdpc.updates import Installed, Release, UpdateError

# Runs `work` away from the window, then calls `done(result)` or `failed(message)` on the
# window's thread. Tests swap in one that runs straight away.
Runner = Callable[[Callable[[], object], Callable[[object], None], Callable[[str], None]], None]


class _Relay(QObject):
    """Carries a background thread's result to the window's thread."""

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)


def run_in_thread(
    work: Callable[[], object], done: Callable[[object], None], failed: Callable[[str], None]
) -> None:
    relay = _Relay()
    relay.done.connect(done, Qt.ConnectionType.QueuedConnection)
    relay.failed.connect(failed, Qt.ConnectionType.QueuedConnection)

    def body() -> None:
        try:
            result = work()
        except UpdateError as error:
            relay.failed.emit(str(error))
        except Exception as error:  # noqa: BLE001 - never let a thread die silently
            relay.failed.emit(f"Something went wrong: {error}")
        else:
            relay.done.emit(result)

    # The relay must outlive the thread; it is kept by the closure until the thread ends.
    threading.Thread(target=body, name="krdpc-update", daemon=True).start()


class Updater(QObject):
    """Owned by the main window. `restart_requested` asks the window to restart krdpc."""

    restart_requested = Signal()
    # Emitted when a check started without asking finds a release (for the tray message).
    found_quietly = Signal(str)

    def __init__(
        self,
        parent: QWidget,
        include_betas: Callable[[], bool],
        runner: Runner = run_in_thread,
        folder: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._window = parent
        self._include_betas = include_betas
        self._run = runner
        self._folder = folder or updates.download_folder()
        self._busy = False
        self._cancel = threading.Event()
        self._progress: QProgressDialog | None = None
        self._process: QProcess | None = None
        self._relay = _Relay(self)
        self._relay.progress.connect(self._show_progress, Qt.ConnectionType.QueuedConnection)

    def busy(self) -> bool:
        return self._busy

    # ---- checking -----------------------------------------------------------

    def check(self, quiet: bool = False) -> None:
        """Look for a newer release. Quiet: say nothing unless one is found."""
        if self._busy:
            return
        self._busy = True
        include_betas = self._include_betas()
        self._run(
            lambda: updates.check(include_betas),
            lambda result: self._checked(result, quiet),
            lambda message: self._check_failed(message, quiet),
        )

    def _check_failed(self, message: str, quiet: bool) -> None:
        self._busy = False
        if not quiet:
            QMessageBox.warning(self._window, "Check for updates", message)

    def _checked(self, result: tuple[Installed, Release | None], quiet: bool) -> None:
        self._busy = False
        current, release = result
        if release is None:
            if not quiet:
                QMessageBox.information(
                    self._window,
                    "Check for updates",
                    f"krdpc {current.release} is the newest version.",
                )
            return
        if quiet and not self._window.isVisible():
            self.found_quietly.emit(release.version)
            return
        self.offer(current, release)

    def offer(self, current: Installed, release: Release) -> None:
        """Say a newer release is out and offer to install it."""
        kind = " (a beta)" if release.prerelease else ""
        box = QMessageBox(
            QMessageBox.Icon.Information,
            "Update available",
            f"krdpc {release.version}{kind} is available. You have {current.release}.",
            parent=self._window,
        )
        install = None
        if current.can_update_itself:
            box.setInformativeText(
                "krdpc downloads the new package, checks it, and installs it. "
                "Your desktop asks for your password first."
            )
            install = box.addButton("Update now", QMessageBox.ButtonRole.AcceptRole)
        else:
            box.setInformativeText(
                "This copy of krdpc was not installed from a package, so it cannot update "
                "itself. The Releases page has the new packages."
            )
        notes = box.addButton(
            "What's new" if install is not None else "Open the Releases page",
            QMessageBox.ButtonRole.HelpRole,
        )
        later = box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(install or later)
        box.exec()
        clicked = box.clickedButton()
        if clicked is notes:
            QDesktopServices.openUrl(QUrl(release.page))
        elif install is not None and clicked is install:
            self.update_to(current, release)

    # ---- downloading ---------------------------------------------------------

    def update_to(self, current: Installed, release: Release) -> None:
        if self._busy or current.package_format is None:
            return
        self._busy = True
        self._cancel.clear()
        package_format = current.package_format
        progress = QProgressDialog(
            f"Downloading krdpc {release.version}…", "Cancel", 0, 0, self._window
        )
        progress.setWindowTitle("Updating krdpc")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(self._cancel.set)
        progress.show()
        self._progress = progress

        folder, cancel, report = self._folder, self._cancel, self._relay.progress.emit
        self._run(
            lambda: updates.download(release, package_format, folder, report, cancel),
            lambda path: self._downloaded(Path(path), package_format, release),
            self._download_failed,
        )

    def _show_progress(self, done: int, total: int) -> None:
        if self._progress is None:
            return
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(min(done, total))

    def _close_progress(self) -> None:
        if self._progress is not None:
            # Closing a progress box counts as pressing its Cancel button: unhook that first.
            self._progress.canceled.disconnect(self._cancel.set)
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None

    def _download_failed(self, message: str) -> None:
        self._busy = False
        self._close_progress()
        if not self._cancel.is_set():
            QMessageBox.warning(self._window, "Update failed", message)

    # ---- installing -----------------------------------------------------------

    def _downloaded(self, path: Path, package_format: str, release: Release) -> None:
        if self._cancel.is_set():
            self._busy = False
            self._close_progress()
            path.unlink(missing_ok=True)
            return
        pkexec = updates.pkexec()
        if pkexec is None:
            self._busy = False
            self._close_progress()
            self._install_by_hand(
                package_format, path, "The program that asks for your password (pkexec) is missing."
            )
            return
        if self._progress is not None:
            self._progress.setLabelText(f"Installing krdpc {release.version}…")
            self._progress.setRange(0, 0)
            self._progress.setCancelButton(None)
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.finished.connect(
            lambda code, status: self._installed(
                process, code, status, path, package_format, release
            )
        )
        process.errorOccurred.connect(
            lambda error: self._install_did_not_start(process, error, path, package_format)
        )
        self._process = process
        process.start(pkexec, updates.install_command(package_format, path))

    def _install_did_not_start(
        self, process: QProcess, error: QProcess.ProcessError, path: Path, package_format: str
    ) -> None:
        if error != QProcess.ProcessError.FailedToStart:
            return
        self._busy = False
        self._close_progress()
        self._process = None
        self._install_by_hand(package_format, path, "The installer could not be started.")

    def _installed(
        self,
        process: QProcess,
        code: int,
        status: QProcess.ExitStatus,
        path: Path,
        package_format: str,
        release: Release,
    ) -> None:
        self._busy = False
        self._close_progress()
        self._process = None
        output = bytes(process.readAll()).decode(errors="replace").strip()
        if status == QProcess.ExitStatus.NormalExit and code == 0:
            path.unlink(missing_ok=True)
            self._ask_to_restart(release)
        elif code == updates.PKEXEC_DISMISSED:
            QMessageBox.information(
                self._window,
                "Not updated",
                f"krdpc was not updated. The downloaded package is kept in {path.parent}.",
            )
        elif code == updates.PKEXEC_REFUSED:
            self._install_by_hand(package_format, path, "Permission to install was not given.")
        else:
            self._install_by_hand(
                package_format, path, f"The installer stopped with code {code}.", output
            )

    def _install_by_hand(
        self, package_format: str, path: Path, why: str, details: str = ""
    ) -> None:
        command = updates.manual_command(package_format, path)
        box = QMessageBox(
            QMessageBox.Icon.Warning,
            "Update not installed",
            f"{why} The new package is downloaded and checked. To install it, run this in a "
            f"terminal:\n\n{command}",
            QMessageBox.StandardButton.Close,
            self._window,
        )
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        copy = box.addButton("Copy command", QMessageBox.ButtonRole.ActionRole)
        if details:
            box.setDetailedText(details)
        box.exec()
        if box.clickedButton() is copy:
            QApplication.clipboard().setText(command)

    def _ask_to_restart(self, release: Release) -> None:
        answer = QMessageBox.question(
            self._window,
            "krdpc updated",
            f"krdpc {release.version} is installed. Restart krdpc now to use it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.restart_requested.emit()
