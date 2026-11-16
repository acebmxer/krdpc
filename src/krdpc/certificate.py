"""Reading the certificate xfreerdp could not verify out of its output."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CertificateInfo:
    common_name: str
    subject: str
    issuer: str
    valid_from: str
    valid_to: str
    thumbprint: str  # SHA-256 as 64 lowercase hex digits
    changed: bool  # xfreerdp says it differs from one it saw before


def _field(text: str, label: str) -> str:
    match = re.search(rf"^\s*{re.escape(label)}:\s+(.*?)\s*$", text, re.MULTILINE)
    return match.group(1) if match else ""


def parse_certificate(output: str) -> CertificateInfo | None:
    """The certificate details xfreerdp printed, or None if it printed none."""
    if "Certificate details for" not in output:
        return None
    digits = _field(output, "Thumbprint").replace(":", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digits):
        return None
    return CertificateInfo(
        common_name=_field(output, "Common Name"),
        subject=_field(output, "Subject"),
        issuer=_field(output, "Issuer"),
        valid_from=_field(output, "Valid from"),
        valid_to=_field(output, "Valid to"),
        thumbprint=digits,
        changed="HOST IDENTIFICATION HAS CHANGED" in output,
    )


def format_thumbprint(thumbprint: str) -> str:
    """`ab:cd:...` for showing to a person."""
    return ":".join(thumbprint[i : i + 2] for i in range(0, len(thumbprint), 2))
