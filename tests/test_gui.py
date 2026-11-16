import dataclasses

import pytest
from PySide6.QtWidgets import QMessageBox

from krdpc.certificate import CertificateInfo
from krdpc.editdialog import EditDialog
from krdpc.launcher import Launcher
from krdpc.mainwindow import MainWindow
from krdpc.passworddialog import PasswordDialog
from krdpc.passwords import PasswordStore, password_key
from krdpc.preferencesdialog import PreferencesDialog
from krdpc.profile import Profile


def computer(name, server="10.0.0.5", **kwargs):
    return Profile(name=name, server=server, **kwargs)


class Asked:
    """Stands in for the password dialog: records that it was shown and answers."""

    def __init__(self, monkeypatch, password="pw", remember=False, accept=True):
        self.shown = 0
        self._answer = (password, remember, accept)
        monkeypatch.setattr(PasswordDialog, "exec", lambda dialog: self._exec())
        monkeypatch.setattr(PasswordDialog, "password", lambda dialog: self._answer[0])
        monkeypatch.setattr(PasswordDialog, "remember", lambda dialog: self._answer[1])

    def _exec(self):
        self.shown += 1
        accepted = PasswordDialog.DialogCode.Accepted
        return accepted if self._answer[2] else PasswordDialog.DialogCode.Rejected


@pytest.fixture
def asked(monkeypatch):
    return Asked(monkeypatch)


@pytest.fixture
def window(qapp, store, asked):
    store.save(computer("Seedbox", "10.0.0.6", group="Home", labels="media"))
    store.save(computer("dev fedora", "10.0.0.5", last_used="2026-11-15T19:37:03"))
    store.save(computer("WorkPC", "10.1.0.11"))
    win = MainWindow(
        store,
        launcher=Launcher(store, find_executable=lambda _name: None),
        passwords=PasswordStore(),
    )
    win.show()
    return win


def select(win, name):
    win._view.selectionModel().clear()
    for row in range(win._proxy.rowCount()):
        if win._proxy.index(row, 0).data() == name:
            win._view.setCurrentIndex(win._proxy.index(row, 0))
            return
    raise AssertionError(name)


def test_lists_computers_sorted_by_name_ignoring_case(window):
    assert window.visible_names() == ["dev fedora", "Seedbox", "WorkPC"]
    assert window._total.text() == "Total 3 items."


def test_columns_show_the_remmina_fields(window):
    proxy = window._proxy
    row = [proxy.index(0, column).data() for column in range(6)]
    assert row == ["dev fedora", "", "", "10.0.0.5", "RDP", "2026-11-15 - 19:37:03"]


def test_search_filters_on_name_group_labels_and_server(window):
    window._search.setText("home")
    assert window.visible_names() == ["Seedbox"]
    assert window._total.text() == "Total 1 item."
    window._search.setText("10.1.")
    assert window.visible_names() == ["WorkPC"]
    window._search.setText("MEDIA")
    assert window.visible_names() == ["Seedbox"]
    window._search.setText("nothing like this")
    assert window.visible_names() == []
    assert window._total.text() == "Total 0 items."
    window._search.clear()
    assert len(window.visible_names()) == 3


def test_search_row_toggles_and_clears(window):
    assert window._search_row.isHidden()
    window.search_action.setChecked(True)
    assert not window._search_row.isHidden()
    window._search.setText("seed")
    window.search_action.setChecked(False)
    assert window._search_row.isHidden()
    assert len(window.visible_names()) == 3


def test_actions_follow_the_selection(window):
    window._view.selectionModel().clear()
    window._update_actions()
    assert not window.edit_action.isEnabled()
    select(window, "WorkPC")
    assert window.edit_action.isEnabled()
    assert window.delete_action.isEnabled()


def test_duplicate_selects_the_copy(window, store):
    select(window, "Seedbox")
    window.duplicate_action.trigger()
    assert "COPY Seedbox" in window.visible_names()
    assert store.get(window.selected_id()).name == "COPY Seedbox"


