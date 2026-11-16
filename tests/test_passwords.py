import keyring
import pytest

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
