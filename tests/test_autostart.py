from krdpc import autostart


def test_off_until_asked(config_home):
    assert not autostart.is_enabled()
    assert autostart.autostart_file() == config_home / "autostart" / "krdpc.desktop"


def test_turning_it_on_writes_a_desktop_entry(config_home):
    autostart.set_enabled(True)
    text = autostart.autostart_file().read_text()
    assert autostart.is_enabled()
    assert text.startswith("[Desktop Entry]\n")
    assert "Type=Application" in text and "Terminal=false" in text
    assert "\nExec=" in text
    assert [p.name for p in autostart.autostart_file().parent.iterdir()] == ["krdpc.desktop"]


def test_turning_it_off_removes_it_and_is_repeatable(config_home):
    autostart.set_enabled(True)
    autostart.set_enabled(False)
    assert not autostart.is_enabled()
    autostart.set_enabled(False)


def test_a_command_path_with_spaces_is_quoted(monkeypatch):
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: "/opt/my apps/krdpc")
    assert 'Exec="/opt/my apps/krdpc"' in autostart.entry_text()


def test_falls_back_to_the_bare_command(monkeypatch):
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: None)
    assert "Exec=krdpc\n" in autostart.entry_text()
