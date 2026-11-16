import os

import pytest
from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QMessageBox

from krdpc.launcher import Launcher
from krdpc.mainwindow import MainWindow
from krdpc.passwords import PasswordStore
from krdpc.preferences import Preferences, PreferencesStore, is_program
from krdpc.preferencesdialog import PreferencesDialog
from krdpc.profile import Profile


@pytest.fixture
def prefs(tmp_path):
    return PreferencesStore(tmp_path)


def test_defaults_when_nothing_is_saved(prefs):
    assert prefs.load() == Preferences()
    assert Preferences().icon_pixels() == 24


def test_roundtrip(prefs):
    chosen = Preferences(
        icon_size="large", confirm_delete=False, remember_window=False, xfreerdp_path="/bin/true"
    )
    prefs.save(chosen)
    assert prefs.load() == chosen
    assert chosen.icon_pixels() == 32


def test_tray_settings_roundtrip(prefs):
    chosen = Preferences(
        show_tray=True, close_to_tray=True, start_minimised=True, start_at_login=True
    )
    prefs.save(chosen)
    assert prefs.load() == chosen


def test_tray_only_options_are_dropped_without_the_tray(prefs):
    prefs.save(Preferences(show_tray=False, close_to_tray=True, start_minimised=True))
    loaded = prefs.load()
    assert (loaded.close_to_tray, loaded.start_minimised) == (False, False)
    assert Preferences(show_tray=True, close_to_tray=True).normalised().close_to_tray is True


def test_a_bad_icon_size_falls_back_to_the_default(prefs, tmp_path):
    (tmp_path / "krdpc.conf").write_text("[General]\nicon_size=huge\nconfirm_delete=maybe\n")
    loaded = prefs.load()
    assert loaded.icon_size == "medium"
    assert loaded.confirm_delete is True


def test_the_settings_file_is_not_mistaken_for_a_computer(tmp_path):
    from krdpc.store import ProfileStore

    PreferencesStore(tmp_path).save(Preferences(icon_size="small"))
    assert ProfileStore(tmp_path).list() == []


def test_window_state_roundtrip(prefs):
    assert prefs.window() is None
    prefs.save_window(QByteArray(b"geometry"), QByteArray(b"columns"))
    geometry, columns = prefs.window()
    assert (bytes(geometry), bytes(columns)) == (b"geometry", b"columns")


def test_is_program(tmp_path):
    script = tmp_path / "prog"
    script.write_text("#!/bin/sh\n")
    assert not is_program(str(script))
    script.chmod(0o755)
    assert is_program(str(script))
    assert not is_program(str(tmp_path))
    assert not is_program(str(tmp_path / "missing"))


def test_dialog_returns_what_was_chosen(qapp):
    dialog = PreferencesDialog(Preferences())
    dialog._icon_size.setCurrentIndex(dialog._icon_size.findData("small"))
    dialog._confirm_delete.setChecked(False)
    dialog._xfreerdp.setText("  /usr/bin/xfreerdp  ")
    chosen = dialog.preferences()
    assert (chosen.icon_size, chosen.confirm_delete) == ("small", False)
    assert chosen.xfreerdp_path == "/usr/bin/xfreerdp"
    assert chosen.remember_window is True


def test_dialog_refuses_a_location_that_is_not_a_program(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: shown.append(a[2]))
    dialog = PreferencesDialog(Preferences(xfreerdp_path="/no/such/xfreerdp"))
    dialog.accept()
    assert dialog.result() != PreferencesDialog.DialogCode.Accepted
    assert "not a program" in shown[0]


@pytest.fixture
def window(qapp, store, monkeypatch):
    store.save(Profile(name="One", server="10.0.0.1"))
    store.save(Profile(name="Two", server="10.0.0.2"))

    def make():
        return MainWindow(
            store,
            launcher=Launcher(store, find_executable=lambda _name: None),
            passwords=PasswordStore(),
        )

    return make


def test_the_icon_size_follows_the_preference(window):
    win = window()
    assert win._view.iconSize().width() == 24
    win._preferences.icon_size = "large"
    win._apply_preferences()
    assert win._view.iconSize().width() == 32


def test_the_menu_opens_preferences_and_applies_them(window, monkeypatch):
    win = window()
    changed = Preferences(icon_size="small", confirm_delete=False)
    monkeypatch.setattr(
        PreferencesDialog, "exec", lambda dialog: PreferencesDialog.DialogCode.Accepted
    )
    monkeypatch.setattr(PreferencesDialog, "preferences", lambda dialog: changed)
    win.preferences_action.trigger()
    assert win._view.iconSize().width() == 16
    assert win._preferences_store.load() == changed
    assert window()._preferences == changed  # and the next start sees it


def select_first(win):
    win._view.setCurrentIndex(win._proxy.index(0, 0))


