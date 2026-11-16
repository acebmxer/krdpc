# krdpc

[![CI](https://github.com/acebmxer/krdpc/actions/workflows/ci.yml/badge.svg)](https://github.com/acebmxer/krdpc/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Status: planning](https://img.shields.io/badge/status-planning-orange.svg)](#roadmap)
[![Python](https://img.shields.io/badge/python-3-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Qt for Python](https://img.shields.io/badge/PySide6-Qt%206-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![KDE Plasma](https://img.shields.io/badge/KDE-Plasma-1D99F3?logo=kde&logoColor=white)](https://kde.org/plasma-desktop/)
[![FreeRDP](https://img.shields.io/badge/FreeRDP-xfreerdp-informational)](https://www.freerdp.com/)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux&logoColor=white)](#requirements)

The client that krdp lacks: a native KDE desktop app that keeps a list of your
remote computers and opens each one with FreeRDP's `xfreerdp`. It is laid out
and behaves like Remmina's main window, but it is built with Qt and follows your
KDE theme.

**Status:** planning. No code yet.

## Why

KDE's krdp shares a Plasma desktop over RDP, and FreeRDP's `xfreerdp` connects to
it and resizes correctly. But FreeRDP has no screen for saving connections: you
type the address and options every time. krdpc adds that screen and nothing else.

## What it will do

- Show your saved computers in a sortable table: name, group, labels, server,
  protocol and last used.
- Search the list as you type.
- Add, edit, duplicate and delete entries in a tabbed dialog (basic, advanced,
  behaviour, notes) covering the usual RDP options: user and domain, resolution,
  colour depth, sound, clipboard, shared folders, gateway, security and more.
- Connect with a double-click or the Connect button: krdpc starts `xfreerdp` with
  the saved options, and dynamic resolution if you want it, so the desktop
  follows the window size.
- Ask for the password when you connect, or remember it in KDE Wallet if you tick
  the box. The password is never written into the profile file.
- Keep each profile as a plain-text file in `~/.config/krdpc/`.
- Show a plain error if `xfreerdp` is missing or exits with an error.

## What it will not do

- It is not an RDP engine. It does not speak RDP itself.
- It is not a server. It does not replace krdp or xrdp.
- It does not copy code from Remmina. Remmina is only the model for the layout
  and behaviour.

## Requirements

- Linux with KDE Plasma (Fedora 45 is the first target).
- The `freerdp` package (provides `xfreerdp`).
- Python 3 and PySide6 (Qt 6).

## Roadmap

1. Repository setup: licence, changelog, issue templates, CI. (done)
2. Profile list and tabbed edit dialog.
3. Connect: build the `xfreerdp` command from a profile and start it.
4. Password box and KDE Wallet.
5. Application menu entry (`.desktop` file).
6. Tests and install documentation.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests target `dev`. To report a
security problem, see [SECURITY.md](SECURITY.md).
