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


def test_xfreerdp3_is_preferred_over_xfreerdp(qapp, store, tmp_path, events):
    asked = []

    def find(name):
        asked.append(name)
        return {"xfreerdp3": fake_xfreerdp(tmp_path), "xfreerdp": "/usr/bin/false"}[name]

    launcher = make_launcher(store, find, events)
    launcher.connect_to(saved(store))
    wait_for(lambda: events["ended"])
    assert asked[0] == "xfreerdp3"
    assert (tmp_path / "args").exists()  # the fake one ran, not /usr/bin/false


def test_plain_xfreerdp_is_used_when_there_is_no_xfreerdp3(qapp, store, tmp_path, events):
    launcher = make_launcher(
        store,
        lambda name: fake_xfreerdp(tmp_path) if name == "xfreerdp" else None,
        events,
    )
    launcher.connect_to(saved(store))
    wait_for(lambda: events["ended"])
    assert events["failed"] == []


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


# What FreeRDP 3.33.1 prints when it cannot parse an option (exit 22, 23 or 24).
_UNKNOWN_OPTION = (
    "[21:32:25:930] [4:00000004] [ERROR][com.winpr.commandline] - [CommandLineParseArgumentsA]:"
    " Failed at index 2 [<censored>]: Unexpected keyword"
)
_BAD_VALUE = (
    "[21:32:25:966] [10:0000000a] [ERROR][com.freerdp.client.common.cmdline] -"
    " [parse_command_line]: Command line parsing failed at 'sec' value 'bogus' [-1002]"
)
_USAGE = "\nxfreerdp - A Free Remote Desktop Protocol Implementation\nSee www.freerdp.com for more"


@pytest.mark.parametrize(
    ("printed", "code", "shown"),
    [
        (_UNKNOWN_OPTION + _USAGE, 23, "Unexpected keyword"),
        (_UNKNOWN_OPTION + _USAGE, 24, "Unexpected keyword"),
        (_BAD_VALUE + _USAGE, 22, "value 'bogus'"),
        (_USAGE, 255, None),
    ],
)
def test_an_option_freerdp_cannot_parse_is_reported_as_one(
    qapp, store, tmp_path, events, printed, code, shown
):
    (tmp_path / "printed").write_text(printed + "\n")
    body = f'cat "{tmp_path}/printed" >&2\nexit {code}'
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path, body), events)
    launcher.connect_to(saved(store, extra_arguments="/bogus-option"))
    wait_for(lambda: events["failed"])
    message = events["failed"][0][1]
    assert message.startswith("FreeRDP did not understand one of the options.")
    assert "licensing" not in message
    assert "Free Remote Desktop Protocol Implementation" not in message
    if shown:
        assert shown in message
    else:
        assert (
            message == "FreeRDP did not understand one of the options. Check the extra arguments."
        )


def test_a_licensing_error_is_still_reported_as_one(qapp, store, tmp_path, events):
    body = 'echo "[ERROR][com.freerdp.core.license] - license failed" >&2\nexit 24'
    launcher = make_launcher(store, lambda _n: fake_xfreerdp(tmp_path, body), events)
    launcher.connect_to(saved(store))
    wait_for(lambda: events["failed"])
    assert "licensing problem" in events["failed"][0][1]


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


def fake_program(tmp_path, name):
    folder = tmp_path / name
    folder.mkdir()
    return fake_xfreerdp(folder)


def test_without_an_x11_display_the_sdl_client_is_used(qapp, store, tmp_path, events):
    """Under WSL with Xwayland down, xfreerdp cannot open a window; FreeRDP's SDL client can."""
    programs = {"xfreerdp": fake_program(tmp_path, "x"), "sdl-freerdp": fake_program(tmp_path, "s")}
    launcher = Launcher(store, find_executable=programs.get, has_x11_display=lambda: False)
    launcher.ended.connect(events["ended"].append)
    launcher.connect_to(saved(store))
    wait_for(lambda: events["ended"])
    assert (tmp_path / "s" / "args").exists()
    assert not (tmp_path / "x" / "args").exists()