def test_delete_asks_first(window, store, monkeypatch):
    select(window, "WorkPC")
    answer = {"value": QMessageBox.StandardButton.Cancel}
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answer["value"])
    window.delete_action.trigger()
    assert len(store.list()) == 3
    answer["value"] = QMessageBox.StandardButton.Yes
    window.delete_action.trigger()
    assert [p.name for p in store.list()].count("WorkPC") == 0
    assert "WorkPC" not in window.visible_names()


def test_new_computer_is_saved_and_selected(window, store, monkeypatch):
    def fill_and_accept(dialog):
        dialog._widgets["name"].setText("Laptop")
        dialog._widgets["server"].setText("192.168.1.9")
        return EditDialog.DialogCode.Accepted

    monkeypatch.setattr(EditDialog, "exec", fill_and_accept)
    window.new_action.trigger()
    assert "Laptop" in window.visible_names()
    assert store.get(window.selected_id()).server == "192.168.1.9"


def test_cancelled_dialog_saves_nothing(window, store, monkeypatch):
    monkeypatch.setattr(EditDialog, "exec", lambda dialog: EditDialog.DialogCode.Rejected)
    window.new_action.trigger()
    assert len(store.list()) == 3


def test_edit_keeps_id_and_last_used(window, store, monkeypatch):
    select(window, "dev fedora")
    before = store.get(window.selected_id())

    def rename(dialog):
        dialog._widgets["name"].setText("Dev Fedora 2")
        return EditDialog.DialogCode.Accepted

    monkeypatch.setattr(EditDialog, "exec", rename)
    window.edit_action.trigger()
    after = store.get(before.id)
    assert (after.name, after.last_used) == ("Dev Fedora 2", before.last_used)


def test_activating_a_row_requests_a_connection(window, monkeypatch):
    monkeypatch.setattr(window._launcher, "connect_to", lambda profile: None)
    seen = []
    window.connect_requested.connect(seen.append)
    index = window._proxy.index(1, 0)
    window._view.activated.emit(index)
    assert seen == [index.data(256)]


def test_dialog_roundtrips_a_profile(qapp):
    original = computer(
        "A",
        "b",
        notes="x\ny",
        sound="local",
        resolution_mode="fixed",
        resolution_width=1280,
        resolution_height=720,
        ignore_certificate=True,
        reconnect_attempts=3,
        id="a",
        last_used="2026-11-15T19:37:03",
    )
    assert EditDialog(original).profile() == original


def test_dialog_fixed_size_enables_the_size_boxes(qapp):
    dialog = EditDialog(computer("A"))
    assert not dialog._widgets["resolution_width"].isEnabled()
    dialog._widgets["resolution_mode"].setCurrentIndex(1)
    assert dialog._widgets["resolution_width"].isEnabled()


def test_dialog_lock_disables_everything_but_the_lock(qapp):
    dialog = EditDialog(computer("A", locked=True))
    assert not dialog._widgets["name"].isEnabled()
    assert dialog._widgets["locked"].isEnabled()
    dialog._widgets["locked"].setChecked(False)
    assert dialog._widgets["name"].isEnabled()
    assert not dialog._widgets["resolution_width"].isEnabled()  # dynamic mode


def test_dialog_refuses_to_save_without_name_or_server(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: shown.append(a[2]))
    dialog = EditDialog(Profile())
    dialog.accept()
    assert dialog.result() != EditDialog.DialogCode.Accepted
    assert "name" in shown[0] and "server" in shown[0]


def test_connect_action_hands_the_profile_to_the_launcher(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: seen.append(args))
    select(window, "WorkPC")
    window.connect_action.trigger()
    assert [(args[0].name, args[1:]) for args in seen] == [("WorkPC", ("pw", ""))]


def test_double_click_connects_too(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: seen.append(args))
    window._view.activated.emit(window._proxy.index(1, 0))
    assert [args[0].name for args in seen] == ["Seedbox"]


def test_a_failed_connection_is_shown_with_the_computer_name(window):
    select(window, "WorkPC")
    window.connect_action.trigger()  # no xfreerdp in the test launcher
    box = window._failure_box
    assert box.windowTitle() == "Cannot connect to WorkPC"
    assert "xfreerdp was not found" in box.text()