def test_delete_asks_unless_turned_off(window, monkeypatch, store):
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a: asked.append(a) or QMessageBox.StandardButton.Yes
    )
    win = window()
    select_first(win)
    win.delete_action.trigger()
    assert len(asked) == 1 and len(store.list()) == 1
    win._preferences.confirm_delete = False
    select_first(win)
    win.delete_action.trigger()
    assert len(asked) == 1 and store.list() == []


def test_the_chosen_xfreerdp_is_used(window, tmp_path):
    win = window()
    program = tmp_path / "my-xfreerdp"
    program.write_text("#!/bin/sh\n")
    program.chmod(0o755)
    win._preferences.xfreerdp_path = str(program)
    assert win._find_xfreerdp("xfreerdp") == str(program)
    win._preferences.xfreerdp_path = str(tmp_path / "gone")
    assert win._find_xfreerdp("xfreerdp") is None
    win._preferences.xfreerdp_path = ""
    assert win._find_xfreerdp("sh") == os.popen("command -v sh").read().strip()


def test_window_size_and_columns_are_remembered(window):
    first = window()
    first.resize(700, 400)  # the test screen is only 800 px wide
    first._view.setColumnWidth(0, 333)
    first.close()
    second = window()
    assert second._view.columnWidth(0) == 333
    assert second.size().width() == 700


def test_window_is_not_remembered_when_turned_off(window):
    first = window()
    first._preferences.remember_window = False
    first._view.setColumnWidth(0, 333)
    first.close()
    assert first._preferences_store.window() is None
    assert window()._view.columnWidth(0) != 333


def test_dialog_tray_options_follow_the_tray_tick(qapp):
    dialog = PreferencesDialog(Preferences(), tray_available=True)
    assert not dialog._close_to_tray.isEnabled() and not dialog._start_minimised.isEnabled()
    dialog._show_tray.setChecked(True)
    assert dialog._close_to_tray.isEnabled() and dialog._start_minimised.isEnabled()
    dialog._close_to_tray.setChecked(True)
    dialog._start_at_login.setChecked(True)
    chosen = dialog.preferences()
    assert (chosen.show_tray, chosen.close_to_tray, chosen.start_at_login) == (True, True, True)
    dialog._show_tray.setChecked(False)
    assert dialog.preferences().close_to_tray is False


def test_dialog_without_a_system_tray(qapp):
    dialog = PreferencesDialog(Preferences(show_tray=True), tray_available=False)
    assert not dialog._show_tray.isEnabled()
    assert dialog.preferences().show_tray is False


@pytest.fixture
def tray(monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))


def test_the_tray_icon_comes_and_goes_with_the_preference(window, tray):
    win = window()
    assert not win.has_tray()
    win._preferences.show_tray = True
    win._apply_preferences()
    assert win.has_tray()
    win._preferences.show_tray = False
    win._apply_preferences()
    assert not win.has_tray()


def test_no_tray_icon_when_the_desktop_has_none(window):
    win = window()
    win._preferences.show_tray = True
    win._apply_preferences()
    assert not win.has_tray()  # the test screen has no tray
    assert not win.starts_hidden()


def test_closing_goes_to_the_tray_and_quit_really_quits(window, tray):
    win = window()
    win._preferences.show_tray = True
    win._preferences.close_to_tray = True
    win._apply_preferences()
    win.show()
    assert win.close() is False and not win.isVisible()  # hidden, still running
    win.show()
    assert win.quit() is True


def test_closing_just_closes_without_close_to_tray(window, tray):
    win = window()
    win._preferences.show_tray = True
    win._apply_preferences()
    win.show()
    assert win.close() is True


def test_start_hidden_needs_the_tray_and_the_preference(window, tray):
    win = window()
    win._preferences.start_minimised = True
    assert not win.starts_hidden()  # no tray icon yet
    win._preferences.show_tray = True
    win._apply_preferences()
    assert win.starts_hidden()


def test_the_tray_click_shows_and_hides_the_window(window, tray):
    win = window()
    win.show()
    win.toggle_window()
    assert not win.isVisible()
    win.toggle_window()
    assert win.isVisible()


def test_start_at_login_writes_and_removes_the_autostart_entry(window, monkeypatch):
    from krdpc import autostart

    win = window()
    on = Preferences(start_at_login=True)
    monkeypatch.setattr(PreferencesDialog, "exec", lambda d: PreferencesDialog.DialogCode.Accepted)
    monkeypatch.setattr(PreferencesDialog, "preferences", lambda d: on)
    win.preferences_action.trigger()
    assert autostart.is_enabled()
    off = Preferences(start_at_login=False)
    monkeypatch.setattr(PreferencesDialog, "preferences", lambda d: off)
    win.preferences_action.trigger()
    assert not autostart.is_enabled()
