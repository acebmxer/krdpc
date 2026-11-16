from krdpc.certificate import format_thumbprint, parse_certificate

THUMB = "ab:cd:ef:01:23:45:67:89:ab:cd:ef:01:23:45:67:89:ab:cd:ef:01:23:45:67:89:ab:cd:ef:01:23:45:67:89"

OUTPUT = f"""[00:00:00:000] [1:2] [WARN][com.freerdp.crypto] - [verify_cb]: failure
   Certificate details for 192.0.2.10:3389 (RDP-Server):
        Common Name: (null)
        Subject:     C = XX, L = Default City, O = Example Ltd
        Issuer:      C = XX, L = Default City, O = Example Ltd
        Valid from:  Jul 27 21:49:36 2026 GMT
        Valid to:    Jul 28 21:49:36 2026 GMT
        Thumbprint:  {THUMB.upper()}
The above X.509 certificate could not be verified.
"""


def test_reads_the_details():
    info = parse_certificate(OUTPUT)
    assert info.subject == "C = XX, L = Default City, O = Example Ltd"
    assert info.issuer == info.subject
    assert info.valid_from == "Jul 27 21:49:36 2026 GMT"
    assert info.valid_to == "Jul 28 21:49:36 2026 GMT"
    assert info.thumbprint == THUMB.replace(":", "")
    assert info.changed is False


def test_notices_a_changed_certificate():
    changed = OUTPUT + "@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @\n"
    assert parse_certificate(changed).changed is True


def test_no_certificate_in_ordinary_output():
    assert parse_certificate("[ERROR] connect failed\n") is None


def test_a_thumbprint_of_the_wrong_length_is_ignored():
    assert parse_certificate("Certificate details for x:1\nThumbprint:  ab:cd\n") is None


def test_format_thumbprint():
    assert format_thumbprint("abcdef") == "ab:cd:ef"
