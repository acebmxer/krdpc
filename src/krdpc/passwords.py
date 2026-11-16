"""Remembered passwords, kept in the desktop's wallet (KDE Wallet) and nowhere else."""

import keyring
from keyring.errors import PasswordDeleteError

SERVICE = "krdpc"


class PasswordStoreError(Exception):
    """The wallet could not be used; the message is for the user."""


def password_key(profile_id: str) -> str:
    return profile_id


def gateway_key(profile_id: str) -> str:
    return f"{profile_id}:gateway"


class PasswordStore:
    """Reads and writes through the `keyring` library, which talks to KDE Wallet."""

    def get(self, key: str) -> str | None:
        try:
            return keyring.get_password(SERVICE, key)
        except Exception as error:  # noqa: BLE001 - each wallet backend fails differently
            raise PasswordStoreError(f"The wallet could not be read: {error}") from None

    def set(self, key: str, value: str) -> None:
        try:
            keyring.set_password(SERVICE, key, value)
        except Exception as error:  # noqa: BLE001
            raise PasswordStoreError(f"The wallet could not save the password: {error}") from None

    def delete(self, key: str) -> None:
        """Remove a password; one that is not there is not an error."""
        try:
            keyring.delete_password(SERVICE, key)
        except PasswordDeleteError:
            return
        except Exception as error:  # noqa: BLE001
            raise PasswordStoreError(f"The wallet could not remove the password: {error}") from None
