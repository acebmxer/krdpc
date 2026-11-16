"""A saved remote computer: its fields, defaults, validation and text form."""

import dataclasses
import re
from collections.abc import Mapping
from dataclasses import dataclass

PROTOCOL = "RDP"

# Every choice list is (stored value, label shown in the edit dialog). The first
# entry is not necessarily the default; the default is the field's own.
CHOICES: dict[str, tuple[tuple[str, str], ...]] = {
    "resolution_mode": (
        ("dynamic", "Follow the window size"),
        ("fixed", "Fixed size"),
    ),
    "color_depth": (
        ("auto", "Automatic"),
        ("8", "256 colours (8 bit)"),
        ("15", "32,768 colours (15 bit)"),
        ("16", "65,536 colours (16 bit)"),
        ("24", "16.7 million colours (24 bit)"),
        ("32", "True colour (32 bit)"),
    ),
    "quality": (
        ("poor", "Poor (fastest)"),
        ("medium", "Medium"),
        ("good", "Good"),
        ("best", "Best (slowest)"),
    ),
    "sound": (
        ("off", "Off"),
        ("local", "Play on this computer"),
        ("remote", "Leave on the remote computer"),
    ),
    "security": (
        ("auto", "Automatic"),
        ("nla", "NLA"),
        ("tls", "TLS"),
        ("rdp", "RDP"),
    ),
    "network": (
        ("auto", "Automatic"),
        ("modem", "Modem"),
        ("broadband", "Broadband"),
        ("wan", "WAN"),
        ("lan", "LAN"),
    ),
}


@dataclass
class Profile:
    """One saved computer. `id` is the file name stem and is not stored inside."""

    id: str = ""

    # Basic
    name: str = ""
    group: str = ""
    labels: str = ""
    server: str = ""
    username: str = ""
    domain: str = ""
    resolution_mode: str = "dynamic"
    resolution_width: int = 1920
    resolution_height: int = 1080
    color_depth: str = "auto"
    quality: str = "good"
    maximize: bool = False
    fullscreen: bool = False
    multimon: bool = False
    clipboard: bool = True
    sound: str = "off"
    microphone: bool = False
    drive: str = ""
    share_printers: bool = False
    share_usb: bool = False

    # Advanced
    security: str = "auto"
    ignore_certificate: bool = False
    gateway_server: str = ""
    gateway_username: str = ""
    gateway_domain: str = ""
    network: str = "auto"
    reconnect_attempts: int = 0
    timeout: int = 0
    console: bool = False
    client_name: str = ""
    keyboard_layout: str = ""
    left_handed: bool = False
    disable_smooth_scrolling: bool = False
    disable_fastpath: bool = False
    extra_arguments: str = ""

    # Behaviour
    before_command: str = ""
    after_command: str = ""
    program: str = ""
    locked: bool = False

    # Notes
    notes: str = ""

    # Bookkeeping, set when krdpc connects: ISO 8601 local time, "" if never.
    last_used: str = ""

    @property
    def protocol(self) -> str:
        return PROTOCOL

    def last_used_text(self) -> str:
        """The last-used time as shown in the list: `2026-11-15 - 19:46:32`."""
        return self.last_used.replace("T", " - ") if self.last_used else ""


STORED_FIELDS = tuple(f for f in dataclasses.fields(Profile) if f.name != "id")

_BOOL_TRUE = {"true", "1", "yes", "on"}
_BOOL_FALSE = {"false", "0", "no", "off"}


def escape(text: str) -> str:
    """Make a string safe to keep on one line of an INI file."""
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")


def unescape(text: str) -> str:
    """Undo `escape`. An unknown backslash sequence is kept as written."""
    table = {"\\": "\\", "n": "\n", "r": "\r"}
    return re.sub(r"\\(.)", lambda m: table.get(m.group(1), m.group(0)), text)


def to_text(value: object) -> str:
    """One field value as stored in the file."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return escape(str(value))


def from_text(field: dataclasses.Field, raw: str | None):
    """One stored value as the field's type; anything unusable gives the default."""
    default = field.default
    if raw is None:
        return default
    if field.type is bool:
        lowered = raw.strip().lower()
        if lowered in _BOOL_TRUE:
            return True
        if lowered in _BOOL_FALSE:
            return False
        return default
    if field.type is int:
        try:
            return max(0, int(raw.strip()))
        except ValueError:
            return default
    value = unescape(raw)
    if field.name in CHOICES and value not in {key for key, _ in CHOICES[field.name]}:
        return default
    return value


def from_mapping(profile_id: str, values: Mapping[str, str]) -> Profile:
    """Build a profile from stored text values; missing or bad ones use defaults."""
    kwargs = {f.name: from_text(f, values.get(f.name)) for f in STORED_FIELDS}
    return Profile(id=profile_id, **kwargs)


def to_mapping(profile: Profile) -> dict[str, str]:
    """The profile's stored text values, in field order."""
    return {f.name: to_text(getattr(profile, f.name)) for f in STORED_FIELDS}


def validate(profile: Profile) -> list[str]:
    """Plain-language problems that stop a profile being saved; empty if fine."""
    problems = []
    if not profile.name.strip():
        problems.append("Give the computer a name.")
    if not profile.server.strip():
        problems.append("Enter the server address.")
    if profile.resolution_mode == "fixed" and (
        profile.resolution_width < 1 or profile.resolution_height < 1
    ):
        problems.append("A fixed size needs a width and a height above zero.")
    return problems
