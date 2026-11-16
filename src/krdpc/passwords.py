"""Remembered passwords, kept in the desktop's wallet (KDE Wallet) and nowhere else."""

import contextlib

import keyring
import keyring.backend
import keyring.core
from keyring.backends import fail
from keyring.errors import PasswordDeleteError

SERVICE = "krdpc"

# The `keyring` library only uses a wallet whose D-Bus service is already running. A desktop
# session starts one, but without a session (Fedora under WSL, a bare window manager) the
# wallet is installed yet idle. These are the services krdpc asks D-Bus to start, first one
# that starts wins: the Secret Service (GNOME Keyring and others), then KDE Wallet, whose
# daemon also brings up KDE's Secret Service.
WALLET_SERVICES = ("org.freedesktop.secrets", "org.kde.kwalletd6", "org.kde.kwalletd5")
START_TIMEOUT = 15  # seconds; D-Bus waits for the wallet to come up before answering

NO_WALLET = (
    "No wallet is running, so krdpc cannot remember passwords. Install KDE Wallet "
    "(or another wallet that offers the Secret Service) and try again. "
    "You can still connect: krdpc asks for the password each time."
)


class PasswordStoreError(Exception):
    """The wallet could not be used; the message is for the user."""


def password_key(profile_id: str) -> str:
    return profile_id


def gateway_key(profile_id: str) -> str:
    return f"{profile_id}:gateway"


def start_wallet_service(connection) -> bool:
    """Ask D-Bus to start the first installed wallet that is not running yet.

    `connection` is a blocking jeepney connection to the session bus. True if one started.
    """
    from jeepney.bus_messages import message_bus

    def call(message, timeout=5):
        return connection.send_and_get_reply(message, timeout=timeout).body

    activatable = set(call(message_bus.ListActivatableNames())[0])
    for name in WALLET_SERVICES:
        if name not in activatable or call(message_bus.NameHasOwner(name))[0]:
            continue
        try:
            call(message_bus.StartServiceByName(name), timeout=START_TIMEOUT)
        except Exception:  # noqa: BLE001, S112 - a wallet that fails to start; try the next one
            continue
        return True
    return False


def _start_wallet() -> bool:
    """Start an idle wallet on the session bus. False if there is no bus or no wallet."""
    try:
        from jeepney.io.blocking import open_dbus_connection

        with open_dbus_connection(bus="SESSION") as connection:
            return start_wallet_service(connection)
    except Exception:  # noqa: BLE001 - no jeepney, no session bus, or D-Bus refused
        return False


class PasswordStore:
    """Reads and writes through the `keyring` library, which talks to KDE Wallet."""

    def _ensure_wallet(self) -> None:
        """Make sure `keyring` has a wallet to talk to, starting an idle one if needed."""
        if not isinstance(keyring.get_keyring(), fail.Keyring):
            return
        if _start_wallet():
            # `keyring` looks for wallets once per run and keeps the answer: look again.
            reset = getattr(keyring.backend.get_all_keyring, "reset", None)
            if reset is not None:
                with contextlib.suppress(KeyError):  # nothing kept yet
                    reset()
            keyring.core.init_backend()
        if isinstance(keyring.get_keyring(), fail.Keyring):
            raise PasswordStoreError(NO_WALLET)

    def get(self, key: str) -> str | None:
        self._ensure_wallet()
        try:
            return keyring.get_password(SERVICE, key)
        except Exception as error:  # noqa: BLE001 - each wallet backend fails differently
            raise PasswordStoreError(f"The wallet could not be read: {error}") from None

    def set(self, key: str, value: str) -> None:
        self._ensure_wallet()
        try:
            keyring.set_password(SERVICE, key, value)
        except Exception as error:  # noqa: BLE001
            raise PasswordStoreError(f"The wallet could not save the password: {error}") from None

    def delete(self, key: str) -> None:
        """Remove a password; one that is not there is not an error."""
        self._ensure_wallet()
        try:
            keyring.delete_password(SERVICE, key)
        except PasswordDeleteError:
            return
        except Exception as error:  # noqa: BLE001
            raise PasswordStoreError(f"The wallet could not remove the password: {error}") from None
