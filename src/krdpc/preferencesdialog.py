"""The Preferences page."""

import dataclasses

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from krdpc.preferences import ICON_SIZES, Preferences, is_program
from krdpc.theme import THEMES


class PreferencesDialog(QDialog):
    def __init__(
        self,
        preferences: Preferences,
        parent: QWidget | None = None,
        tray_available: bool | None = None,
    ) -> None:
        super().__init__(parent)
        if tray_available is None:
            tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(460)
        self._original = preferences

        self._icon_size = QComboBox()
        for name, label, _pixels in ICON_SIZES:
            self._icon_size.addItem(label, name)
        self._icon_size.setCurrentIndex(max(0, self._icon_size.findData(preferences.icon_size)))
        self._theme = QComboBox()
        for name, label in THEMES:
            self._theme.addItem(label, name)
        self._theme.setCurrentIndex(max(0, self._theme.findData(preferences.theme)))
        self._confirm_delete = QCheckBox("Ask before deleting a computer")
        self._confirm_delete.setChecked(preferences.confirm_delete)
        self._remember_window = QCheckBox("Remember the window size and the columns")
        self._remember_window.setChecked(preferences.remember_window)

        self._show_tray = QCheckBox("Show an icon in the system tray")
        self._show_tray.setChecked(preferences.show_tray)
        self._close_to_tray = QCheckBox("Closing the window keeps krdpc running in the tray")
        self._close_to_tray.setChecked(preferences.close_to_tray)
        self._start_minimised = QCheckBox("Start with the window hidden, in the tray")
        self._start_minimised.setChecked(preferences.start_minimised)
        self._start_at_login = QCheckBox("Start krdpc when I log in")
        self._start_at_login.setChecked(preferences.start_at_login)
        if not tray_available:
            self._show_tray.setEnabled(False)
            self._show_tray.setToolTip("No system tray was found on this desktop.")
            self._show_tray.setChecked(False)
        self._show_tray.toggled.connect(self._tray_changed)
        self._tray_changed()

        self._xfreerdp = QLineEdit(preferences.xfreerdp_path)
        self._xfreerdp.setPlaceholderText("Empty: use xfreerdp3 or xfreerdp from your PATH")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        program_row = QHBoxLayout()
        program_row.addWidget(self._xfreerdp, 1)
        program_row.addWidget(browse)

        form = QFormLayout()
        form.addRow("Colours", self._theme)
        form.addRow("Icon size", self._icon_size)
        form.addRow("", self._confirm_delete)
        form.addRow("", self._remember_window)
        form.addRow("", self._show_tray)
        form.addRow("", self._close_to_tray)
        form.addRow("", self._start_minimised)
        form.addRow("", self._start_at_login)
        form.addRow("xfreerdp", program_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _tray_changed(self) -> None:
        """The two tray-only options need the tray icon."""
        shown = self._show_tray.isChecked()
        self._close_to_tray.setEnabled(shown)
        self._start_minimised.setEnabled(shown)

    def preferences(self) -> Preferences:
        return dataclasses.replace(
            self._original,
            show_tray=self._show_tray.isChecked(),
            close_to_tray=self._close_to_tray.isChecked(),
            start_minimised=self._start_minimised.isChecked(),
            start_at_login=self._start_at_login.isChecked(),
            icon_size=self._icon_size.currentData(),
            theme=self._theme.currentData(),
            confirm_delete=self._confirm_delete.isChecked(),
            remember_window=self._remember_window.isChecked(),
            xfreerdp_path=self._xfreerdp.text().strip(),
        ).normalised()

    def _browse(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Choose xfreerdp")
        if path:
            self._xfreerdp.setText(path)

    def accept(self) -> None:
        path = self.preferences().xfreerdp_path
        if path and not is_program(path):
            QMessageBox.warning(
                self, "Cannot save yet", "The xfreerdp location is not a program you can run."
            )
            return
        super().accept()
