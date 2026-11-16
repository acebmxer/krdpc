import stat
from datetime import datetime

import pytest

from krdpc.profile import Profile
from krdpc.store import ProfileStore, default_directory, slugify


def make(name="Dev Fedora", **kwargs):
    return Profile(name=name, server="10.0.0.5", **kwargs)


def test_empty_when_folder_missing(store):
    assert store.list() == []


def test_save_assigns_id_and_roundtrips(store):
    saved = store.save(make(username="nick", notes="a\nb"))
    assert saved.id == "dev-fedora"
    assert (store.directory / "dev-fedora.ini").is_file()
    assert store.get("dev-fedora") == saved
    assert store.list() == [saved]


def test_same_name_gets_a_new_id(store):
    first = store.save(make())
    second = store.save(make())
    assert (first.id, second.id) == ("dev-fedora", "dev-fedora-2")


def test_saving_again_keeps_the_id_and_file(store):
    saved = store.save(make())
    renamed = store.save(Profile(**{**saved.__dict__, "name": "Renamed"}))
    assert renamed.id == saved.id
    assert [p.name for p in store.list()] == ["Renamed"]


def test_file_is_private_and_leaves_no_temp_files(store):
    store.save(make())
    path = store.directory / "dev-fedora.ini"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [p.name for p in store.directory.iterdir()] == ["dev-fedora.ini"]


def test_password_fields_are_never_written(store):
    store.save(make())
    text = (store.directory / "dev-fedora.ini").read_text()
    assert "password" not in text.lower()


def test_delete(store):
    saved = store.save(make())
    store.delete(saved.id)
    assert store.list() == []
    store.delete(saved.id)  # already gone: no error


def test_duplicate(store):
    original = store.save(make(last_used="2026-11-15T19:46:32", username="nick"))
    copy = store.duplicate(original.id)
    assert copy.name == "COPY Dev Fedora"
    assert copy.id != original.id
    assert copy.username == "nick"
    assert copy.last_used == ""
    assert len(store.list()) == 2


def test_touch_last_used(store):
    saved = store.save(make())
    when = datetime(2026, 11, 15, 19, 46, 32, 999)
    assert store.touch_last_used(saved.id, when).last_used == "2026-11-15T19:46:32"
    assert store.get(saved.id).last_used == "2026-11-15T19:46:32"


def test_get_missing_raises_key_error(store):
    with pytest.raises(KeyError):
        store.get("nope")


@pytest.mark.parametrize("bad", ["../evil", "a/b", "", ".hidden", "UPPER", "a b"])
def test_ids_that_could_leave_the_folder_are_refused(store, bad):
    with pytest.raises(ValueError):
        store.get(bad)
    with pytest.raises(ValueError):
        store.delete(bad)


def test_unreadable_and_foreign_files_are_skipped(store):
    store.save(make())
    (store.directory / "broken.ini").write_text("no section here\n")
    (store.directory / "binary.ini").write_bytes(b"\xff\xfe\x00")
    (store.directory / "notes.txt").write_text("hello")
    (store.directory / "Bad Name.ini").write_text("[profile]\nname=x\n")
    assert [p.id for p in store.list()] == ["dev-fedora"]


def test_slugify():
    assert slugify("  Win11 - Dev! ") == "win11-dev"
    assert slugify("!!!") == "computer"


def test_default_directory_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_directory() == tmp_path / "krdpc"
    assert ProfileStore().directory == tmp_path / "krdpc"
