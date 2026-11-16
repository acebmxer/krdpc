# krdpc

[![CI](https://github.com/acebmxer/krdpc/actions/workflows/ci.yml/badge.svg)](https://github.com/acebmxer/krdpc/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Status: in development](https://img.shields.io/badge/status-in%20development-orange.svg)](#roadmap)
[![Python](https://img.shields.io/badge/python-3-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Qt for Python](https://img.shields.io/badge/PySide6-Qt%206-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![KDE Plasma](https://img.shields.io/badge/KDE-Plasma-1D99F3?logo=kde&logoColor=white)](https://kde.org/plasma-desktop/)
[![FreeRDP](https://img.shields.io/badge/FreeRDP-xfreerdp-informational)](https://www.freerdp.com/)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux&logoColor=white)](#requirements)

The client that krdp lacks: a native KDE desktop app that keeps a list of your
remote computers and opens each one with FreeRDP's `xfreerdp`. It is laid out
and behaves like Remmina's main window, but it is built with Qt and follows your
KDE theme.

**Status:** in development, not released yet. Everything below works; the install
steps are for trying it from a clone of this repository.

## Why

KDE's krdp shares a Plasma desktop over RDP, and FreeRDP's `xfreerdp` connects to
it and resizes correctly. But FreeRDP has no screen for saving connections: you
type the address and options every time. krdpc adds that screen and nothing else.

## What it does

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
  the box. The password is never written into the profile file or put on the
  `xfreerdp` command line.
- Ask before trusting a certificate `xfreerdp` cannot verify, and remember your
  answer for that computer.
- Keep each profile as a plain-text file in `~/.config/krdpc/`.
- Set a few preferences: icon size, whether to confirm deleting, remembering the
  window layout, where `xfreerdp` is, a system tray icon (with closing to the tray
  and starting hidden), and starting at login.
- Show a plain error if `xfreerdp` is missing or exits with an error.

## What it does not do

- It is not an RDP engine. It does not speak RDP itself.
- It is not a server. It does not replace krdp or xrdp.
- It does not copy code from Remmina. Remmina is only the model for the layout
  and behaviour.

## Requirements

- Linux with KDE Plasma (Fedora 45 is the first target).
- FreeRDP 3, which provides `xfreerdp` (Fedora and Arch: package `freerdp`; Debian and Ubuntu:
  package `freerdp3-x11`, which provides `xfreerdp3`). FreeRDP 2 is not supported.
- Python 3, PySide6 (Qt 6) and `keyring` (Fedora: `python3-pyside6`, `python3-keyring`).
- KDE Wallet, if you want passwords remembered.

## Install

### From a package

Download the file for your distribution from the
[Releases page](https://github.com/acebmxer/krdpc/releases) (a beta is published
there as a pre-release). Each package pulls in FreeRDP 3, PySide6 and `keyring`
from your distribution, so krdpc follows your Plasma theme.

| Distribution | Install | Remove |
| --- | --- | --- |
| Fedora | `sudo dnf install ./krdpc-*.rpm` | `sudo dnf remove krdpc` |
| Debian 13, Ubuntu 26.04 and newer | `sudo apt install ./krdpc_*.deb` | `sudo apt remove krdpc` |
| Arch Linux | `sudo pacman -U krdpc-*.pkg.tar.zst` | `sudo pacman -R krdpc` |

Ubuntu 24.04 and older have no PySide6 package, so the `.deb` cannot be installed
there; use the steps below with a virtual environment instead.

krdpc then appears in the application menu under Network. To update, install the
newer package the same way.

### From a clone of this repository

On Fedora KDE. Use Fedora's own PySide6 package, not the one from PyPI: it is built
against the Qt that Plasma uses, so krdpc follows your theme and icons.

```bash
sudo dnf install freerdp python3-pyside6 python3-keyring
pip install --user --no-deps .
install -Dm644 data/krdpc.desktop ~/.local/share/applications/krdpc.desktop
install -Dm644 src/krdpc/krdpc.svg ~/.local/share/icons/hicolor/scalable/apps/krdpc.svg
```

Or run `krdpc` in a terminal. After `git pull`, run
`pip install --user --no-deps --force-reinstall .` again: the application menu starts
the installed copy, not the files in the clone. To remove it:

```bash
pip uninstall krdpc
rm ~/.local/share/applications/krdpc.desktop
rm ~/.local/share/icons/hicolor/scalable/apps/krdpc.svg
```

### What it leaves behind

Either way, krdpc keeps your computers in `~/.config/krdpc/`, your settings in
`~/.config/krdpc/krdpc.conf`, and (if you turn on "start at login")
`~/.config/autostart/krdpc.desktop`. Delete those to remove everything. Remembered
passwords stay in KDE Wallet under the name `krdpc`; remove them there.

## Using it

1. Click **+** to add a computer. Only a name and a server are needed.
2. Double-click it (or right-click and choose Connect). krdpc asks for the
   password; tick **Remember in KDE Wallet** to be asked only once.
3. The first time a computer shows a certificate `xfreerdp` cannot verify, krdpc
   shows it and asks whether to trust it.
4. Right-click a computer to edit, duplicate or delete it. **Ctrl+F** searches.
5. **Preferences** is in the menu at the top right.

## If something goes wrong

- **"xfreerdp was not found."** Install the `freerdp` package, or point
  Preferences at the program.
- **The password is asked every time.** The wallet may be locked or missing.
  krdpc says so in the status bar and asks instead. A refused sign-in also makes
  krdpc forget the saved password.
- **The window looks plain, not like Plasma.** The PySide6 from PyPI was
  installed. Remove it and use the Fedora package.
- **Closing the window does not end krdpc.** With "closing keeps krdpc in the tray"
  on, the window is only hidden. Choose Quit in the tray menu, or in the main
  menu, to end it.

## Not built

- Grouping the list by group or label (Remmina's tree view).
- An SSH tunnel tab.
- Default values for new computers.
- Other protocols; krdpc is for RDP only.

## Roadmap

1. Repository setup: licence, changelog, issue templates, CI. (done)
2. Profile list and tabbed edit dialog. (done)
3. Connect: build the `xfreerdp` command from a profile and start it. (done)
4. Password box and KDE Wallet. (done)
5. Application menu entry (`.desktop` file). (done)
6. Preferences page in the main menu. (done)
7. Tests and install documentation. (done)

The first release is next: the version number and a tag come when the project is ready.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests target `dev`. To report a
security problem, see [SECURITY.md](SECURITY.md).