def test_failures_are_shown_one_at_a_time_and_never_twice(window):
    pid = window._store.list()[0].id
    window._launcher.failed.emit(pid, "first problem\n\nlog line")
    window._launcher.failed.emit(pid, "second problem")
    window._launcher.failed.emit(pid, "second problem")  # already waiting
    window._launcher.failed.emit(pid, "first problem\n\nlog line")  # already showing
    first = window._failure_box
    assert first.text() == "first problem"
    assert first.detailedText() == "log line"
    first.accept()
    second = window._failure_box
    assert second is not first and second.text() == "second problem"
    second.accept()
    assert window._failure_box is None


def test_asks_before_a_second_connection_to_the_same_computer(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: seen.append(args))
    monkeypatch.setattr(window._launcher, "active_count_for", lambda _id: 1)
    answer = {"value": QMessageBox.StandardButton.Cancel}
    monkeypatch.setattr(QMessageBox, "question", lambda *a: answer["value"])
    select(window, "WorkPC")
    window.connect_action.trigger()
    assert seen == []
    answer["value"] = QMessageBox.StandardButton.Yes
    window.connect_action.trigger()
    assert len(seen) == 1


def test_starting_shows_a_status_message(window):
    pid = window._store.list()[0].id
    window._launcher.started.emit(pid)
    assert "Started" in window.statusBar().currentMessage()


def test_connecting_refreshes_last_used(window, store):
    profile = store.list()[0]
    store.touch_last_used(profile.id)
    window._launcher.started.emit(profile.id)
    assert any(window._proxy.index(r, 5).data() for r in range(3))


def test_closing_with_open_connections_asks(window, monkeypatch):
    monkeypatch.setattr(window._launcher, "active_count", lambda: 2)
    stopped = []
    monkeypatch.setattr(window._launcher, "stop_all", lambda: stopped.append(True))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    assert not window.close()
    assert stopped == []
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Close)
    assert window.close()
    assert stopped == [True]


def profile_named(window, name):
    return next(p for p in window._store.list() if p.name == name)


def test_cancelling_the_password_box_does_not_connect(window, monkeypatch):
    Asked(monkeypatch, accept=False)
    seen = []
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: seen.append(args))
    select(window, "WorkPC")
    window.connect_action.trigger()
    assert seen == []


def test_remembering_saves_to_the_wallet_and_stops_asking(window, monkeypatch, wallet):
    asked = Asked(monkeypatch, password="s3cret", remember=True)
    seen = []
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: seen.append(args))
    select(window, "WorkPC")
    window.connect_action.trigger()
    work = profile_named(window, "WorkPC")
    assert work.remember_password is True
    assert wallet.items[("krdpc", password_key(work.id))] == "s3cret"
    assert "s3cret" not in (window._store.directory / f"{work.id}.ini").read_text()
    window.connect_action.trigger()  # second time: from the wallet
    assert asked.shown == 1
    assert seen[1][1:] == ("s3cret", "")


def test_not_remembering_forgets_an_earlier_password(window, monkeypatch, wallet):
    Asked(monkeypatch, password="one", remember=True)
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: None)
    select(window, "WorkPC")
    window.connect_action.trigger()
    work = profile_named(window, "WorkPC")
    # The saved password is not used while the tick is gone; asking again unticked removes it.
    window._store.save(dataclasses.replace(work, remember_password=False))
    Asked(monkeypatch, password="two", remember=False)
    window.connect_action.trigger()
    assert ("krdpc", password_key(work.id)) not in wallet.items


def test_a_refused_sign_in_forgets_the_remembered_password(window, monkeypatch, wallet):
    Asked(monkeypatch, password="old", remember=True)
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: None)
    select(window, "WorkPC")
    window.connect_action.trigger()
    work = profile_named(window, "WorkPC")
    window._launcher.login_rejected.emit(work.id)
    assert ("krdpc", password_key(work.id)) not in wallet.items


