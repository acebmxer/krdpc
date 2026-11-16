# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| Latest release | :white_check_mark: |
| Older tags | :x: |

krdpc is pre-1.0 and under active development. Fixes go into the next release
rather than being backported.

## Threat model

**What it holds.** Each saved computer's name, address, username and connection
options, as plain-text files in `~/.config/krdpc/`, readable by you only. Passwords
are never written to those files: krdpc asks for the password when you connect,
or, if you tick the box, stores it in KDE Wallet (through the desktop's Secret
Service, using the `keyring` library). The same goes for a gateway's password.
A profile also keeps the SHA-256 fingerprint of a certificate you chose to trust
for that computer.

**How passwords are passed.** krdpc starts `xfreerdp /args-from:stdin` and writes
the options, password included, to its standard input. The password is never in
`xfreerdp`'s command line, where any program could read it, and never on disk.
A password that contains a line break is refused, because that is how the options
are separated.

**Certificates.** `xfreerdp` is told to accept only the certificate whose
fingerprint you trusted. Any other unverifiable certificate is shown to you
first. If one differs from what you trusted before, krdpc says so. "Ignore
certificate errors" switches all of this off for that computer.

**What it runs.** krdpc starts `xfreerdp` as you, with the options of the
profile you chose. Anyone who can edit your profile files can make krdpc run
`xfreerdp` with different options (including the raw extra-arguments and
before/after-connection commands that profiles allow), so keep
`~/.config/krdpc/` writable by you only.

**What it does not do.** krdpc speaks no RDP itself and opens no network port.
Connection security (certificates, NLA, TLS) is FreeRDP's.

## Reporting a vulnerability

Report privately through GitHub, not in a public issue:

1. Open the [Security tab](https://github.com/acebmxer/krdpc/security) of this
   repository.
2. Choose **Report a vulnerability**.
3. Describe the issue, how to reproduce it, and what an attacker gains.

Expect an acknowledgement within a few days. Please give a reasonable window
for a fix before disclosing publicly.

## Scope

In scope: how krdpc stores and passes passwords, how it builds the `xfreerdp`
command line from a profile, and anything that lets a profile run something it
should not.

Out of scope: vulnerabilities in FreeRDP, Qt or KDE themselves (report those
to their projects), and anything requiring an attacker who can already write
to your home directory.
