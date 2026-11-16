import dataclasses

from krdpc.profile import (
    CHOICES,
    STORED_FIELDS,
    Profile,
    escape,
    from_mapping,
    to_mapping,
    unescape,
    validate,
)


def test_defaults_roundtrip_through_text():
    profile = Profile(name="Office PC", server="10.0.0.5")
    assert from_mapping("office-pc", to_mapping(profile)) == dataclasses.replace(
        profile, id="office-pc"
    )


def test_every_stored_field_roundtrips_with_changed_values():
    changed = {}
    for field in STORED_FIELDS:
        if field.type is bool:
            changed[field.name] = not field.default
        elif field.type is int:
            changed[field.name] = 7
        elif field.name in CHOICES:
            changed[field.name] = CHOICES[field.name][-1][0]
        else:
            changed[field.name] = f"value of {field.name}"
    profile = Profile(id="x", **changed)
    assert from_mapping("x", to_mapping(profile)) == profile


def test_multiline_and_backslashes_survive():
    text = "line one\nline two\\with slash\r\nend"
    assert unescape(escape(text)) == text
    profile = Profile(notes=text)
    assert from_mapping("a", to_mapping(profile)).notes == text


def test_unknown_escape_is_kept():
    assert unescape("a\\qb") == "a\\qb"


def test_bad_values_fall_back_to_defaults():
    profile = from_mapping(
        "a",
        {
            "resolution_width": "wide",
            "clipboard": "perhaps",
            "sound": "loud",
            "reconnect_attempts": "-5",
        },
    )
    defaults = Profile()
    assert profile.resolution_width == defaults.resolution_width
    assert profile.clipboard is defaults.clipboard
    assert profile.sound == defaults.sound
    assert profile.reconnect_attempts == 0


def test_missing_values_use_defaults_and_unknown_keys_are_ignored():
    profile = from_mapping("a", {"name": "N", "something_new": "x"})
    assert profile.name == "N"
    assert profile.server == ""
    assert profile.clipboard is True


def test_bool_spellings():
    assert from_mapping("a", {"maximize": "Yes"}).maximize is True
    assert from_mapping("a", {"clipboard": "0"}).clipboard is False


def test_validate():
    assert validate(Profile(name="a", server="b")) == []
    assert len(validate(Profile())) == 2
    fixed = Profile(name="a", server="b", resolution_mode="fixed", resolution_width=0)
    assert validate(fixed) == ["A fixed size needs a width and a height above zero."]
    assert validate(dataclasses.replace(fixed, resolution_mode="dynamic")) == []


def test_last_used_text():
    assert Profile(last_used="2026-11-15T19:46:32").last_used_text() == "2026-11-15 - 19:46:32"
    assert Profile().last_used_text() == ""
