---
name: Bug report
about: Something in krdpc does not work as documented
title: '[Bug] '
labels: bug
assignees: ''
---

## What happened

<!-- A clear description of what went wrong. Paste error messages exactly. -->

## What you expected

## Steps to reproduce

1. Open krdpc
2. Select / click `...`
3. See error

## Output

<!-- Anything krdpc or xfreerdp printed (start krdpc from a terminal to see it),
     or the message in the status bar. Remove addresses, usernames and anything
     else sensitive. -->

```
(paste output here)
```

## Environment

| Field | Value |
|-------|-------|
| krdpc version | <!-- main menu (top right) > About krdpc, e.g. "krdpc 0.1.0" --> |
| Installed from | <!-- .rpm, .deb, Arch package, or a clone with pip --> |
| Distro & version | <!-- e.g. Fedora 45, Debian 13, Arch 2026-10 --> |
| Desktop & Qt | <!-- e.g. KDE Plasma 6.5, Qt 6.11 --> |
| FreeRDP | <!-- output of `xfreerdp /version` (or `xfreerdp3 /version`) --> |
| Area affected | <!-- e.g. connecting, password / KDE Wallet, certificate, tray, Preferences --> |

## Does the same happen with xfreerdp on its own?

<!-- If the problem is inside the connection, try the same computer with
     xfreerdp in a terminal. This tells us whether the problem is in krdpc or
     in FreeRDP. -->

- [ ] Same problem with `xfreerdp`
- [ ] Works with `xfreerdp`, fails only in krdpc
- [ ] Not tried

## Additional context

<!-- Screenshots or anything else that might help. -->
