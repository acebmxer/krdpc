import time

import pytest
from PySide6.QtCore import QCoreApplication

from krdpc.launcher import Launcher, explain_exit
from krdpc.profile import Profile


def wait_for(condition, seconds=10):
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        QCoreApplication.processEvents()
        time.sleep(0.01)


def fake_xfreerdp(tmp_path, body="exit 0"):
    script = tmp_path / "fake-xfreerdp"
    script.write_text(
        f'#!/bin/sh\necho "$@" > "{tmp_path}/args"\ncat > "{tmp_path}/stdin"\n{body}\n'
    )
    script.chmod(0o755)
    return str(script)


@pytest.fixture
def events():
    return {"started": [], "ended": [], "failed": [], "certificates": [], "rejected": []}


def make_launcher(store, find, events):
    launcher = Launcher(store, find_executable=find)
    launcher.started.connect(events["started"].append)
    launcher.ended.connect(events["ended"].append)
    launcher.failed.connect(lambda pid, msg: events["failed"].append((pid, msg)))
    launcher.certificate_untrusted.connect(lambda pid, info: events["certificates"].append(info))
    launcher.login_rejected.connect(events["rejected"].append)
    return launcher


def saved(store, **kwargs):
    return store.save(Profile(name="Dev", server="10.0.0.5", **kwargs))


def test_missing_xfreerdp_is_a_plain_message(qapp, store, events):
    launcher = make_launcher(store, lambda _name: None, events)
    launcher.connect_to(saved(store))
    assert events["failed"][0][1].startswith("xfreerdp was not found")
    assert launcher.active_count() == 0


def test_successful_connection(qapp, store, tmp_path, events):
    profile = saved(store, username="nick")
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path), events)
    launcher.connect_to(profile)
    wait_for(lambda: events["ended"])
    assert events["started"] == [profile.id] and events["failed"] == []
    assert "/args-from:stdin" in (tmp_path / "args").read_text()
    assert "/v:10.0.0.5" in (tmp_path / "stdin").read_text()
    assert store.get(profile.id).last_used != ""
    assert launcher.active_count() == 0


def test_the_password_goes_through_the_pipe_and_not_the_arguments(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path), events)
    profile = saved(store, username="nick", gateway_server="gw")
    launcher.connect_to(profile, "s3cret", "gwpass")
    wait_for(lambda: events["ended"])
    piped = (tmp_path / "stdin").read_text().splitlines()
    assert "/p:s3cret" in piped
    assert "/gateway:g:gw,p:gwpass" in piped
    assert "/u:nick" in piped
    argv = (tmp_path / "args").read_text()
    assert "s3cret" not in argv and "gwpass" not in argv
    assert argv.split() == ["/args-from:stdin"]


def test_a_password_with_a_line_break_never_starts_anything(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path), events)
    launcher.connect_to(saved(store), "a\nb")
    assert "line break" in events["failed"][0][1]
    assert not (tmp_path / "args").exists()


CERTIFICATE_OUTPUT = """echo 'Certificate details for 192.0.2.10:3389 (RDP-Server):'
echo '        Subject:     C = XX, O = Example'
echo '        Issuer:      C = XX, O = Example'
echo '        Valid from:  Jul 27 21:49:36 2026 GMT'
echo '        Valid to:    Jul 28 21:49:36 2026 GMT'
echo '        Thumbprint:  ab:cd:ef:01:23:45:67:89:ab:cd:ef:01:23:45:67:89:ab:cd:ef:01:23:45:67:89:ab:cd:ef:01:23:45:67:89'
exit 143"""


def test_an_untrusted_certificate_is_reported_instead_of_a_failure(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path, CERTIFICATE_OUTPUT), events)
    profile = saved(store)
    launcher.connect_to(profile)
    wait_for(lambda: events["certificates"])
    assert events["certificates"][0].thumbprint == "abcdef0123456789" * 4
    assert events["failed"] == []


def test_a_refused_sign_in_is_reported(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path, "exit 134"), events)
    profile = saved(store)
    launcher.connect_to(profile, "wrong")
    wait_for(lambda: events["failed"])
    assert events["rejected"] == [profile.id]
    assert "Sign-in failed" in events["failed"][0][1]


def test_other_failures_are_not_sign_in_refusals(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path, "exit 131"), events)
    launcher.connect_to(saved(store))
    wait_for(lambda: events["failed"])
    assert events["rejected"] == []


def test_normal_exit_codes_do_not_complain(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path, "exit 11"), events)
    launcher.connect_to(saved(store))
    wait_for(lambda: events["ended"] or events["failed"])
    assert events["failed"] == []


def test_failure_explains_the_code_and_shows_the_output(qapp, store, tmp_path, events):
    body = 'echo "connect failed: no route" >&2\nexit 131'
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path, body), events)
    profile = saved(store)
    launcher.connect_to(profile)
    wait_for(lambda: events["failed"])
    pid, message = events["failed"][0]
    assert pid == profile.id
    assert "Could not connect" in message
    assert "connect failed: no route" in message
    assert events["ended"] == []


def test_a_crash_is_reported(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path, "kill -9 $$"), events)
    launcher.connect_to(saved(store))
    wait_for(lambda: events["failed"])
    assert "stopped unexpectedly" in events["failed"][0][1]


def test_bad_extra_arguments_never_start_anything(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path), events)
    launcher.connect_to(saved(store, extra_arguments='"oops'))
    assert "extra arguments" in events["failed"][0][1]
    assert not (tmp_path / "args").exists()


def test_before_command_runs_first(qapp, store, tmp_path, events):
    marker = tmp_path / "before"
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path), events)
    launcher.connect_to(saved(store, before_command=f"touch {marker}"))
    wait_for(lambda: events["ended"])
    assert marker.exists()


def test_failing_before_command_stops_the_connection(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path), events)
    launcher.connect_to(saved(store, before_command="echo nope; exit 3"))
    wait_for(lambda: events["failed"])
    assert "before connecting failed" in events["failed"][0][1]
    assert "nope" in events["failed"][0][1]
    assert not (tmp_path / "args").exists()
    assert events["started"] == []


def test_after_command_runs_when_the_session_ends(qapp, store, tmp_path, events):
    marker = tmp_path / "after"
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path), events)
    launcher.connect_to(saved(store, after_command=f"touch {marker}"))
    wait_for(lambda: events["ended"])
    wait_for(marker.exists)


def test_stop_all_ends_open_connections(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path, "sleep 30"), events)
    launcher.connect_to(saved(store))
    wait_for(lambda: events["started"])
    assert launcher.active_count() == 1
    launcher.stop_all()
    wait_for(lambda: launcher.active_count() == 0)


def test_stopping_everything_is_not_a_failure(qapp, store, tmp_path, events):
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path, "sleep 30"), events)
    profile = saved(store)
    launcher.connect_to(profile)
    wait_for(lambda: events["started"])
    assert launcher.active_count_for(profile.id) == 1
    launcher.stop_all()
    wait_for(lambda: launcher.active_count() == 0)
    assert events["failed"] == []


def test_explain_exit():
    assert "Could not connect" in explain_exit(131)
    assert "cancelled" in explain_exit(145)
    assert "licensing" in explain_exit(20)
    assert explain_exit(250) == "xfreerdp stopped with code 250."