def test_deleting_a_computer_removes_its_password(window, monkeypatch, wallet):
    Asked(monkeypatch, password="x", remember=True)
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: None)
    select(window, "WorkPC")
    window.connect_action.trigger()
    work = profile_named(window, "WorkPC")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    select(window, "WorkPC")
    window.delete_action.trigger()
    assert ("krdpc", password_key(work.id)) not in wallet.items


def certificate(thumbprint="ab" * 32, changed=False):
    return CertificateInfo("", "C = XX", "C = XX", "Jul 1", "Jul 2", thumbprint, changed)


def test_trusting_a_certificate_saves_it_and_tries_again(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: seen.append(args))
    select(window, "WorkPC")
    window.connect_action.trigger()
    work = profile_named(window, "WorkPC")
    monkeypatch.setattr(window, "_trust_certificate", lambda profile, info: True)
    window._launcher.certificate_untrusted.emit(work.id, certificate())
    assert profile_named(window, "WorkPC").trusted_certificate == "ab" * 32
    assert len(seen) == 2
    assert seen[1][0].trusted_certificate == "ab" * 32
    assert seen[1][1:] == ("pw", "")


def test_declining_a_certificate_changes_nothing(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: seen.append(args))
    select(window, "WorkPC")
    window.connect_action.trigger()
    work = profile_named(window, "WorkPC")
    monkeypatch.setattr(window, "_trust_certificate", lambda profile, info: False)
    window._launcher.certificate_untrusted.emit(work.id, certificate())
    assert profile_named(window, "WorkPC").trusted_certificate == ""
    assert len(seen) == 1


def test_the_eye_shows_and_hides_what_was_typed(qapp):
    from PySide6.QtWidgets import QLineEdit

    dialog = PasswordDialog(computer("A", gateway_server="gw"))
    for field in (dialog._password, dialog._gateway):
        assert field.echoMode() == QLineEdit.EchoMode.Password
        eye = field.actions()[0]
        eye.setChecked(True)
        assert field.echoMode() == QLineEdit.EchoMode.Normal
        eye.setChecked(False)
        assert field.echoMode() == QLineEdit.EchoMode.Password


def test_the_list_icons_are_24_pixels(window):
    size = window._view.iconSize()
    assert (size.width(), size.height()) == (24, 24)


# ---- error paths and small corners ------------------------------------------------------


def test_an_unreadable_wallet_falls_back_to_asking(window, monkeypatch, wallet):
    import keyring

    asked = Asked(monkeypatch, password="typed")
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: None)
    select(window, "WorkPC")
    work = profile_named(window, "WorkPC")
    window._store.save(dataclasses.replace(work, remember_password=True))

    def locked(*_args):
        raise RuntimeError("wallet is locked")

    monkeypatch.setattr(keyring, "get_password", locked)
    window.connect_action.trigger()
    assert asked.shown == 1
    assert "wallet is locked" in window.statusBar().currentMessage()


def test_a_wallet_that_cannot_save_is_reported_and_nothing_is_remembered(window, monkeypatch):
    import keyring

    Asked(monkeypatch, password="x", remember=True)
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: shown.append(a[2]))
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: None)

    def refuse(*_args):
        raise RuntimeError("no wallet")

    monkeypatch.setattr(keyring, "set_password", refuse)
    select(window, "WorkPC")
    window.connect_action.trigger()
    assert "no wallet" in shown[0]
    assert profile_named(window, "WorkPC").remember_password is False


def test_a_wallet_that_cannot_forget_is_reported(window, monkeypatch):
    import keyring

    def refuse(*_args):
        raise RuntimeError("cannot delete")

    monkeypatch.setattr(keyring, "delete_password", refuse)
    window._forget_passwords(profile_named(window, "WorkPC").id)
    assert "cannot delete" in window.statusBar().currentMessage()


def test_connecting_to_a_computer_deleted_elsewhere_just_refreshes(window, monkeypatch, store):
    seen = []
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: seen.append(args))
    select(window, "WorkPC")
    store.delete(window.selected_id())
    window.connect_action.trigger()
    assert seen == [] and "WorkPC" not in window.visible_names()


def test_started_for_an_unknown_computer_is_ignored(window):
    window._launcher.started.emit("long-gone")


