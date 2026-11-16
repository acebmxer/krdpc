"""The tabbed dialog for adding and editing a computer."""

import dataclasses

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from krdpc.profile import CHOICES, STORED_FIELDS, Profile, validate

_LOCK_FIELD = "locked"


class EditDialog(QDialog):
    """Edit one profile. `profile()` returns the result; nothing is saved here."""

    def __init__(self, profile: Profile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._original = profile
        self.setWindowTitle(f"Edit {profile.name}" if profile.id else "New computer")
        self.setMinimumWidth(480)
        self._widgets: dict[str, QWidget] = {}

        self._tabs = QTabWidget()
        self._tabs.addTab(self._basic_tab(), "Basic")
        self._tabs.addTab(self._advanced_tab(), "Advanced")
        self._tabs.addTab(self._behaviour_tab(), "Behaviour")
        self._tabs.addTab(self._notes_tab(), "Notes")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._tabs)
        layout.addWidget(buttons)

        for field in STORED_FIELDS:
            if field.name in self._widgets:
                _write(self._widgets[field.name], getattr(profile, field.name))
        self._fixed_size_changed()
        self._apply_lock()

    # ---- tabs -------------------------------------------------------------

    def _basic_tab(self) -> QWidget:
        form, tab = _form()
        self._add(form, "Name", "name", QLineEdit())
        self._add(form, "Group", "group", QLineEdit())
        self._add(form, "Labels", "labels", QLineEdit(placeholderText="Separate with commas"))
        self._add(form, "Server", "server", QLineEdit(placeholderText="Address or name"))
        self._add(form, "Username", "username", QLineEdit())
        self._add(form, "Domain", "domain", QLineEdit())

        mode = _combo("resolution_mode")
        mode.currentIndexChanged.connect(self._fixed_size_changed)
        width, height = _spin(1, 16384), _spin(1, 16384)
        self._widgets["resolution_width"], self._widgets["resolution_height"] = width, height
        self._widgets["resolution_mode"] = mode
        size_row = QHBoxLayout()
        size_row.addWidget(mode, 1)
        size_row.addWidget(width)
        size_row.addWidget(QLabel("×"))
        size_row.addWidget(height)
        form.addRow("Resolution", size_row)

        self._add(form, "Colour depth", "color_depth", _combo("color_depth"))
        self._add(form, "Quality", "quality", _combo("quality"))
        self._add(form, "Sound", "sound", _combo("sound"))
        self._add(form, "", "maximize", QCheckBox("Start maximised"))
        self._add(form, "", "fullscreen", QCheckBox("Full screen"))
        self._add(form, "", "multimon", QCheckBox("Use several monitors"))
        self._add(form, "", "clipboard", QCheckBox("Share the clipboard"))
        self._add(form, "", "microphone", QCheckBox("Share the microphone"))
        self._add(form, "", "share_printers", QCheckBox("Share printers"))
        self._add(form, "", "share_usb", QCheckBox("Share USB devices"))

        folder = QLineEdit(placeholderText="A folder on this computer to share")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(folder, 1)
        folder_row.addWidget(browse)
        self._widgets["drive"] = folder
        form.addRow("Shared folder", folder_row)
        return tab

    def _advanced_tab(self) -> QWidget:
        form, tab = _form()
        self._add(form, "Security", "security", _combo("security"))
        self._add(form, "", "ignore_certificate", QCheckBox("Ignore certificate errors"))
        self._add(form, "Gateway server", "gateway_server", QLineEdit())
        self._add(form, "Gateway username", "gateway_username", QLineEdit())
        self._add(form, "Gateway domain", "gateway_domain", QLineEdit())
        self._add(form, "Network", "network", _combo("network"))
        self._add(form, "Reconnect attempts", "reconnect_attempts", _spin(0, 1000, "default"))
        self._add(form, "Time-out (seconds)", "timeout", _spin(0, 3600, "default"))
        self._add(form, "", "console", QCheckBox("Connect to the console (admin) session"))
        self._add(form, "Client name", "client_name", QLineEdit())
        self._add(form, "Keyboard layout", "keyboard_layout", QLineEdit(placeholderText="Default"))
        self._add(
            form,
            "Extra arguments",
            "extra_arguments",
            QLineEdit(placeholderText="Added to the xfreerdp command as they are"),
        )
        return tab

    def _behaviour_tab(self) -> QWidget:
        form, tab = _form()
        self._add(form, "Run before connecting", "before_command", QLineEdit())
        self._add(form, "Run after disconnecting", "after_command", QLineEdit())
        self._add(
            form,
            "Start program",
            "program",
            QLineEdit(placeholderText="A program on the remote computer, started on sign-in"),
        )
        lock = QCheckBox("Lock this computer's settings")
        lock.toggled.connect(self._apply_lock)
        self._add(form, "", _LOCK_FIELD, lock)
        return tab

    def _notes_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        notes = QPlainTextEdit()
        self._widgets["notes"] = notes
        layout.addWidget(notes)
        return tab

    # ---- behaviour --------------------------------------------------------

    def _add(self, form: QFormLayout, label: str, field: str, widget: QWidget) -> None:
        self._widgets[field] = widget
        form.addRow(label, widget)

    def _fixed_size_changed(self) -> None:
        fixed = _read(self._widgets["resolution_mode"]) == "fixed"
        self._widgets["resolution_width"].setEnabled(fixed and not self._locked())
        self._widgets["resolution_height"].setEnabled(fixed and not self._locked())

    def _locked(self) -> bool:
        return bool(_read(self._widgets[_LOCK_FIELD]))

    def _apply_lock(self) -> None:
        """A locked computer cannot be changed until the lock is turned off."""
        locked = self._locked()
        for name, widget in self._widgets.items():
            if name != _LOCK_FIELD:
                widget.setEnabled(not locked)
        if not locked:
            self._fixed_size_changed()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder to share")
        if folder:
            _write(self._widgets["drive"], folder)

    def profile(self) -> Profile:
        """The profile as the dialog now shows it, with the original's id and last use."""
        values = {name: _read(widget) for name, widget in self._widgets.items()}
        return dataclasses.replace(self._original, **values)

    def accept(self) -> None:
        problems = validate(self.profile())
        if problems:
            QMessageBox.warning(self, "Cannot save yet", "\n".join(problems))
            return
        super().accept()


def _form() -> tuple[QFormLayout, QWidget]:
    tab = QWidget()
    form = QFormLayout(tab)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return form, tab


def _combo(field: str) -> QComboBox:
    box = QComboBox()
    for value, label in CHOICES[field]:
        box.addItem(label, value)
    return box


def _spin(low: int, high: int, zero_text: str = "") -> QSpinBox:
    box = QSpinBox()
    box.setRange(low, high)
    if zero_text:
        box.setSpecialValueText(zero_text)
    return box


def _read(widget: QWidget):
    if isinstance(widget, QLineEdit):
        return widget.text().strip()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QComboBox):
        return widget.currentData()
    if isinstance(widget, QPlainTextEdit):
        return widget.toPlainText()
    raise TypeError(f"Cannot read a {type(widget).__name__}")


def _write(widget: QWidget, value) -> None:
    if isinstance(widget, QLineEdit):
        widget.setText(value)
    elif isinstance(widget, QCheckBox):
        widget.setChecked(value)
    elif isinstance(widget, QSpinBox):
        widget.setValue(value)
    elif isinstance(widget, QComboBox):
        widget.setCurrentIndex(max(0, widget.findData(value)))
    elif isinstance(widget, QPlainTextEdit):
        widget.setPlainText(value)
    else:
        raise TypeError(f"Cannot write a {type(widget).__name__}")
