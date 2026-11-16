"""The main window: a searchable, sortable list of saved computers."""

import dataclasses
import shutil
import sys
from collections import deque
from contextlib import contextmanager

from PySide6.QtCore import (
    QModelIndex,
    QPoint,
    QProcess,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QIcon, QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSystemTrayIcon,
    QToolBar,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from krdpc import autostart, theme, updates
from krdpc.certificate import CertificateInfo, format_thumbprint
from krdpc.editdialog import EditDialog
from krdpc.icons import symbolic_icon
from krdpc.launcher import Launcher
from krdpc.passworddialog import PasswordDialog
from krdpc.passwords import PasswordStore, PasswordStoreError, gateway_key, password_key
from krdpc.preferences import PreferencesStore, is_program
from krdpc.preferencesdialog import PreferencesDialog
from krdpc.profile import PROTOCOL, Profile
from krdpc.store import ProfileStore
from krdpc.updater import Updater

COLUMNS = ("Name", "Group", "Labels", "Server", "Plugin", "Last used")
COL_NAME, COL_GROUP, COL_LABELS, COL_SERVER, COL_PLUGIN, COL_LAST_USED = range(6)
_SEARCHED = (COL_NAME, COL_GROUP, COL_LABELS, COL_SERVER)
ID_ROLE = Qt.ItemDataRole.UserRole


class ProfileFilter(QSortFilterProxyModel):
    """Keeps the rows of the chosen protocol that contain the search text."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._needle = ""
        self._protocol = PROTOCOL
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_needle(self, text: str) -> None:
        with self._changing_filter():
            self._needle = text.strip().casefold()

    def set_protocol(self, protocol: str) -> None:
        with self._changing_filter():
            self._protocol = protocol

    @contextmanager
    def _changing_filter(self):
        """Tell the view the filter is changing (Qt 6.10 way, with the older fallback)."""
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            yield
            self.endFilterChange()
        else:
            yield
            self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model.index(row, COL_PLUGIN, parent).data() != self._protocol:
            return False
        if not self._needle:
            return True
        return any(
            self._needle in (model.index(row, column, parent).data() or "").casefold()
            for column in _SEARCHED
        )


class MainWindow(QMainWindow):
    # Emitted by a double-click or Enter on a computer.
    connect_requested = Signal(str)

    def __init__(
        self,
        store: ProfileStore,
        parent: QWidget | None = None,
        launcher: Launcher | None = None,
        passwords: PasswordStore | None = None,
        preferences: PreferencesStore | None = None,
        updater: Updater | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._preferences_store = preferences or PreferencesStore(store.directory)
        self._preferences = self._preferences_store.load()
        self._tray: QSystemTrayIcon | None = None
        self._tray_toggle: QAction | None = None
        self._quitting = False
        self._passwords = passwords or PasswordStore()
        self._updater = updater or Updater(self, lambda: self._preferences.include_betas)
        self._updater.restart_requested.connect(self.restart)
        self._updater.found_quietly.connect(self._update_found_in_tray)
        # What each computer was last connected with, to try again after a certificate is trusted.
        self._retry: dict[str, tuple[str, str]] = {}
        self._launcher = launcher or Launcher(
            store, find_executable=self._find_xfreerdp, parent=self
        )
        self._launcher.started.connect(self._connection_started)
        self._launcher.failed.connect(self._show_failure)
        self._launcher.certificate_untrusted.connect(self._ask_about_certificate)
        self._launcher.login_rejected.connect(self._forget_passwords)
        self._failures: deque[tuple[str, str]] = deque()
        self._failure_box: QMessageBox | None = None
        self._failure_shown: tuple[str, str] | None = None
        self.connect_requested.connect(self.connect_profile)
        self.setWindowTitle("krdpc")
        self.resize(780, 460)

        self._model = QStandardItemModel(0, len(COLUMNS), self)
        self._model.setHorizontalHeaderLabels(COLUMNS)
        self._proxy = ProfileFilter(self)
        self._proxy.setSourceModel(self._model)

        self._make_actions()
        self._make_toolbar()

        self._protocol = QComboBox()
        self._protocol.addItem(PROTOCOL)
        self._protocol.currentTextChanged.connect(self._proxy.set_protocol)
        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.setPlaceholderText("Search")
        self._search.textChanged.connect(self._proxy.set_needle)
        self._search_row = QWidget()
        row = QHBoxLayout(self._search_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(self._protocol)
        row.addWidget(self._search, 4)
        row.addStretch(1)
        self._search_row.hide()

        self._view = QTreeView()
        self._view.setModel(self._proxy)
        self._view.setRootIsDecorated(False)
        self._view.setUniformRowHeights(True)
        self._view.setAlternatingRowColors(True)
        self._view.setSortingEnabled(True)
        self._view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._show_context_menu)
        self._view.activated.connect(self._activated)
        self._view.sortByColumn(COL_NAME, Qt.SortOrder.AscendingOrder)
        self._view.selectionModel().selectionChanged.connect(self._update_actions)
        self._view.header().setStretchLastSection(True)

        self._total = QLabel()
        self.statusBar().addPermanentWidget(self._total, 1)
        # Which build is running, so testers can tell betas apart at a glance (#9).
        self._version = QLabel(f"krdpc {updates.installed().release}")
        self.statusBar().addPermanentWidget(self._version)
        self._proxy.rowsInserted.connect(self._update_total)
        self._proxy.rowsRemoved.connect(self._update_total)
        self._proxy.layoutChanged.connect(self._update_total)
        self._proxy.modelReset.connect(self._update_total)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self._search_row)
        layout.addWidget(self._view, 1)
        self.setCentralWidget(central)

        self.reload()
        for column, width in enumerate((180, 80, 80, 120, 55, 160)):
            self._view.setColumnWidth(column, width)
        self._apply_preferences()
        self._restore_window()

    # ---- building the window ---------------------------------------------

    def _make_actions(self) -> None:
        def action(text: str, icon: str, shortcut=None, slot=None) -> QAction:
            made = QAction(symbolic_icon(icon, self.palette()), text, self)
            if shortcut is not None:
                made.setShortcut(QKeySequence(shortcut))
            if slot is not None:
                made.triggered.connect(slot)
            return made

        self.new_action = action("New computer", "list-add", QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.new_profile)
        self.search_action = action("Search", "edit-find", QKeySequence.StandardKey.Find)
        self.search_action.setCheckable(True)
        self.search_action.toggled.connect(self._toggle_search)
        self.connect_action = action("Connect", "network-connect", "Ctrl+Return")
        self.connect_action.triggered.connect(lambda: self.connect_profile(self.selected_id()))
        self.edit_action = action("Edit…", "document-edit", "F4")
        self.edit_action.triggered.connect(lambda: self.edit_profile(self.selected_id()))
        self.duplicate_action = action("Duplicate", "edit-copy", "Ctrl+D")
        self.duplicate_action.triggered.connect(lambda: self.duplicate_profile(self.selected_id()))
        self.delete_action = action("Delete…", "edit-delete", QKeySequence.StandardKey.Delete)
        self.delete_action.triggered.connect(lambda: self.delete_profile(self.selected_id()))
        self.preferences_action = action("Preferences…", "configure", "Ctrl+,")
        self.preferences_action.triggered.connect(self.show_preferences)
        self.update_action = action(
            "Check for updates…", "system-software-update", slot=self.check_for_updates
        )
        self.about_action = action("About krdpc", "help-about", slot=self._about)
        self.quit_action = action("Quit", "application-exit", QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.quit)
        for each in (
            self.connect_action,
            self.edit_action,
            self.duplicate_action,
            self.delete_action,
        ):
            self.addAction(each)  # shortcuts work while the list has focus

    def _make_toolbar(self) -> None:
        bar = QToolBar("Main", self)
        bar.setMovable(False)
        bar.addAction(self.new_action)
        bar.addAction(self.search_action)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        menu = QMenu(self)
        menu.addAction(self.preferences_action)
        menu.addAction(self.update_action)
        menu.addAction(self.about_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        button = QToolButton()
        icon = symbolic_icon("open-menu", self.palette(), fallback="application-menu")
        if icon.isNull():
            # No icon theme has one: a word, so the button is never an empty square.
            button.setText("Menu")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        else:
            button.setIcon(icon)
        button.setToolTip("Main menu")
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bar.addWidget(button)
        self.addToolBar(bar)

    # ---- the list --------------------------------------------------------

    def reload(self) -> None:
        """Read every profile again, keeping the selection if it still exists."""
        keep = self.selected_id()
        self._model.removeRows(0, self._model.rowCount())
        icon = QIcon.fromTheme("krdc", QIcon.fromTheme("preferences-desktop-remote-desktop"))
        for profile in self._store.list():
            cells = [
                QStandardItem(text)
                for text in (
                    profile.name,
                    profile.group,
                    profile.labels,
                    profile.server,
                    profile.protocol,
                    profile.last_used_text(),
                )
            ]
            cells[COL_NAME].setIcon(icon)
            for cell in cells:
                cell.setData(profile.id, ID_ROLE)
            self._model.appendRow(cells)
        self._update_total()
        self.select_id(keep)
        self._update_actions()

    def selected_id(self) -> str:
        """The id of the selected computer, or an empty string."""
        indexes = self._view.selectionModel().selectedRows()
        return indexes[0].data(ID_ROLE) if indexes else ""

    def select_id(self, profile_id: str) -> None:
        if not profile_id:
            return
        for row in range(self._proxy.rowCount()):
            index = self._proxy.index(row, COL_NAME)
            if index.data(ID_ROLE) == profile_id:
                self._view.setCurrentIndex(index)
                return

    def visible_names(self) -> list[str]:
        """The names in the list as shown, top to bottom."""
        return [self._proxy.index(row, COL_NAME).data() for row in range(self._proxy.rowCount())]

    def _update_total(self, *_args) -> None:
        count = self._proxy.rowCount()
        self._total.setText(f"Total {count} item{'' if count == 1 else 's'}.")

    def _update_actions(self, *_args) -> None:
        has = bool(self.selected_id())
        for each in (
            self.connect_action,
            self.edit_action,
            self.duplicate_action,
            self.delete_action,
        ):
            each.setEnabled(has)

    def _toggle_search(self, shown: bool) -> None:
        self._search_row.setVisible(shown)
        if shown:
            self._search.setFocus()
        else:
            self._search.clear()
            self._view.setFocus()

    def _activated(self, index: QModelIndex) -> None:
        self.connect_requested.emit(index.data(ID_ROLE))

    def _context_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(self.connect_action)
        menu.addSeparator()
        menu.addAction(self.edit_action)
        menu.addAction(self.duplicate_action)
        menu.addSeparator()
        menu.addAction(self.delete_action)
        return menu

    def _show_context_menu(self, position: QPoint) -> None:
        if self._view.indexAt(position).isValid():
            self._context_menu().exec(self._view.viewport().mapToGlobal(position))

    # ---- changing profiles -----------------------------------------------

    @property
    def launcher(self) -> Launcher:
        return self._launcher

    def connect_profile(self, profile_id: str) -> None:
        if not profile_id:
            return
        try:
            profile = self._store.get(profile_id)
        except KeyError:
            self.reload()  # it was removed outside krdpc
            return
        already = self._launcher.active_count_for(profile.id)
        if already:
            answer = QMessageBox.question(
                self,
                "Already open",
                f"{profile.name} is already open or still connecting. Open another connection?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        credentials = self._credentials(profile)
        if credentials is None:
            return
        self._retry[profile.id] = credentials
        self._launcher.connect_to(profile, *credentials)

    def _credentials(self, profile: Profile) -> tuple[str, str] | None:
        """The password and gateway password: remembered ones, or ask. None if cancelled."""
        if profile.remember_password:
            try:
                password = self._passwords.get(password_key(profile.id))
                gateway = (
                    self._passwords.get(gateway_key(profile.id)) if profile.gateway_server else ""
                )
            except PasswordStoreError as error:
                self.statusBar().showMessage(str(error), 10000)
                password = gateway = None
            if password is not None and gateway is not None:
                return password, gateway
        dialog = PasswordDialog(profile, self)
        if dialog.exec() != PasswordDialog.DialogCode.Accepted:
            return None
        self._remember(profile, dialog.remember(), dialog.password(), dialog.gateway_password())
        return dialog.password(), dialog.gateway_password()

    def _remember(self, profile: Profile, remember: bool, password: str, gateway: str) -> None:
        """Keep or drop the password in the wallet to match the tick in the dialog."""
        try:
            if remember:
                self._passwords.set(password_key(profile.id), password)
                if profile.gateway_server:
                    self._passwords.set(gateway_key(profile.id), gateway)
            else:
                self._forget_in_wallet(profile.id)
        except PasswordStoreError as error:
            QMessageBox.warning(self, "KDE Wallet", str(error))
            remember = False
        if remember != profile.remember_password:
            self._store.save(dataclasses.replace(profile, remember_password=remember))

    def _forget_in_wallet(self, profile_id: str) -> None:
        self._passwords.delete(password_key(profile_id))
        self._passwords.delete(gateway_key(profile_id))

    def _forget_passwords(self, profile_id: str) -> None:
        """The sign-in was refused: stop using a remembered password that may be out of date."""
        try:
            self._forget_in_wallet(profile_id)
        except PasswordStoreError as error:
            self.statusBar().showMessage(str(error), 10000)

    def _connection_started(self, profile_id: str) -> None:
        self.reload()
        try:
            name = self._store.get(profile_id).name
        except (KeyError, ValueError):
            return
        self.statusBar().showMessage(f"Started {name}.", 8000)

    def _ask_about_certificate(self, profile_id: str, info: CertificateInfo) -> None:
        """The remote computer's certificate is not one xfreerdp can verify: ask, then retry."""
        try:
            profile = self._store.get(profile_id)
        except (KeyError, ValueError):
            return
        if not self._trust_certificate(profile, info):
            return
        trusted = dataclasses.replace(profile, trusted_certificate=info.thumbprint)
        self._store.save(trusted)
        self.reload()
        credentials = self._retry.get(profile_id)
        if credentials is not None:
            self._launcher.connect_to(trusted, *credentials)

    def _trust_certificate(self, profile: Profile, info: CertificateInfo) -> bool:
        """Show the certificate and ask whether to trust it."""
        different = bool(profile.trusted_certificate) or info.changed
        text = f"{profile.name} presented a certificate that cannot be verified."
        if different:
            text = (
                f"WARNING: the certificate {profile.name} presented is different from the one "
                "seen before. Someone could be intercepting the connection, or the computer "
                "may just have a new certificate."
            )
        box = QMessageBox(QMessageBox.Icon.Warning, "Untrusted certificate", text, parent=self)
        box.setInformativeText(
            f"Subject: {info.subject}\nIssuer: {info.issuer}\n"
            f"Valid: {info.valid_from} to {info.valid_to}\n"
            f"SHA-256: {format_thumbprint(info.thumbprint)}\n\n"
            "Trust it only if you expect this certificate. krdpc remembers it for this computer."
        )
        trust = box.addButton("Trust and connect", QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel)
        box.exec()
        return box.clickedButton() is trust

    def _show_failure(self, profile_id: str, message: str) -> None:
        """Queue a problem; they are shown one at a time and the same one only once."""
        problem = (profile_id, message)
        if problem == self._failure_shown or problem in self._failures:
            return
        self._failures.append(problem)
        if self._failure_box is None:
            self._next_failure()

    def _next_failure(self) -> None:
        if not self._failures:
            self._failure_box = None
            self._failure_shown = None
            return
        problem = self._failures.popleft()
        profile_id, message = problem
        try:
            name = self._store.get(profile_id).name
        except (KeyError, ValueError):
            name = "the computer"
        summary, _, details = message.partition("\n\n")
        box = QMessageBox(
            QMessageBox.Icon.Warning,
            f"Cannot connect to {name}",
            summary,
            QMessageBox.StandardButton.Ok,
            self,
        )
        if details:
            box.setDetailedText(details)
        # Open without waiting: a waiting dialog would block the ones that follow it.
        box.setWindowModality(Qt.WindowModality.WindowModal)
        box.finished.connect(lambda _result: self._failure_closed(box))
        self._failure_shown = problem
        self._failure_box = box
        box.open()

    def _failure_closed(self, box: QMessageBox) -> None:
        box.deleteLater()
        self._failure_box = None
        self._next_failure()

    def closeEvent(self, event) -> None:
        if self.has_tray() and self._preferences.close_to_tray and not self._quitting:
            self._save_window()
            self.hide()
            event.ignore()
            return
        count = self._launcher.active_count()
        if count:
            answer = QMessageBox.question(
                self,
                "Close krdpc",
                f"{count} connection{' is' if count == 1 else 's are'} open. "
                "Closing krdpc closes "
                f"{'it' if count == 1 else 'them'}.",
                QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Close:
                event.ignore()
                return
            self._launcher.stop_all()
        self._save_window()
        event.accept()
        QApplication.quit()

    # ---- preferences ------------------------------------------------------

    def show_preferences(self) -> None:
        dialog = PreferencesDialog(self._preferences, self)
        if dialog.exec() == PreferencesDialog.DialogCode.Accepted:
            before = self._preferences
            self._preferences = dialog.preferences()
            self._preferences_store.save(self._preferences)
            self._apply_preferences()
            if self._preferences.start_at_login != before.start_at_login:
                self._apply_autostart()

    def _apply_preferences(self) -> None:
        theme.apply(self._preferences.theme)
        pixels = self._preferences.icon_pixels()
        self._view.setIconSize(QSize(pixels, pixels))
        self._update_tray()

    def _apply_autostart(self) -> None:
        try:
            autostart.set_enabled(self._preferences.start_at_login)
        except OSError as error:
            QMessageBox.warning(self, "Start at login", f"Could not change it: {error}")

    # ---- the system tray ----------------------------------------------------

    def _update_tray(self) -> None:
        wanted = self._preferences.show_tray and QSystemTrayIcon.isSystemTrayAvailable()
        if wanted and self._tray is None:
            self._tray = QSystemTrayIcon(self.windowIcon(), self)
            self._tray.setToolTip("krdpc")
            menu = QMenu(self)
            self._tray_toggle = menu.addAction("Show krdpc", self.toggle_window)
            menu.addAction(self.new_action.icon(), "New computer", self._new_from_tray)
            menu.addSeparator()
            menu.addAction(self.quit_action)
            menu.aboutToShow.connect(self._update_tray_menu)
            self._tray.setContextMenu(menu)
            self._tray.activated.connect(self._tray_activated)
            self._tray.show()
        elif not wanted and self._tray is not None:
            self._tray.hide()
            self._tray.deleteLater()
            self._tray = None

    def has_tray(self) -> bool:
        return self._tray is not None

    def starts_hidden(self) -> bool:
        """True if krdpc should start out of sight, in the tray."""
        return self.has_tray() and self._preferences.start_minimised

    def toggle_window(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_window()

    def _update_tray_menu(self) -> None:
        shown = self.isVisible() and not self.isMinimized()
        self._tray_toggle.setText("Hide krdpc" if shown else "Show krdpc")

    def _new_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.new_profile()

    def quit(self) -> bool:
        """Really quit, even with "closing keeps krdpc in the tray" on."""
        self._quitting = True
        closed = self.close()
        if not closed:
            self._quitting = False
        return closed

    # ---- updates ----------------------------------------------------------------

    @property
    def updater(self) -> Updater:
        return self._updater

    def check_for_updates(self) -> None:
        self._updater.check()

    def check_for_updates_at_start(self, delay_ms: int = 3000) -> None:
        """If Preferences allow it, look for a newer release shortly after starting."""
        if self._preferences.check_updates:
            QTimer.singleShot(delay_ms, lambda: self._updater.check(quiet=True))

    def _update_found_in_tray(self, version: str) -> None:
        """A newer release was found while the window was hidden in the tray."""
        if self._tray is not None:
            self._tray.showMessage(
                "krdpc",
                f"krdpc {version} is available. Choose Check for updates in krdpc's menu.",
                QSystemTrayIcon.MessageIcon.Information,
            )

    def restart(self) -> None:
        """Quit and start the krdpc command again, so a newly installed version runs."""
        program = sys.argv[0] if is_program(sys.argv[0]) else shutil.which("krdpc")
        if program and self.quit():
            QProcess.startDetached(program, sys.argv[1:])

    def _find_xfreerdp(self, name: str) -> str | None:
        """The xfreerdp chosen in Preferences, or the first one on the PATH."""
        chosen = self._preferences.xfreerdp_path
        if chosen:
            return chosen if is_program(chosen) else None
        return shutil.which(name)

    def _restore_window(self) -> None:
        if not self._preferences.remember_window:
            return
        saved = self._preferences_store.window()
        if saved is not None:
            geometry, columns = saved
            self.restoreGeometry(geometry)
            self._view.header().restoreState(columns)

    def _save_window(self) -> None:
        if self._preferences.remember_window:
            self._preferences_store.save_window(
                self.saveGeometry(), self._view.header().saveState()
            )

    def new_profile(self) -> None:
        self._edit(Profile())

    def edit_profile(self, profile_id: str) -> None:
        if profile_id:
            self._edit(self._store.get(profile_id))

    def _edit(self, profile: Profile) -> None:
        dialog = EditDialog(profile, self)
        if dialog.exec() == EditDialog.DialogCode.Accepted:
            saved = self._store.save(dialog.profile())
            if profile.remember_password and not saved.remember_password:
                self._forget_passwords(saved.id)
            self.reload()
            self.select_id(saved.id)

    def duplicate_profile(self, profile_id: str) -> None:
        if profile_id:
            copy = self._store.duplicate(profile_id)
            self.reload()
            self.select_id(copy.id)

    def delete_profile(self, profile_id: str) -> None:
        if not profile_id:
            return
        name = self._store.get(profile_id).name
        confirmed = not self._preferences.confirm_delete  # not asked: go straight ahead
        if self._preferences.confirm_delete:
            answer = QMessageBox.question(
                self,
                "Delete computer",
                f"Delete “{name}”? Its saved settings are removed.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            confirmed = answer == QMessageBox.StandardButton.Yes
        if confirmed:
            self._store.delete(profile_id)
            self._forget_passwords(profile_id)
            self.reload()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About krdpc",
            f"<b>krdpc {updates.installed().release}</b><br>A list of remote computers that opens "
            "each one with FreeRDP's xfreerdp.",
        )