def test_unticking_remember_in_the_edit_dialog_forgets_the_password(window, monkeypatch, wallet):
    Asked(monkeypatch, password="keep", remember=True)
    monkeypatch.setattr(window._launcher, "connect_to", lambda *args: None)
    select(window, "WorkPC")
    window.connect_action.trigger()
    work = profile_named(window, "WorkPC")
    assert ("krdpc", password_key(work.id)) in wallet.items

    def untick(dialog):
        dialog._widgets["remember_password"].setChecked(False)
        return EditDialog.DialogCode.Accepted

    monkeypatch.setattr(EditDialog, "exec", untick)
    window.edit_action.trigger()
    assert ("krdpc", password_key(work.id)) not in wallet.items


def click_button(box, index):
    box.buttons()[index].click()


def test_the_certificate_question_names_a_new_certificate(window, monkeypatch):
    texts = []

    def answer(box):
        texts.append((box.text(), box.informativeText()))
        click_button(box, 0)  # "Trust and connect"

    monkeypatch.setattr(QMessageBox, "exec", answer)
    assert window._trust_certificate(profile_named(window, "WorkPC"), certificate()) is True
    text, details = texts[0]
    assert "cannot be verified" in text and "WARNING" not in text
    assert "SHA-256: ab:ab:ab" in details and "Subject: C = XX" in details


def test_the_certificate_question_warns_when_it_changed(window, monkeypatch):
    texts = []

    def answer(box):
        texts.append(box.text())
        click_button(box, 1)  # Cancel

    monkeypatch.setattr(QMessageBox, "exec", answer)
    work = profile_named(window, "WorkPC")
    assert window._trust_certificate(work, certificate(changed=True)) is False
    trusted_before = dataclasses.replace(work, trusted_certificate="cd" * 32)
    assert window._trust_certificate(trusted_before, certificate()) is False
    assert all("WARNING" in text for text in texts)


def test_the_protocol_filter(window):
    window._proxy.set_protocol("VNC")
    assert window.visible_names() == []
    window._proxy.set_protocol("RDP")
    assert len(window.visible_names()) == 3


def test_the_right_click_menu(window):
    menu = window._context_menu()
    assert [a.text() for a in menu.actions() if a.text()] == [
        "Connect",
        "Edit…",
        "Duplicate",
        "Delete…",
    ]


def test_right_clicking_empty_space_opens_no_menu(window, monkeypatch):
    from PySide6.QtCore import QPoint

    monkeypatch.setattr(window, "_context_menu", lambda: pytest.fail("a menu was opened"))
    window._show_context_menu(QPoint(5, 5000))


def test_the_tray_menu_and_clicks(window, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    window._preferences.show_tray = True
    window._apply_preferences()
    window.show()
    window._update_tray_menu()
    assert window._tray_toggle.text() == "Hide krdpc"
    window._tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert not window.isVisible()
    window._update_tray_menu()
    assert window._tray_toggle.text() == "Show krdpc"
    window._tray_activated(QSystemTrayIcon.ActivationReason.Context)  # right-click: ignored here
    assert not window.isVisible()
    opened = []
    monkeypatch.setattr(window, "new_profile", lambda: opened.append(True))
    window._new_from_tray()
    assert window.isVisible() and opened == [True]


def test_quitting_can_be_cancelled_while_connections_are_open(window, monkeypatch):
    monkeypatch.setattr(window._launcher, "active_count", lambda: 1)
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    assert window.quit() is False
    assert window._quitting is False


def test_start_at_login_that_cannot_be_written_is_reported(window, monkeypatch):
    from krdpc import autostart
    from krdpc.preferences import Preferences

    def refuse(_enabled):
        raise OSError("read-only folder")

    shown = []
    monkeypatch.setattr(autostart, "set_enabled", refuse)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: shown.append(a[2]))
    monkeypatch.setattr(PreferencesDialog, "exec", lambda d: PreferencesDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        PreferencesDialog, "preferences", lambda d: Preferences(start_at_login=True)
    )
    window.preferences_action.trigger()
    assert "read-only folder" in shown[0]