def test_sdl_freerdp3_is_preferred_over_sdl_freerdp(qapp, store, tmp_path, events):
    asked = []

    def find(name):
        asked.append(name)
        return fake_xfreerdp(tmp_path) if name == "sdl-freerdp3" else None

    launcher = Launcher(store, find_executable=find, has_x11_display=lambda: False)
    launcher.ended.connect(events["ended"].append)
    launcher.connect_to(saved(store))
    wait_for(lambda: events["ended"])
    assert asked == ["sdl-freerdp3"]


def test_with_an_x11_display_xfreerdp_stays_first(qapp, store, tmp_path, events):
    programs = {"xfreerdp": fake_program(tmp_path, "x"), "sdl-freerdp": fake_program(tmp_path, "s")}
    launcher = Launcher(store, find_executable=programs.get, has_x11_display=lambda: True)
    launcher.ended.connect(events["ended"].append)
    launcher.connect_to(saved(store))
    wait_for(lambda: events["ended"])
    assert (tmp_path / "x" / "args").exists()
    assert not (tmp_path / "s" / "args").exists()


def test_the_sdl_client_is_used_when_it_is_the_only_one_installed(qapp, store, tmp_path, events):
    launcher = Launcher(
        store,
        find_executable={"sdl-freerdp3": fake_xfreerdp(tmp_path)}.get,
        has_x11_display=lambda: True,
    )
    launcher.ended.connect(events["ended"].append)
    launcher.connect_to(saved(store))
    wait_for(lambda: events["ended"])
    assert (tmp_path / "args").exists()


def test_no_x11_display_and_no_sdl_client_is_a_plain_message(qapp, store, tmp_path, events):
    launcher = Launcher(
        store,
        find_executable={"xfreerdp": fake_xfreerdp(tmp_path)}.get,
        has_x11_display=lambda: False,
    )
    launcher.failed.connect(lambda pid, msg: events["failed"].append(msg))
    launcher.connect_to(saved(store))
    assert "no X11 display" in events["failed"][0]
    assert "freerdp3-sdl" in events["failed"][0]
    assert not (tmp_path / "args").exists()


def test_messages_name_the_program_that_ran(qapp, store, tmp_path, events):
    script = tmp_path / "sdl-freerdp"
    script.write_text("#!/bin/sh\ncat > /dev/null\nexit 250\n")
    script.chmod(0o755)
    launcher = Launcher(
        store, find_executable={"sdl-freerdp": str(script)}.get, has_x11_display=lambda: False
    )
    launcher.failed.connect(lambda pid, msg: events["failed"].append(msg))
    launcher.connect_to(saved(store))
    wait_for(lambda: events["failed"])
    assert events["failed"][0].startswith("sdl-freerdp stopped with code 250.")


def test_x11_display_check(tmp_path, monkeypatch):
    import socket

    from krdpc import launcher

    assert not launcher.x11_display_available({})
    assert not launcher.x11_display_available({"DISPLAY": "nonsense"})
    assert launcher.x11_display_available({"DISPLAY": "remotehost:10.0"})
    # A local display counts only if its socket answers.
    sockets = tmp_path / "x11"
    sockets.mkdir()
    real_connect = socket.socket.connect

    def connect(self, address):
        if isinstance(address, str) and address.startswith("/tmp/.X11-unix/"):
            address = str(sockets / address.rsplit("/", 1)[1])
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    assert not launcher.x11_display_available({"DISPLAY": ":7"})
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sockets / "X7"))
    server.listen()
    try:
        assert launcher.x11_display_available({"DISPLAY": ":7"})
        assert launcher.x11_display_available({"DISPLAY": "unix:7.0"})
    finally:
        server.close()
