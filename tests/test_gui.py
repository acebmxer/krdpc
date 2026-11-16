import pytest
from PySide6.QtWidgets import QMessageBox

from krdpc.editdialog import EditDialog
from krdpc.launcher import Launcher
from krdpc.mainwindow import MainWindow
from krdpc.profile import Profile


def computer(name, server="10.0.0.5", **kwargs):
    return Profile(name=name, server=server, **kwargs)


@pytest.fixture
def window(qapp, store):
    store.save(computer("Seedbox", "10.0.0.6", group="Home", labels="media"))
    store.save(computer("dev fedora", "10.0.0.5", last_used="2026-11-15T19:37:03"))
    store.save(computer("WorkPC", "10.1.0.11"))
    win = MainWindow(store, launcher=Launcher(store, find_executable=lambda _name: None))
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
    monkeypatch.setattr(window._launcher, "connect_to", seen.append)
    select(window, "WorkPC")
    window.connect_action.trigger()
    assert [p.name for p in seen] == ["WorkPC"]


def test_double_click_connects_too(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window._launcher, "connect_to", seen.append)
    window._view.activated.emit(window._proxy.index(1, 0))
    assert [p.name for p in seen] == ["Seedbox"]


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
    monkeypatch.setattr(window._launcher, "connect_to", seen.append)
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
