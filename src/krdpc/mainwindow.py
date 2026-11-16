"""The main window: a searchable, sortable list of saved computers."""

from contextlib import contextmanager

from PySide6.QtCore import QModelIndex, QPoint, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from krdpc import __version__
from krdpc.editdialog import EditDialog
from krdpc.icons import symbolic_icon
from krdpc.profile import PROTOCOL, Profile
from krdpc.store import ProfileStore

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
    # Emitted by a double-click or Enter on a computer; connecting arrives in stage 3.
    connect_requested = Signal(str)

    def __init__(self, store: ProfileStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
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
        self.edit_action = action("Edit…", "document-edit", "F4")
        self.edit_action.triggered.connect(lambda: self.edit_profile(self.selected_id()))
        self.duplicate_action = action("Duplicate", "edit-copy", "Ctrl+D")
        self.duplicate_action.triggered.connect(lambda: self.duplicate_profile(self.selected_id()))
        self.delete_action = action("Delete…", "edit-delete", QKeySequence.StandardKey.Delete)
        self.delete_action.triggered.connect(lambda: self.delete_profile(self.selected_id()))
        self.about_action = action("About krdpc", "help-about", slot=self._about)
        self.quit_action = action("Quit", "application-exit", QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)
        for each in (self.edit_action, self.duplicate_action, self.delete_action):
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
        menu.addAction(self.about_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        button = QToolButton()
        button.setIcon(symbolic_icon("open-menu", self.palette(), fallback="application-menu"))
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
        for each in (self.edit_action, self.duplicate_action, self.delete_action):
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

    def _show_context_menu(self, position: QPoint) -> None:
        if not self._view.indexAt(position).isValid():
            return
        menu = QMenu(self)
        menu.addAction(self.edit_action)
        menu.addAction(self.duplicate_action)
        menu.addSeparator()
        menu.addAction(self.delete_action)
        menu.exec(self._view.viewport().mapToGlobal(position))

    # ---- changing profiles -----------------------------------------------

    def new_profile(self) -> None:
        self._edit(Profile())

    def edit_profile(self, profile_id: str) -> None:
        if profile_id:
            self._edit(self._store.get(profile_id))

    def _edit(self, profile: Profile) -> None:
        dialog = EditDialog(profile, self)
        if dialog.exec() == EditDialog.DialogCode.Accepted:
            saved = self._store.save(dialog.profile())
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
        answer = QMessageBox.question(
            self,
            "Delete computer",
            f"Delete “{name}”? Its saved settings are removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._store.delete(profile_id)
            self.reload()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About krdpc",
            f"<b>krdpc {__version__}</b><br>A list of remote computers that opens "
            "each one with FreeRDP's xfreerdp.",
        )
