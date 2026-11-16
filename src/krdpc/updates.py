"""Finding, downloading and installing a newer krdpc release from GitHub.

Only packaged copies can update themselves. The release build writes `krdpc/_package.py`
(see scripts/build_package.sh) with the exact release it was built as (`0.1.0` or
`0.1.0-beta.1`) and the package format (`rpm`, `deb` or `arch`). A copy installed from a
clone has no such file: it can learn that a newer release exists, but not install it.
"""

import hashlib
import json
import os
import re
import shutil
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from krdpc import __version__

REPOSITORY = "acebmxer/krdpc"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases"
_API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=50"
# A package is only ever downloaded from this repository's own release files.
_DOWNLOAD_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
_TIMEOUT = 20  # seconds, for each network read
_CHUNK = 64 * 1024

FORMATS = ("rpm", "deb", "arch")
_SUFFIXES = {"rpm": ".rpm", "deb": ".deb", "arch": ".pkg.tar.zst"}
_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?")


class UpdateError(Exception):
    """Something went wrong; the message is a plain sentence for the user."""


class Cancelled(UpdateError):
    def __init__(self) -> None:
        super().__init__("The download was cancelled.")


def version_key(text: str) -> tuple[int, int, int, int, int] | None:
    """A sortable key for `0.1.0`, `v0.1.0` or `0.1.0-beta.2`; None if it is neither.

    A beta comes before the stable release of the same number: 0.1.0-beta.2 < 0.1.0.
    """
    match = _VERSION.fullmatch(text.strip())
    if match is None:
        return None
    major, minor, patch, beta = match.groups()
    stable = (1, 0) if beta is None else (0, int(beta))
    return (int(major), int(minor), int(patch), *stable)


@dataclass(frozen=True)
class Installed:
    release: str  # e.g. "0.1.0" or "0.1.0-beta.1"
    package_format: str | None  # "rpm", "deb", "arch", or None for a copy from a clone

    @property
    def can_update_itself(self) -> bool:
        return self.package_format in FORMATS


def installed() -> Installed:
    """What this copy of krdpc is, from the file the package build adds."""
    try:
        from krdpc import _package  # only packaged copies have it
    except ImportError:
        return Installed(__version__, None)
    release = str(getattr(_package, "RELEASE", __version__))
    package_format = getattr(_package, "FORMAT", None)
    if version_key(release) is None:
        release = __version__
    return Installed(release, package_format if package_format in FORMATS else None)


@dataclass(frozen=True)
class Release:
    tag: str  # "v0.2.0" or "v0.2.0-beta.1"
    prerelease: bool
    page: str  # the release's page on GitHub
    assets: dict[str, str] = field(default_factory=dict)  # file name -> download URL

    @property
    def version(self) -> str:
        return self.tag.removeprefix("v")

    def package(self, package_format: str) -> tuple[str, str] | None:
        """(file name, URL) of this release's package for the format, or None."""
        suffix = _SUFFIXES.get(package_format)
        if suffix is None:
            return None
        found = sorted(
            (name, url)
            for name, url in self.assets.items()
            if name.endswith(suffix) and url.startswith(_DOWNLOAD_PREFIX)
        )
        return found[0] if len(found) == 1 else None

    def checksums(self) -> str | None:
        """The URL of SHA256SUMS, or None."""
        url = self.assets.get("SHA256SUMS")
        return url if url and url.startswith(_DOWNLOAD_PREFIX) else None


def parse_releases(data: object) -> list[Release]:
    """The published releases in GitHub's answer; drafts and odd tags are left out."""
    releases = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        tag = str(item.get("tag_name") or "")
        if version_key(tag) is None:
            continue
        assets = {
            str(asset.get("name")): str(asset.get("browser_download_url"))
            for asset in item.get("assets") or []
            if isinstance(asset, dict) and asset.get("name") and asset.get("browser_download_url")
        }
        releases.append(
            Release(
                tag=tag,
                prerelease=bool(item.get("prerelease")) or "-beta." in tag,
                page=str(item.get("html_url") or RELEASES_PAGE),
                assets=assets,
            )
        )
    return releases


def newest(releases: list[Release], current: str, include_betas: bool) -> Release | None:
    """The newest release above `current`, or None. Betas only if asked for."""
    have = version_key(current)
    candidates = [
        release
        for release in releases
        if (include_betas or not release.prerelease)
        and (have is None or version_key(release.tag) > have)
    ]
    return max(candidates, key=lambda release: version_key(release.tag), default=None)


