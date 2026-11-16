import pytest

from krdpc.command import CommandError, build_command
from krdpc.profile import CHOICES, Profile


def make(**kwargs):
    return Profile(name="Dev Fedora", server="10.0.0.5", **kwargs)


def test_minimal_profile():
    assert build_command(make()) == [
        "xfreerdp",
        "/v:10.0.0.5",
        "/t:Dev Fedora",
        "/d:",
        "/dynamic-resolution",
        "-wallpaper",
        "+clipboard",
        "/audio-mode:none",
    ]


def test_executable_is_the_first_argument():
    assert build_command(make(), "/usr/bin/xfreerdp")[0] == "/usr/bin/xfreerdp"


def test_credentials():
    args = build_command(make(username="nick", domain="CORP"))
    assert "/u:nick" in args and "/d:CORP" in args


def test_no_password_unless_given():
    assert not [a for a in build_command(make()) if a.startswith("/p")]
    assert "/p:s3cret" in build_command(make(), password="s3cret")
    assert "/p:" in build_command(make(), password="")  # a deliberately blank password


def test_passwords_may_not_contain_line_breaks():
    with pytest.raises(CommandError, match="line break"):
        build_command(make(), password="a\nb")
    with pytest.raises(CommandError, match="line break"):
        build_command(make(gateway_server="g"), gateway_password="a\rb")


def test_a_trusted_certificate_is_accepted_by_its_fingerprint():
    thumb = "ab" * 32
    assert f"/cert:fingerprint:sha256:{thumb}" in build_command(make(trusted_certificate=thumb))
    both = build_command(make(trusted_certificate=thumb, ignore_certificate=True))
    assert "/cert:ignore" in both and not [a for a in both if "fingerprint" in a]


def test_fixed_size_replaces_dynamic_resolution():
    args = build_command(
        make(resolution_mode="fixed", resolution_width=2560, resolution_height=1440)
    )
    assert "/size:2560x1440" in args
    assert "/dynamic-resolution" not in args


def test_window_modes():
    assert "/f" in build_command(make(fullscreen=True, maximize=True))
    assert "+workarea" not in build_command(make(fullscreen=True, maximize=True))
    assert "+workarea" in build_command(make(maximize=True))
    assert "+multimon" in build_command(make(multimon=True))


@pytest.mark.parametrize(
    ("quality", "expected"),
    [
        ("poor", ["-wallpaper", "-themes", "-fonts"]),
        ("medium", ["-wallpaper", "-themes"]),
        ("good", ["-wallpaper"]),
        ("best", ["+aero", "+menu-anims"]),
    ],
)
def test_quality(quality, expected):
    args = build_command(make(quality=quality))
    assert [a for a in args if a[0] in "+-" and a != "-clipboard"][: len(expected)] == expected


def test_every_choice_builds():
    for field, choices in CHOICES.items():
        for value, _label in choices:
            build_command(make(**{field: value}))


def test_colour_depth_security_network():
    args = build_command(make(color_depth="16", security="nla", network="lan"))
    assert {"/bpp:16", "/sec:nla", "/network:lan"} <= set(args)
    plain = build_command(make())
    assert not [a for a in plain if a.startswith(("/bpp", "/sec", "/network"))]


def test_redirections():
    args = build_command(
        make(
            clipboard=False,
            sound="local",
            microphone=True,
            drive="/home/nick/Documents",
            share_printers=True,
            share_usb=True,
        )
    )
    assert "-clipboard" in args and "+clipboard" not in args
    assert {"/audio-mode:redirect", "/sound", "/microphone", "/printer", "/usb:auto"} <= set(args)
    assert "/drive:Documents,/home/nick/Documents" in args
    assert "/audio-mode:server" in build_command(make(sound="remote"))


def test_drive_with_odd_names():
    assert "/drive:share,/" in build_command(make(drive="/"))
    assert "/drive:a b,/x/a,b" in build_command(make(drive="/x/a,b"))


def test_advanced_options():
    args = build_command(
        make(
            ignore_certificate=True,
            reconnect_attempts=5,
            timeout=30,
            console=True,
            client_name="laptop",
            keyboard_layout="0x409",
            program="notepad",
        )
    )
    expected = {
        "/cert:ignore",
        "+auto-reconnect",
        "/auto-reconnect-max-retries:5",
        "/timeout:30000",
        "+admin",
        "/client-hostname:laptop",
        "/kbd:layout:0x409",
        "/shell:notepad",
    }
    assert expected <= set(args)


def test_gateway():
    args = build_command(
        make(gateway_server="gw.example.com", gateway_username="u", gateway_domain="D")
    )
    assert "/gateway:g:gw.example.com,u:u,d:D" in args
    assert "/gateway:g:gw.example.com" in build_command(make(gateway_server="gw.example.com"))
    with_password = build_command(make(gateway_server="gw"), gateway_password="pw")
    assert "/gateway:g:gw,p:pw" in with_password
    with pytest.raises(CommandError):
        build_command(make(gateway_server="gw"), gateway_password="a,b")
    with pytest.raises(CommandError):
        build_command(make(gateway_server="a,p:secret"))


def test_extra_arguments_are_split_like_a_shell():
    args = build_command(make(extra_arguments='/gfx:AVC444 "/t:My PC" +fonts'))
    assert args[-3:] == ["/gfx:AVC444", "/t:My PC", "+fonts"]


def test_unbalanced_quote_is_a_clear_error():
    with pytest.raises(CommandError, match="extra arguments"):
        build_command(make(extra_arguments='"oops'))


def test_no_server_is_an_error():
    with pytest.raises(CommandError):
        build_command(Profile(name="x"))


def test_values_stay_one_argument_each():
    args = build_command(Profile(name="x +admin", server="s", username="a /p:secret"))
    assert "/u:a /p:secret" in args and "/t:x +admin" in args
    assert "+admin" not in args


def test_a_line_break_in_a_setting_is_refused():
    with pytest.raises(CommandError, match="line break"):
        build_command(Profile(name="a\nb", server="s"))
