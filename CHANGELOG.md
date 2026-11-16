# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

krdpc is a native KDE app that keeps a list of remote computers and opens each
one with FreeRDP's `xfreerdp`.

## [Unreleased]

### Added

- **Packages.** A `.rpm` for Fedora, a `.deb` for Debian 13 and Ubuntu 26.04 and newer, and a
  package for Arch Linux, each depending on the distribution's own FreeRDP 3, PySide6 and
  `keyring`. krdpc now also finds FreeRDP 3's `xfreerdp3` program, which is how Debian and
  Ubuntu name it. The README says how to install them.
- **Documentation.** The README now covers installing, updating and removing krdpc, using it,
  what to do when something goes wrong, and what is not built.
- **Preferences.** **Preferences…** in the main menu (Ctrl+,) sets the size of the icons in the
  list (small, medium or large), whether deleting a computer asks first, whether krdpc remembers
  its window size and column layout between runs, and which `xfreerdp` to use instead of the
  first one found on your PATH. They are kept in `~/.config/krdpc/krdpc.conf`.
- **System tray.** Preferences can show a krdpc icon in the system tray: click it to show or hide
  the window, right-click for New computer and Quit. With it on you can also have closing the
  window keep krdpc running in the tray (open connections stay open; Quit really quits) and start
  krdpc with the window hidden. **Start krdpc when I log in** adds or removes
  `~/.config/autostart/krdpc.desktop`.
- **Application menu entry.** A `krdpc.desktop` file and an icon, so krdpc appears in the KDE
  application menu (Network) and can be pinned to the taskbar. krdpc's window shows the same
  icon. The README says how to install them.
- **Password box.** Connecting asks for the password in a box instead of the terminal, with an
  eye at the right end of the field to show what you typed. Tick
  **Remember in KDE Wallet** and krdpc keeps it in KDE Wallet and stops asking; a refused sign-in
  makes it forget the saved password, and so does deleting the computer or unticking the option
  in the edit dialog. If the computer uses a gateway, its password is asked for and remembered
  too. The password is sent to `xfreerdp` through a pipe, so it is never on its command line or
  in your profile file. A blank domain is sent as blank, so `xfreerdp` no longer stops to ask for
  one.
- **Certificate dialog.** When the remote computer's certificate cannot be verified (for example
  a self-signed one), krdpc shows its subject, issuer, dates and SHA-256 fingerprint and asks
  whether to trust it, instead of `xfreerdp` asking in the terminal. Trusting it saves the
  fingerprint for that computer only; the Advanced tab shows it with a **Forget** button. If the
  certificate later differs, krdpc warns that it has changed before asking again.
- **Connect.** Double-click a computer, press Enter, or right-click it and choose Connect. krdpc
  starts `xfreerdp` with that computer's saved options and updates its "Last used" time. If
  `xfreerdp` is missing, the options cannot be turned into a command, or the connection fails,
  a message says what went wrong in plain words and shows the last lines `xfreerdp` printed.
  The commands set to run before connecting and after disconnecting are run, and a failing
  before-command stops the connection. Closing krdpc while connections are open asks first, and
  so does opening a second connection to a computer that is already open. Problems are shown one
  at a time, with `xfreerdp`'s log under **Show Details**, and a status-bar message confirms
  that a connection started. Ctrl+C in the terminal ends the connections and quits.
- **The list of computers.** The main window shows saved computers in a sortable table
  (Name, Group, Labels, Server, Plugin, Last used) with a search row, a toolbar and a "Total N
  items." footer, laid out like Remmina's main window and built with Qt so it follows your KDE
  theme. Search matches the name, group, labels and server as you type. Right-click a computer
  to edit, duplicate (as `COPY <name>`) or delete it.
- **Add and edit a computer.** A tabbed dialog (Basic, Advanced, Behaviour, Notes) holds the
  usual RDP options: user and domain, resolution (follow the window size or a fixed size),
  colour depth, quality, sound, clipboard, microphone, printers, USB, a shared folder, security,
  gateway, network, reconnect and time-out, keyboard layout, extra arguments, commands to run
  before and after, and a lock that stops changes.
- **Where it keeps them.** Each computer is one plain-text file in `~/.config/krdpc/`, readable
  by you only. No password is stored in it.
