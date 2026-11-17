"""Finding, downloading and installing a newer release (krdpc.updates and krdpc.updater)."""

import hashlib
import io
import json
import sys
import threading
import types

import pytest
from PySide6.QtCore import QCoreApplication, QProcess
from PySide6.QtWidgets import QMessageBox

from krdpc import __version__, updates
from krdpc.launcher import Launcher
from krdpc.mainwindow import MainWindow
from krdpc.passwords import PasswordStore
from krdpc.preferences import Preferences, PreferencesStore
from krdpc.preferencesdialog import PreferencesDialog
from krdpc.updater import Updater, run_in_thread
from krdpc.updates import Installed, Release, UpdateError

BASE = "https://github.com/acebmxer/krdpc/releases/download"


def release(tag, prerelease=None, files=("rpm", "deb", "arch")):
    version = tag.removeprefix("v")
    names = {
        "rpm": f"krdpc-{version}-1.noarch.rpm",
        "deb": f"krdpc_{version}_all.deb",
        "arch": f"krdpc-{version}-1-any.pkg.tar.zst",
    }
    assets = {names[kind]: f"{BASE}/{tag}/{names[kind]}" for kind in files}
    assets["SHA256SUMS"] = f"{BASE}/{tag}/SHA256SUMS"
    return Release(
        tag=tag,
        prerelease="-beta." in tag if prerelease is None else prerelease,
        page=f"https://github.com/acebmxer/krdpc/releases/tag/{tag}",
        assets=assets,
    )


# ---- versions -------------------------------------------------------------------


def test_versions_sort_with_a_beta_before_its_release():
    order = ["0.1.0-beta.1", "0.1.0-beta.2", "0.1.0-beta.10", "v0.1.0", "0.1.1-beta.1", "0.2.0"]
    keys = [updates.version_key(text) for text in order]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)


def test_odd_versions_are_not_versions():
    for text in ("", "latest", "0.1", "v0.1.0-rc.1", "0.1.0.dev0", "v0.1.0-beta"):
        assert updates.version_key(text) is None, text


# ---- what is installed ------------------------------------------------------------


def test_a_copy_from_a_clone_cannot_update_itself(monkeypatch):
    monkeypatch.setitem(sys.modules, "krdpc._package", None)  # import fails
    current = updates.installed()
    assert current == Installed(__version__, None)
    assert not current.can_update_itself


def test_a_packaged_copy_knows_its_release_and_format(monkeypatch):
    stamp = types.ModuleType("krdpc._package")
    stamp.RELEASE, stamp.FORMAT = "0.1.0-beta.3", "deb"
    monkeypatch.setitem(sys.modules, "krdpc._package", stamp)
    current = updates.installed()
    assert current == Installed("0.1.0-beta.3", "deb")
    assert current.can_update_itself


def test_a_damaged_stamp_is_not_trusted(monkeypatch):
    stamp = types.ModuleType("krdpc._package")
    stamp.RELEASE, stamp.FORMAT = "nonsense", "snap"
    monkeypatch.setitem(sys.modules, "krdpc._package", stamp)
    assert updates.installed() == Installed(__version__, None)


# ---- choosing a release -------------------------------------------------------------


def github_answer():
    def item(tag, prerelease=False, draft=False):
        found = release(tag, prerelease)
        return {
            "tag_name": tag,
            "prerelease": prerelease,
            "draft": draft,
            "html_url": found.page,
            "assets": [
                {"name": name, "browser_download_url": url} for name, url in found.assets.items()
            ],
        }

    return [
        item("v0.3.0", draft=True),
        item("v0.2.1-beta.1", prerelease=True),
        item("v0.2.0"),
        item("v0.2.0-beta.2", prerelease=True),
        item("not-a-version"),
        item("v0.1.0"),
    ]


def test_drafts_and_odd_tags_are_left_out():
    tags = [found.tag for found in updates.parse_releases(github_answer())]
    assert tags == ["v0.2.1-beta.1", "v0.2.0", "v0.2.0-beta.2", "v0.1.0"]
    assert updates.parse_releases({"message": "rate limited"}) == []