def _open(url: str, accept: str = "*/*"):
    request = urllib.request.Request(
        url, headers={"Accept": accept, "User-Agent": f"krdpc/{__version__}"}
    )
    try:
        return urllib.request.urlopen(request, timeout=_TIMEOUT)
    except OSError as error:  # URLError, HTTPError and timeouts are all OSErrors
        raise UpdateError(f"Could not reach GitHub: {_reason(error)}") from error


def _reason(error: OSError) -> str:
    return str(getattr(error, "reason", None) or error)


def fetch_releases() -> list[Release]:
    """Ask GitHub for the releases. Raises UpdateError."""
    with _open(_API, "application/vnd.github+json") as answer:
        try:
            data = json.load(answer)
        except (OSError, ValueError) as error:
            raise UpdateError("GitHub's answer about releases could not be read.") from error
    return parse_releases(data)


def check(include_betas: bool) -> tuple[Installed, Release | None]:
    """This copy and the newest release above it (None: already the newest)."""
    current = installed()
    return current, newest(fetch_releases(), current.release, include_betas)


def download_folder() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "krdpc" / "updates"


def expected_checksum(sums: str, name: str) -> str | None:
    """The SHA-256 that a `sha256sum` listing gives for `name`."""
    for line in sums.splitlines():
        parts = line.strip().split(maxsplit=1)
        if (
            len(parts) == 2
            and parts[1].lstrip("*") == name
            and re.fullmatch(r"[0-9a-f]{64}", parts[0])
        ):
            return parts[0]
    return None


def download(
    release: Release,
    package_format: str,
    folder: Path,
    progress: Callable[[int, int], None] = lambda _done, _total: None,
    cancel: threading.Event | None = None,
) -> Path:
    """Download the package for this format and check it against SHA256SUMS.

    Returns the file. Raises UpdateError (Cancelled if `cancel` was set).
    """
    found = release.package(package_format)
    if found is None:
        raise UpdateError(f"krdpc {release.version} has no {package_format} package to install.")
    name, url = found
    sums_url = release.checksums()
    if sums_url is None:
        raise UpdateError(f"krdpc {release.version} has no SHA256SUMS file to check it against.")
    with _open(sums_url) as answer:
        try:
            sums = answer.read(1024 * 1024).decode("utf-8", errors="replace")
        except OSError as error:
            raise UpdateError(f"Could not download SHA256SUMS: {_reason(error)}") from error
    wanted = expected_checksum(sums, name)
    if wanted is None:
        raise UpdateError(f"SHA256SUMS does not list {name}.")

    folder.mkdir(parents=True, exist_ok=True)
    target = folder / Path(name).name
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    try:
        with _open(url) as answer, open(partial, "wb") as out:
            total = int(answer.headers.get("Content-Length") or 0)
            done = 0
            while chunk := answer.read(_CHUNK):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                progress(done, total)
    except OSError as error:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"Could not download {name}: {_reason(error)}") from error
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != wanted:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"{name} did not match its checksum, so it was not installed.")
    os.replace(partial, target)
    return target


def install_command(package_format: str, path: Path) -> list[str]:
    """The package-manager command that installs `path` (run as root)."""
    if package_format == "rpm":
        return ["dnf", "install", "-y", str(path)]
    if package_format == "deb":
        return ["apt-get", "install", "-y", str(path)]
    if package_format == "arch":
        return ["pacman", "-U", "--noconfirm", str(path)]
    raise ValueError(package_format)


def manual_command(package_format: str, path: Path) -> str:
    """The same install as a line to type in a terminal."""
    words = ["sudo", *install_command(package_format, path)]
    words = [word for word in words if word not in {"-y", "--noconfirm"}]
    return " ".join(f"'{word}'" if " " in word else word for word in words)


def pkexec() -> str | None:
    """pkexec, which shows the desktop's own password box for admin rights."""
    return shutil.which("pkexec")


def pkexec_arguments(package_format: str, path: Path) -> list[str]:
    """What to give pkexec to install `path`.

    `--disable-internal-agent` stops pkexec asking for the password in the terminal krdpc was
    started from, where nobody sees the question and the install waits forever. With no
    desktop password box it now fails at once, and krdpc shows the command to run by hand.
    """
    return ["--disable-internal-agent", *install_command(package_format, path)]


# pkexec's own exit codes: the password box was closed, or no permission was given.
PKEXEC_DISMISSED = 126
PKEXEC_REFUSED = 127
