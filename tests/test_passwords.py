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

    def send_and_get_reply(self, message, timeout=None):
        from jeepney import HeaderFields

        member = message.header.fields[HeaderFields.member]
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
