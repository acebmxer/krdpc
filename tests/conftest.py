import os

import pytest

# Tests draw windows without a screen; set before Qt loads.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    from krdpc.store import ProfileStore

    return ProfileStore(tmp_path / "krdpc")


class MemoryKeyring:
    """Stands in for KDE Wallet: keeps passwords in a dict for the length of a test."""

    def __init__(self):
        self.items = {}

    def get_password(self, service, key):
        return self.items.get((service, key))

    def set_password(self, service, key, value):
        self.items[(service, key)] = value

    def delete_password(self, service, key):
        from keyring.errors import PasswordDeleteError

        if (service, key) not in self.items:
            raise PasswordDeleteError(key)
        del self.items[(service, key)]


@pytest.fixture(autouse=True)
def wallet(monkeypatch):
    """No test ever touches the real wallet."""
    import keyring

    memory = MemoryKeyring()
    monkeypatch.setattr(keyring, "get_password", memory.get_password)
    monkeypatch.setattr(keyring, "set_password", memory.set_password)
    monkeypatch.setattr(keyring, "delete_password", memory.delete_password)
    return memory


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    """No test ever writes to the real ~/.config (autostart entries, settings)."""
    home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    return home
