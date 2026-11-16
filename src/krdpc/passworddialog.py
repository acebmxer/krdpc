"""Asks for the password (and the gateway's, if there is one) when connecting."""

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from krdpc.icons import symbolic_icon
from krdpc.profile import Profile


class PasswordDialog(QDialog):
    def __init__(self, profile: Profile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Connect to {profile.name}")
        self.setMinimumWidth(380)

        who = f"{profile.username}@{profile.server}" if profile.username else profile.server
        self._password = _password_field(self)
        self._gateway = _password_field(self)
        self._remember = QCheckBox("Remember in KDE Wallet")
        self._remember.setChecked(profile.remember_password)
        self._has_gateway = bool(profile.gateway_server)

        form = QFormLayout()
        form.addRow("Password", self._password)
        if self._has_gateway:
            form.addRow("Gateway password", self._gateway)
        form.addRow("", self._remember)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Connect")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Password for {who}"))
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._password.setFocus()

    def password(self) -> str:
        return self._password.text()

    def gateway_password(self) -> str:
        return self._gateway.text() if self._has_gateway else ""

    def remember(self) -> bool:
        return self._remember.isChecked()


def _password_field(parent: QWidget) -> QLineEdit:
    """A hidden-text field with an eye at its right end that shows what was typed."""
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    eye = QAction("Show the password", field)
    eye.setCheckable(True)
    eye.setIcon(symbolic_icon("view-visible", parent.palette(), fallback="view-hidden"))
    eye.setToolTip("Show the password")
    eye.toggled.connect(
        lambda shown: field.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        )
    )
    field.addAction(eye, QLineEdit.ActionPosition.TrailingPosition)
    return field
