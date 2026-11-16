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
options, as plain-text files in `~/.config/krdpc/`. Passwords are never written
to those files: krdpc asks for the password when you connect, or, if you tick
the box, stores it in KDE Wallet.

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
