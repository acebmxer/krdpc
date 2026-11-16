"""Turn a profile into the `xfreerdp` command line."""

import shlex
from pathlib import PurePath

from krdpc.profile import Profile


class CommandError(ValueError):
    """A profile that cannot be turned into a command; the message is for the user."""


# What each quality level turns off or on. xfreerdp options verified against 3.33.1.
_QUALITY = {
    "poor": ["-wallpaper", "-themes", "-fonts"],
    "medium": ["-wallpaper", "-themes"],
    "good": ["-wallpaper"],
    "best": ["+aero", "+menu-anims"],
}

_SOUND = {
    "off": ["/audio-mode:none"],
    "local": ["/audio-mode:redirect", "/sound"],
    "remote": ["/audio-mode:server"],
}


def build_command(profile: Profile, executable: str = "xfreerdp") -> list[str]:
    """The argument list that starts `profile`. No password is ever included."""
    if not profile.server.strip():
        raise CommandError("This computer has no server address.")

    args = [executable, f"/v:{profile.server.strip()}", f"/t:{profile.name}"]
    if profile.username:
        args.append(f"/u:{profile.username}")
    if profile.domain:
        args.append(f"/d:{profile.domain}")

    if profile.fullscreen:
        args.append("/f")
    elif profile.maximize:
        args.append("+workarea")
    if profile.resolution_mode == "fixed":
        args.append(f"/size:{profile.resolution_width}x{profile.resolution_height}")
    else:
        args.append("/dynamic-resolution")
    if profile.multimon:
        args.append("+multimon")
    if profile.color_depth != "auto":
        args.append(f"/bpp:{profile.color_depth}")
    args += _QUALITY[profile.quality]

    args.append("+clipboard" if profile.clipboard else "-clipboard")
    args += _SOUND[profile.sound]
    if profile.microphone:
        args.append("/microphone")
    if profile.drive:
        args.append(_drive_argument(profile.drive))
    if profile.share_printers:
        args.append("/printer")
    if profile.share_usb:
        args.append("/usb:auto")

    if profile.security != "auto":
        args.append(f"/sec:{profile.security}")
    if profile.ignore_certificate:
        args.append("/cert:ignore")
    if profile.gateway_server:
        args.append(_gateway_argument(profile))
    if profile.network != "auto":
        args.append(f"/network:{profile.network}")
    if profile.reconnect_attempts:
        args += ["+auto-reconnect", f"/auto-reconnect-max-retries:{profile.reconnect_attempts}"]
    if profile.timeout:
        args.append(f"/timeout:{profile.timeout * 1000}")
    if profile.console:
        args.append("+admin")
    if profile.client_name:
        args.append(f"/client-hostname:{profile.client_name}")
    if profile.keyboard_layout:
        args.append(f"/kbd:layout:{profile.keyboard_layout}")
    if profile.program:
        args.append(f"/shell:{profile.program}")

    if profile.extra_arguments.strip():
        try:
            args += shlex.split(profile.extra_arguments)
        except ValueError as error:
            raise CommandError(f"The extra arguments are not valid: {error}.") from None
    return args


def _drive_argument(path: str) -> str:
    """`/drive:<name>,<path>`; the share is named after the folder."""
    name = PurePath(path).name.replace(",", " ").strip() or "share"
    return f"/drive:{name},{path}"


def _gateway_argument(profile: Profile) -> str:
    parts = [("g", profile.gateway_server), ("u", profile.gateway_username)]
    parts.append(("d", profile.gateway_domain))
    for _, value in parts:
        if "," in value:
            raise CommandError("The gateway settings cannot contain commas.")
    return "/gateway:" + ",".join(f"{key}:{value}" for key, value in parts if value)