def test_only_stable_releases_unless_betas_are_wanted():
    found = updates.parse_releases(github_answer())
    assert updates.newest(found, "0.1.0", include_betas=False).tag == "v0.2.0"
    assert updates.newest(found, "0.1.0", include_betas=True).tag == "v0.2.1-beta.1"


def test_a_beta_user_is_offered_the_stable_release_of_that_version():
    found = updates.parse_releases(github_answer())
    assert updates.newest(found, "0.2.0-beta.2", include_betas=False).tag == "v0.2.0"


def test_nothing_is_offered_when_already_newest():
    found = updates.parse_releases(github_answer())
    assert updates.newest(found, "0.2.0", include_betas=False) is None
    assert updates.newest(found, "0.2.1-beta.1", include_betas=True) is None


def test_the_package_for_each_format():
    found = release("v0.2.0")
    assert found.package("rpm") == (
        "krdpc-0.2.0-1.noarch.rpm",
        f"{BASE}/v0.2.0/krdpc-0.2.0-1.noarch.rpm",
    )
    assert found.package("deb")[0] == "krdpc_0.2.0_all.deb"
    assert found.package("arch")[0] == "krdpc-0.2.0-1-any.pkg.tar.zst"
    assert found.package("snap") is None
    assert release("v0.2.0", files=("deb",)).package("rpm") is None


def test_files_from_anywhere_else_are_never_used():
    found = Release(
        tag="v0.2.0",
        prerelease=False,
        page="",
        assets={
            "krdpc-0.2.0-1.noarch.rpm": "https://example.com/krdpc-0.2.0-1.noarch.rpm",
            "SHA256SUMS": "https://example.com/SHA256SUMS",
        },
    )
    assert found.package("rpm") is None
    assert found.checksums() is None


def test_fetching_reads_githubs_answer(monkeypatch):
    seen = []

    def fake_open(url, accept="*/*"):
        seen.append((url, accept))
        return io.BytesIO(json.dumps(github_answer()).encode())

    monkeypatch.setattr(updates, "_open", fake_open)
    assert updates.fetch_releases()[0].tag == "v0.2.1-beta.1"
    assert seen == [(updates._API, "application/vnd.github+json")]


def test_an_unreadable_answer_is_a_plain_error(monkeypatch):
    monkeypatch.setattr(updates, "_open", lambda url, accept="*/*": io.BytesIO(b"<html>"))
    with pytest.raises(UpdateError, match="could not be read"):
        updates.fetch_releases()


def test_no_network_is_a_plain_error(monkeypatch):
    import urllib.error

    def refuse(request, timeout):
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(updates.urllib.request, "urlopen", refuse)
    with pytest.raises(UpdateError, match="Could not reach GitHub: Name or service not known"):
        updates.fetch_releases()


# ---- downloading ----------------------------------------------------------------------


