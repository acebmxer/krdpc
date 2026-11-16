"""Profiles on disk: one INI file per computer in the krdpc config folder."""

import configparser
import dataclasses
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from krdpc.profile import Profile, from_mapping, to_mapping

log = logging.getLogger(__name__)

SECTION = "profile"
_ID = re.compile(r"[a-z0-9][a-z0-9-]*")


def default_directory() -> Path:
    """`$XDG_CONFIG_HOME/krdpc`, or `~/.config/krdpc`."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "krdpc"


def slugify(name: str) -> str:
    """A file-name-safe id for a computer's name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "computer"


class ProfileStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory if directory is not None else default_directory()

    def _path(self, profile_id: str) -> Path:
        if not _ID.fullmatch(profile_id):
            raise ValueError(f"Not a valid profile id: {profile_id!r}")
        return self.directory / f"{profile_id}.ini"

    def _read(self, path: Path) -> Profile:
        parser = _parser()
        with path.open(encoding="utf-8") as handle:
            parser.read_file(handle)
        return from_mapping(path.stem, dict(parser[SECTION]))

    def list(self) -> list[Profile]:
        """Every readable profile; a file that cannot be read is logged and skipped."""
        if not self.directory.is_dir():
            return []
        profiles = []
        for path in sorted(self.directory.glob("*.ini")):
            if not _ID.fullmatch(path.stem):
                continue
            try:
                profiles.append(self._read(path))
            except (OSError, UnicodeDecodeError, configparser.Error, KeyError) as error:
                log.warning("Skipping %s: %s", path, error)
        return profiles

    def get(self, profile_id: str) -> Profile:
        """The profile with this id; KeyError if there is none."""
        path = self._path(profile_id)
        try:
            return self._read(path)
        except FileNotFoundError:
            raise KeyError(profile_id) from None

    def _free_id(self, name: str) -> str:
        base = slugify(name)
        candidate, number = base, 2
        while self._path(candidate).exists():
            candidate = f"{base}-{number}"
            number += 1
        return candidate

    def save(self, profile: Profile) -> Profile:
        """Write the profile (a new id is given if it has none) and return it."""
        if not profile.id:
            self.directory.mkdir(parents=True, exist_ok=True)
            profile = dataclasses.replace(profile, id=self._free_id(profile.name))
        path = self._path(profile.id)
        self.directory.mkdir(parents=True, exist_ok=True)
        parser = _parser()
        parser[SECTION] = to_mapping(profile)
        _write_private(path, parser)
        return profile

    def delete(self, profile_id: str) -> None:
        self._path(profile_id).unlink(missing_ok=True)

    def duplicate(self, profile_id: str) -> Profile:
        """Save a copy named `COPY <name>`, never connected to yet."""
        original = self.get(profile_id)
        return self.save(
            dataclasses.replace(original, id="", name=f"COPY {original.name}", last_used="")
        )

    def touch_last_used(self, profile_id: str, when: datetime | None = None) -> Profile:
        """Record that the computer was just connected to."""
        moment = (when or datetime.now()).replace(microsecond=0)
        return self.save(dataclasses.replace(self.get(profile_id), last_used=moment.isoformat()))


def _parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # keep key case exactly as written
    return parser


def _write_private(path: Path, parser: configparser.ConfigParser) -> None:
    """Replace the file in one step, readable by its owner only."""
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".ini")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            parser.write(stream)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
