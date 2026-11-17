import keyring
import keyring.core
import pytest
from keyring.backends import fail

from krdpc import passwords
from krdpc.passwords import PasswordStore, PasswordStoreError, gateway_key, password_key


def test_roundtrip(wallet):
    store = PasswordStore()
    assert store.get("a") is None
    store.set("a", "s3cret")
    assert store.get("a") == "s3cret"
    store.delete("a")
    assert store.get("a") is None


def test_deleting_a_missing_password_is_fine(wallet):
    PasswordStore().delete("never-saved")


def test_keys_do_not_clash():
    assert password_key("dev") != gateway_key("dev")


def test_wallet_failures_become_a_plain_error(monkeypatch):
    def broken(*_args):
        raise RuntimeError("wallet is locked")

    monkeypatch.setattr(keyring, "get_password", broken)
    monkeypatch.setattr(keyring, "set_password", broken)
    monkeypatch.setattr(keyring, "delete_password", broken)
    store = PasswordStore()
    for call in (lambda: store.get("a"), lambda: store.set("a", "b"), lambda: store.delete("a")):
        with pytest.raises(PasswordStoreError, match="wallet is locked"):
            call()


class FakeBus:
    """Answers the session bus calls krdpc makes; records which services it was asked to start."""

    def __init__(self, activatable=(), running=(), broken=()):
        self.activatable = list(activatable)
        self.running = set(running)
        self.broken = set(broken)
        self.started = []
        self.calls = []  # every method, in order
        self.activation_env = {}  # what D-Bus was told to give the services it starts
        self.systemd_env = []  # what systemd's user manager was told

    def send_and_get_reply(self, message, timeout=None):
        from jeepney import HeaderFields

        member = message.header.fields[HeaderFields.member]
        self.calls.append(member)
        if member == "ListActivatableNames":
            body = (self.activatable,)
        elif member == "NameHasOwner":
            body = (message.body[0] in self.running,)
        elif member == "StartServiceByName":
            name = message.body[0]
            self.started.append(name)
            if name in self.broken:
                raise RuntimeError("service exited")
            self.running.add(name)
            body = (1,)
        elif member == "UpdateActivationEnvironment":
            self.activation_env.update(message.body[0])
            body = ()
        elif member == "SetEnvironment":
            self.systemd_env.extend(message.body[0])
            body = ()
        else:
            raise AssertionError(member)
        return type("Reply", (), {"body": body})()


def test_an_idle_kde_wallet_is_started():
    bus = FakeBus(activatable=["org.kde.kwalletd5", "org.kde.kwalletd6", "org.example.other"])
    assert passwords.start_wallet_service(bus)
    assert bus.started == ["org.kde.kwalletd6"]


def test_a_running_wallet_is_left_alone():
    bus = FakeBus(activatable=["org.kde.kwalletd6"], running=["org.kde.kwalletd6"])
    assert not passwords.start_wallet_service(bus)
    assert bus.started == []


def test_a_wallet_that_fails_to_start_falls_through_to_the_next():
    bus = FakeBus(
        activatable=["org.freedesktop.secrets", "org.kde.kwalletd6"],
        broken=["org.freedesktop.secrets"],
    )
    assert passwords.start_wallet_service(bus)
    assert bus.started == ["org.freedesktop.secrets", "org.kde.kwalletd6"]


SCREEN = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0", "HOME": "/home/someone"}


def test_the_wallet_is_told_where_the_screen_is_before_it_starts():
    """Without a desktop session (WSL) D-Bus and systemd know no display, so the wallet aborts."""
    bus = FakeBus(activatable=["org.kde.kwalletd6", passwords.SYSTEMD], running=[passwords.SYSTEMD])
    assert passwords.start_wallet_service(bus, SCREEN)
    assert bus.activation_env == {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
    assert sorted(bus.systemd_env) == ["DISPLAY=:0", "WAYLAND_DISPLAY=wayland-0"]
    assert bus.calls.index("UpdateActivationEnvironment") < bus.calls.index("StartServiceByName")
    assert bus.calls.index("SetEnvironment") < bus.calls.index("StartServiceByName")


def test_systemd_is_not_called_when_it_is_not_on_the_bus():
    bus = FakeBus(activatable=["org.kde.kwalletd6"])
    assert passwords.start_wallet_service(bus, SCREEN)
    assert bus.activation_env == {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
    assert "SetEnvironment" not in bus.calls


def test_nothing_is_shared_when_no_wallet_needs_starting():
    bus = FakeBus(activatable=["org.kde.kwalletd6"], running=["org.kde.kwalletd6"])
    assert not passwords.start_wallet_service(bus, SCREEN)
    assert "UpdateActivationEnvironment" not in bus.calls


def test_no_display_means_nothing_is_shared():
    bus = FakeBus(activatable=["org.kde.kwalletd6"])
    assert passwords.start_wallet_service(bus, {"HOME": "/home/someone"})
    assert "UpdateActivationEnvironment" not in bus.calls


def test_a_refused_environment_update_still_starts_the_wallet():
    class RefusingBus(FakeBus):
        def send_and_get_reply(self, message, timeout=None):
            from jeepney import HeaderFields

            if message.header.fields[HeaderFields.member] == "UpdateActivationEnvironment":
                raise RuntimeError("org.freedesktop.DBus.Error.AccessDenied")
            return super().send_and_get_reply(message, timeout)

    bus = RefusingBus(activatable=["org.kde.kwalletd6"])
    assert passwords.start_wallet_service(bus, SCREEN)
    assert bus.started == ["org.kde.kwalletd6"]


def test_nothing_to_start_without_an_installed_wallet():
    assert not passwords.start_wallet_service(FakeBus(activatable=["org.example.other"]))


def test_no_wallet_at_all_gives_a_plain_message(monkeypatch, wallet):
    monkeypatch.setattr(keyring, "get_keyring", fail.Keyring)
    monkeypatch.setattr(passwords, "_start_wallet", lambda: False)
    store = PasswordStore()
    for call in (lambda: store.get("a"), lambda: store.set("a", "b"), lambda: store.delete("a")):
        with pytest.raises(PasswordStoreError, match="No wallet is running"):
            call()
    assert wallet.items == {}


def test_a_started_wallet_is_used_straight_away(monkeypatch, wallet):
    """`keyring` remembers "no wallet" for the run; after starting one it must look again."""
    found = {"backend": fail.Keyring()}
    looked_again = []

    def init_backend():
        looked_again.append(True)
        found["backend"] = wallet

    monkeypatch.setattr(keyring, "get_keyring", lambda: found["backend"])
    monkeypatch.setattr(keyring.core, "init_backend", init_backend)
    monkeypatch.setattr(passwords, "_start_wallet", lambda: True)
    store = PasswordStore()
    store.set("a", "s3cret")
    assert store.get("a") == "s3cret"
    assert looked_again == [True]