class Answer(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


def serve(monkeypatch, package=b"package bytes" * 10000, sums=None):
    found = release("v0.2.0")
    name, url = found.package("rpm")
    if sums is None:
        sums = f"{hashlib.sha256(package).hexdigest()}  {name}\n0000  other\n"
    files = {url: package, found.checksums(): sums.encode()}
    monkeypatch.setattr(updates, "_open", lambda url, accept="*/*": Answer(files[url]))
    return found, package


def test_the_package_is_downloaded_and_checked(monkeypatch, tmp_path):
    found, package = serve(monkeypatch)
    progress = []
    path = updates.download(
        found, "rpm", tmp_path, lambda done, total: progress.append((done, total))
    )
    assert path == tmp_path / "krdpc-0.2.0-1.noarch.rpm"
    assert path.read_bytes() == package
    assert progress[-1] == (len(package), len(package))
    assert list(tmp_path.iterdir()) == [path]


def test_a_package_that_does_not_match_its_checksum_is_thrown_away(monkeypatch, tmp_path):
    found, _package = serve(monkeypatch, sums="0" * 64 + "  krdpc-0.2.0-1.noarch.rpm\n")
    with pytest.raises(UpdateError, match="did not match its checksum"):
        updates.download(found, "rpm", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_package_missing_from_the_checksums_is_not_downloaded(monkeypatch, tmp_path):
    found, _package = serve(monkeypatch, sums="")
    with pytest.raises(UpdateError, match="does not list"):
        updates.download(found, "rpm", tmp_path)
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_a_cancelled_download_leaves_nothing(monkeypatch, tmp_path):
    found, _package = serve(monkeypatch)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(updates.Cancelled):
        updates.download(found, "rpm", tmp_path, cancel=cancel)
    assert list(tmp_path.iterdir()) == []


def test_a_release_without_this_format_or_checksums_is_refused(tmp_path):
    with pytest.raises(UpdateError, match="no rpm package"):
        updates.download(release("v0.2.0", files=("deb",)), "rpm", tmp_path)
    found = release("v0.2.0")
    del found.assets["SHA256SUMS"]
    with pytest.raises(UpdateError, match="no SHA256SUMS"):
        updates.download(found, "rpm", tmp_path)


def test_checksum_lines_in_both_sha256sum_styles():
    digest = "a" * 64
    assert updates.expected_checksum(f"{digest}  krdpc.rpm\n", "krdpc.rpm") == digest
    assert updates.expected_checksum(f"{digest} *krdpc.rpm\n", "krdpc.rpm") == digest
    assert updates.expected_checksum(f"{digest}  krdpc.rpm.old\n", "krdpc.rpm") is None
    assert updates.expected_checksum("nothex  krdpc.rpm\n", "krdpc.rpm") is None


# ---- installing ------------------------------------------------------------------------


def test_each_format_installs_with_its_own_package_manager(tmp_path):
    path = tmp_path / "file"
    assert updates.install_command("rpm", path) == ["dnf", "install", "-y", str(path)]
    assert updates.install_command("deb", path) == ["apt-get", "install", "-y", str(path)]
    assert updates.install_command("arch", path) == ["pacman", "-U", "--noconfirm", str(path)]
    with pytest.raises(ValueError):
        updates.install_command("snap", path)


def test_the_command_to_type_by_hand():
    from pathlib import Path

    assert updates.manual_command("rpm", Path("/c/krdpc.rpm")) == "sudo dnf install /c/krdpc.rpm"
    assert (
        updates.manual_command("arch", Path("/my files/k.pkg.tar.zst"))
        == "sudo pacman -U '/my files/k.pkg.tar.zst'"
    )


# ---- the boxes ---------------------------------------------------------------------------


def now(work, done, failed):
    """Runs the background work straight away, so tests need no threads."""
    try:
        result = work()
    except UpdateError as error:
        failed(str(error))
    else:
        done(result)


class Boxes:
    """Records every message box instead of showing it, and clicks a chosen button."""

    def __init__(self, monkeypatch, click=None, answer=QMessageBox.StandardButton.No):
        self.shown = []
        self._click = click

        def record(kind):
            def show(_parent, title, text, *_rest):
                self.shown.append((kind, title, text))
                return answer

            return show

        for kind in ("information", "warning", "question"):
            monkeypatch.setattr(QMessageBox, kind, record(kind))
        monkeypatch.setattr(QMessageBox, "exec", lambda box: self._exec(box))

    def _exec(self, box):
        buttons = [button.text() for button in box.buttons()]
        self.shown.append(("box", box.windowTitle(), box.text(), buttons))
        for button in box.buttons():
            if button.text() == self._click:
                button.click()
        return 0


@pytest.fixture
def window(qapp, store):
    def make(**kwargs):
        return MainWindow(
            store,
            launcher=Launcher(store, find_executable=lambda _name: None),
            passwords=PasswordStore(),
            **kwargs,
        )

    return make


def updater_for(window, tmp_path, betas=False):
    win = window()
    updater = Updater(win, lambda: betas, runner=now, folder=tmp_path / "updates")
    return win, updater


def test_a_check_that_finds_nothing_says_so_only_when_asked(window, tmp_path, monkeypatch):
    boxes = Boxes(monkeypatch)
    monkeypatch.setattr(updates, "check", lambda betas: (Installed("0.2.0", "rpm"), None))
    _win, updater = updater_for(window, tmp_path)
    updater.check(quiet=True)
    assert boxes.shown == []
    updater.check()
    assert boxes.shown == [
        ("information", "Check for updates", "krdpc 0.2.0 is the newest version.")
    ]
    assert not updater.busy()


def test_a_failed_check_is_shown_only_when_asked(window, tmp_path, monkeypatch):
    boxes = Boxes(monkeypatch)

    def offline(_betas):
        raise UpdateError("Could not reach GitHub: no network")

    monkeypatch.setattr(updates, "check", offline)
    _win, updater = updater_for(window, tmp_path)
    updater.check(quiet=True)
    assert boxes.shown == []
    updater.check()
    assert boxes.shown == [("warning", "Check for updates", "Could not reach GitHub: no network")]


def test_the_beta_preference_is_passed_to_the_check(window, tmp_path, monkeypatch):
    Boxes(monkeypatch)
    asked = []
    monkeypatch.setattr(
        updates, "check", lambda betas: asked.append(betas) or (Installed("0.1.0", None), None)
    )
    for betas in (False, True):
        _win, updater = updater_for(window, tmp_path, betas)
        updater.check(quiet=True)
    assert asked == [False, True]


def test_a_packaged_copy_is_offered_the_update(window, tmp_path, monkeypatch):
    boxes = Boxes(monkeypatch, click="Later")
    newer = release("v0.2.0-beta.1")
    monkeypatch.setattr(updates, "check", lambda betas: (Installed("0.1.0", "rpm"), newer))
    win, updater = updater_for(window, tmp_path, betas=True)
    win.show()
    updater.check(quiet=True)
    kind, title, text, buttons = boxes.shown[0]
    assert (kind, title) == ("box", "Update available")
    assert text == "krdpc 0.2.0-beta.1 (a beta) is available. You have 0.1.0."
    assert sorted(buttons) == ["Later", "Update now", "What's new"]


def test_a_copy_from_a_clone_is_sent_to_the_releases_page(window, tmp_path, monkeypatch):
    boxes = Boxes(monkeypatch, click="Open the Releases page")
    opened = []
    monkeypatch.setattr(
        updates, "check", lambda betas: (Installed("0.1.0", None), release("v0.2.0"))
    )
    import krdpc.updater

    monkeypatch.setattr(
        krdpc.updater.QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )
    _win, updater = updater_for(window, tmp_path)
    updater.check()
    assert "Update now" not in boxes.shown[0][3]
    assert opened == ["https://github.com/acebmxer/krdpc/releases/tag/v0.2.0"]


def test_a_quiet_check_with_the_window_hidden_tells_the_tray(window, tmp_path, monkeypatch):
    boxes = Boxes(monkeypatch)
    monkeypatch.setattr(
        updates, "check", lambda betas: (Installed("0.1.0", "rpm"), release("v0.2.0"))
    )
    _win, updater = updater_for(window, tmp_path)
    found = []
    updater.found_quietly.connect(found.append)
    updater.check(quiet=True)
    assert found == ["0.2.0"]
    assert boxes.shown == []


def fake_pkexec(tmp_path, monkeypatch, code, output="installed"):
    """A stand-in for pkexec that records its arguments and exits with `code`."""
    script = tmp_path / "pkexec"
    log = tmp_path / "pkexec.args"
    script.write_text(f'#!/bin/sh\necho "$@" > "{log}"\necho {output}\nexit {code}\n')
    script.chmod(0o755)
    monkeypatch.setattr(updates, "pkexec", lambda: str(script))
    return log


def run_update(window, tmp_path, monkeypatch, code, answer=QMessageBox.StandardButton.No):
    boxes = Boxes(monkeypatch, answer=answer)
    downloaded = tmp_path / "updates" / "krdpc-0.2.0-1.noarch.rpm"

    def fake_download(found, package_format, folder, progress, cancel):
        folder.mkdir(parents=True, exist_ok=True)
        downloaded.write_bytes(b"rpm")
        progress(3, 3)
        return downloaded

    monkeypatch.setattr(updates, "download", fake_download)
    log = fake_pkexec(tmp_path, monkeypatch, code)
    _win, updater = updater_for(window, tmp_path)
    restarts = []
    updater.restart_requested.connect(lambda: restarts.append(True))
    updater.update_to(Installed("0.1.0", "rpm"), release("v0.2.0"))
    updater._process.waitForFinished(5000)
    QCoreApplication.processEvents()
    assert not updater.busy()
    return boxes, downloaded, log, restarts


def test_a_successful_install_asks_to_restart(window, tmp_path, monkeypatch):
    boxes, downloaded, log, restarts = run_update(
        window, tmp_path, monkeypatch, 0, answer=QMessageBox.StandardButton.Yes
    )
    assert log.read_text().split() == [
        "--disable-internal-agent",
        "dnf",
        "install",
        "-y",
        str(downloaded),
    ]
    assert boxes.shown == [
        ("question", "krdpc updated", "krdpc 0.2.0 is installed. Restart krdpc now to use it?")
    ]
    assert restarts == [True]
    assert not downloaded.exists()


def test_closing_the_password_box_keeps_the_package(window, tmp_path, monkeypatch):
    boxes, downloaded, _log, restarts = run_update(
        window, tmp_path, monkeypatch, updates.PKEXEC_DISMISSED
    )
    assert boxes.shown[0][:2] == ("information", "Not updated")
    assert downloaded.exists() and restarts == []


def test_a_failed_install_shows_the_command_to_run_by_hand(window, tmp_path, monkeypatch):
    boxes, downloaded, _log, restarts = run_update(window, tmp_path, monkeypatch, 1)
    kind, title, text, buttons = boxes.shown[0]
    assert (kind, title) == ("box", "Update not installed")
    assert "stopped with code 1" in text
    assert text.endswith(f"sudo dnf install {downloaded}")
    assert "Copy command" in buttons
    assert downloaded.exists() and restarts == []


def test_pkexec_never_asks_for_the_password_in_a_terminal():
    from pathlib import Path

    path = Path("/x/k.rpm")
    for package_format in ("rpm", "deb", "arch"):
        arguments = updates.pkexec_arguments(package_format, path)
        assert arguments[0] == "--disable-internal-agent"
        assert arguments[1:] == updates.install_command(package_format, path)


def test_no_password_box_shows_the_command_to_run_by_hand(window, tmp_path, monkeypatch):
    boxes, downloaded, _log, restarts = run_update(
        window, tmp_path, monkeypatch, updates.PKEXEC_REFUSED
    )
    kind, title, text, _buttons = boxes.shown[0]
    assert (kind, title) == ("box", "Update not installed")
    assert "no password box" in text
    assert text.endswith(f"sudo dnf install {downloaded}")
    assert downloaded.exists() and restarts == []


def test_no_pkexec_shows_the_command_to_run_by_hand(window, tmp_path, monkeypatch):
    boxes = Boxes(monkeypatch)
    path = tmp_path / "k.rpm"
    monkeypatch.setattr(updates, "download", lambda *args: path)
    monkeypatch.setattr(updates, "pkexec", lambda: None)
    _win, updater = updater_for(window, tmp_path)
    updater.update_to(Installed("0.1.0", "rpm"), release("v0.2.0"))
    assert "pkexec" in boxes.shown[0][2]
    assert not updater.busy()


def test_a_failed_download_is_reported(window, tmp_path, monkeypatch):
    boxes = Boxes(monkeypatch)

    def broken(*_args):
        raise UpdateError(
            "krdpc-0.2.0-1.noarch.rpm did not match its checksum, so it was not installed."
        )

    monkeypatch.setattr(updates, "download", broken)
    _win, updater = updater_for(window, tmp_path)
    updater.update_to(Installed("0.1.0", "rpm"), release("v0.2.0"))
    assert boxes.shown[0][:2] == ("warning", "Update failed")
    assert "checksum" in boxes.shown[0][2]


# ---- the window and Preferences -------------------------------------------------------------


def test_the_main_menu_has_check_for_updates(window, monkeypatch):
    win = window()
    checked = []
    monkeypatch.setattr(win.updater, "check", lambda quiet=False: checked.append(quiet))
    win.update_action.trigger()
    assert checked == [False]


def test_the_check_at_start_follows_the_preference(window, monkeypatch, qapp):
    for wanted in (True, False):
        win = window()
        win._preferences.check_updates = wanted
        checked = []
        monkeypatch.setattr(
            win.updater, "check", lambda quiet=False, seen=checked: seen.append(quiet)
        )
        win.check_for_updates_at_start(delay_ms=0)
        QCoreApplication.processEvents()
        assert checked == ([True] if wanted else [])


def test_restarting_quits_then_starts_krdpc_again(window, monkeypatch, tmp_path):
    program = tmp_path / "krdpc"
    program.write_text("#!/bin/sh\n")
    program.chmod(0o755)
    started = []
    monkeypatch.setattr(sys, "argv", [str(program), "--flag"])
    monkeypatch.setattr(QProcess, "startDetached", lambda *args: started.append(args) or True)
    monkeypatch.setattr("krdpc.mainwindow.QApplication.quit", lambda: None)
    win = window()
    win.show()
    win.restart()
    assert started == [(str(program), ["--flag"])]
    assert not win.isVisible()


def test_restarting_is_cancelled_with_the_quit(window, monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(QProcess, "startDetached", lambda *args: started.append(args) or True)
    win = window()
    monkeypatch.setattr(win, "quit", lambda: False)
    win.restart()
    assert started == []


def test_the_update_preferences_roundtrip(tmp_path):
    prefs = PreferencesStore(tmp_path)
    assert (Preferences().check_updates, Preferences().include_betas) == (True, False)
    chosen = Preferences(check_updates=False, include_betas=True)
    prefs.save(chosen)
    assert prefs.load() == chosen


def test_the_dialog_sets_the_update_preferences(qapp):
    dialog = PreferencesDialog(Preferences())
    assert dialog._check_updates.isChecked() and not dialog._include_betas.isChecked()
    dialog._check_updates.setChecked(False)
    dialog._include_betas.setChecked(True)
    chosen = dialog.preferences()
    assert (chosen.check_updates, chosen.include_betas) == (False, True)


def wait_for(qapp, results, timeout_s=5.0):
    """Run the event loop until a result arrives, as the window would."""
    from PySide6.QtCore import QElapsedTimer

    clock = QElapsedTimer()
    clock.start()
    while not results and clock.elapsed() < timeout_s * 1000:
        qapp.processEvents()
    return results


@pytest.mark.parametrize("attempt", range(5))
def test_a_result_from_the_background_thread_reaches_the_window(qapp, attempt):
    """The thread ends right after sending; the result must still arrive (#10)."""
    results = []
    run_in_thread(lambda: "found", results.append, lambda m: results.append(("failed", m)))
    assert wait_for(qapp, results) == ["found"]


def test_a_failure_from_the_background_thread_reaches_the_window(qapp):
    def broken():
        raise UpdateError("Could not reach GitHub")

    results = []
    run_in_thread(broken, lambda r: results.append(r), lambda m: results.append(("failed", m)))
    assert wait_for(qapp, results) == [("failed", "Could not reach GitHub")]
