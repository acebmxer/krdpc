import pytest
from test_launcher import fake_xfreerdp, wait_for

from krdpc import sessionwindow
from krdpc.launcher import Launcher
from krdpc.preferences import PreferencesStore
from krdpc.profile import Profile
from krdpc.sessionwindow import SessionWindow, read_session_window, window_arguments


def profile(**kwargs):
    return Profile(id="dev", name="Dev", server="10.0.0.5", **kwargs)


def test_a_normal_window_is_asked_for_by_size():
    assert window_arguments(profile(), SessionWindow(1280, 800), []) == ["/size:1280x800"]


def test_a_maximized_window_opens_maximized():
    window = SessionWindow(1920, 1050, maximized=True)
    assert window_arguments(profile(), window, []) == ["+workarea"]


def test_a_maximized_window_with_no_earlier_size_still_opens_maximized():
    assert window_arguments(profile(), SessionWindow(0, 0, maximized=True), []) == ["+workarea"]


def test_nothing_remembered_adds_nothing():
    assert window_arguments(profile(), None, []) == []


def test_a_tiny_window_is_not_remembered():
    assert window_arguments(profile(), SessionWindow(40, 30), []) == []


@pytest.mark.parametrize(
    "settings",
    [
        {"resolution_mode": "fixed"},
        {"fullscreen": True},
        {"maximize": True},
        {"multimon": True},
    ],
)
def test_a_computer_whose_settings_choose_the_size_keeps_it(settings):
    assert window_arguments(profile(**settings), SessionWindow(1280, 800), []) == []


@pytest.mark.parametrize("option", ["/size:800x600", "/w:800", "/h:600", "+workarea", "/f"])
def test_a_size_in_the_extra_arguments_is_kept(option):
    assert window_arguments(profile(), SessionWindow(1280, 800), [option]) == []


def test_another_option_starting_with_f_does_not_count_as_full_screen():
    assert window_arguments(profile(), SessionWindow(1280, 800), ["/fonts"]) == ["/size:1280x800"]


def test_the_size_is_stored_per_computer(tmp_path):
    prefs = PreferencesStore(tmp_path)
    assert prefs.session_window("dev") is None
    prefs.save_session_window("dev", SessionWindow(1280, 800))
    prefs.save_session_window("other", SessionWindow(900, 700))
    assert prefs.session_window("dev") == SessionWindow(1280, 800)
    assert PreferencesStore(tmp_path).session_window("other") == SessionWindow(900, 700)


def test_maximizing_keeps_the_size_from_before(tmp_path):
    prefs = PreferencesStore(tmp_path)
    prefs.save_session_window("dev", SessionWindow(1280, 800))
    prefs.save_session_window("dev", SessionWindow(1920, 1050, maximized=True))
    assert prefs.session_window("dev") == SessionWindow(1280, 800, maximized=True)
    prefs.save_session_window("dev", SessionWindow(1000, 700))
    assert prefs.session_window("dev") == SessionWindow(1000, 700)


def test_a_forgotten_computer_has_no_size(tmp_path):
    prefs = PreferencesStore(tmp_path)
    prefs.save_session_window("dev", SessionWindow(1280, 800))
    prefs.forget_session_window("dev")
    assert prefs.session_window("dev") is None


def test_a_damaged_stored_size_is_ignored(tmp_path):
    (tmp_path / "krdpc.conf").write_text("[sessions]\ndev\\width=wide\ndev\\height=2\n")
    assert PreferencesStore(tmp_path).session_window("dev") is None


# ---- the launcher -------------------------------------------------------------------------


def launcher_with(store, tmp_path, remembered, seen, body="exit 0"):
    kept = []
    launcher = Launcher(
        store,
        find_executable=lambda _name: fake_xfreerdp(tmp_path, body),
        remembering_windows=lambda: True,
        recall_window=lambda _profile: remembered,
        remember_window=lambda prof, window: kept.append((prof.id, window)),
        read_window=lambda _pid: seen,
    )
    return launcher, kept


def test_the_remembered_size_is_given_to_xfreerdp(qapp, store, tmp_path):
    computer = store.save(Profile(name="Dev", server="10.0.0.5", extra_arguments="/cert:ignore"))
    launcher, _ = launcher_with(store, tmp_path, SessionWindow(1280, 800), None)
    launcher.connect_to(computer)
    wait_for(lambda: launcher.active_count() == 0)
    lines = (tmp_path / "stdin").read_text().split()
    assert "/size:1280x800" in lines
    assert lines.index("/size:1280x800") < lines.index("/cert:ignore")


def test_the_last_size_seen_is_kept_when_the_session_ends(qapp, store, tmp_path):
    computer = store.save(Profile(name="Dev", server="10.0.0.5"))
    seen = SessionWindow(1111, 777)
    launcher, kept = launcher_with(store, tmp_path, None, seen, body="sleep 1")
    launcher.connect_to(computer)
    wait_for(lambda: launcher.active_count() == 0)
    assert kept == [(computer.id, seen)]


def test_a_session_with_no_window_keeps_nothing(qapp, store, tmp_path):
    computer = store.save(Profile(name="Dev", server="10.0.0.5"))
    launcher, kept = launcher_with(store, tmp_path, None, None, body="sleep 1")
    launcher.connect_to(computer)
    wait_for(lambda: launcher.active_count() == 0)
    assert kept == []


def test_nothing_is_read_or_given_when_remembering_is_off(qapp, store, tmp_path):
    computer = store.save(Profile(name="Dev", server="10.0.0.5"))
    reads = []
    launcher = Launcher(
        store,
        find_executable=lambda _name: fake_xfreerdp(tmp_path, "sleep 1"),
        remembering_windows=lambda: False,
        recall_window=lambda _profile: SessionWindow(1280, 800),
        read_window=lambda pid: reads.append(pid),
    )
    launcher.connect_to(computer)
    wait_for(lambda: launcher.active_count() == 0)
    assert "/size:1280x800" not in (tmp_path / "stdin").read_text()
    assert reads == []


def test_the_sdl_client_is_left_alone(qapp, store, tmp_path):
    computer = store.save(Profile(name="Dev", server="10.0.0.5"))
    script = tmp_path / "sdl-freerdp"
    script.write_text(f'#!/bin/sh\ncat > "{tmp_path}/stdin"\nsleep 1\n')
    script.chmod(0o755)
    reads = []
    launcher = Launcher(
        store,
        find_executable=lambda name: str(script) if name == "sdl-freerdp" else None,
        has_x11_display=lambda: False,
        remembering_windows=lambda: True,
        recall_window=lambda _profile: SessionWindow(1280, 800),
        read_window=lambda pid: reads.append(pid),
    )
    launcher.connect_to(computer)
    wait_for(lambda: launcher.active_count() == 0)
    assert "/size:1280x800" not in (tmp_path / "stdin").read_text()
    assert reads == []


# ---- reading a real window ----------------------------------------------------------------


def test_without_a_display_there_is_no_window(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    assert read_session_window(1) is None


def test_without_libx11_there_is_no_window(monkeypatch):
    monkeypatch.setattr(sessionwindow.ctypes.util, "find_library", lambda _name: None)
    assert read_session_window(1) is None


def test_a_loader_failure_is_not_an_error(monkeypatch):
    def fail(_name):
        raise OSError("no such library")

    monkeypatch.setattr(sessionwindow.ctypes, "CDLL", fail)
    assert read_session_window(1) is None
