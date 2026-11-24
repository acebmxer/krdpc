# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

krdpc is a native KDE app that keeps a list of remote computers and opens each
one with FreeRDP's `xfreerdp`.

## [Unreleased]

### Fixed

- **Maximizing the remote window under WSL.** With FreeRDP's SDL client (used under WSL),
  a maximized window could stay black: at an odd window height (1920×995 maximized) FreeRDP
  throws away the remote computer's H.264 picture. Under WSL, computers set to **Follow the
  window size** now get their picture in the progressive format instead, which has no such
  limit. A computer set to a fixed size opened a window that could not change size, and
  maximizing it made WSL end the connection; under WSL its picture is now scaled to fit the
  window. Full screen is unchanged (#16).

## [0.1.0] - 2026-11-16

**The first release.** krdpc keeps a list of your remote computers and opens each one with
FreeRDP, with packages for Fedora, Debian, Ubuntu and Arch Linux. Coming from a beta: krdpc
0.1.0-beta.4 and later offer this release as an update; with an earlier beta, install the
0.1.0 package by hand once.

### Added

- **Updates.** krdpc checks for a new version shortly after it starts (Preferences can turn
  this off), and **Check for updates…** in the main menu checks at once. **Update now**
  downloads the package for your distribution from the Releases page, checks it against
  `SHA256SUMS`, installs it with `dnf`, `apt-get` or `pacman` after your desktop asks for your
  password, and offers to restart krdpc. **Include beta versions** in Preferences offers betas
  as well as stable releases. If installing is not allowed, krdpc shows the command to run
  instead. A copy installed from a clone only says a new version is out. About krdpc now shows
  the exact version, beta number included (#6), and so does the right end of the main window's
  status bar, e.g. `krdpc 0.1.0-beta.2` (#9). The result of a check now always reaches the
  window; before, it was often lost, so no update was ever offered (#10). With no desktop
  password box (Fedora under WSL), installing now stops at once and shows the command to run,
  instead of waiting for a password typed into the terminal krdpc was started from (#14).
- **Packages.** A `.rpm` for Fedora, a `.deb` for Debian 13 and Ubuntu 26.04 and newer, and a
  package for Arch Linux, each depending on the distribution's own FreeRDP 3, PySide6 and
  `keyring`. krdpc now also finds FreeRDP 3's `xfreerdp3` program, which is how Debian and
  Ubuntu name it. The README says how to install them. On a system with no desktop icon theme
  for Qt (such as Fedora under WSL) the toolbar takes its icons from Breeze or Adwaita, which
  the packages now recommend, instead of showing blank buttons, and the main menu button reads
  **Menu** if no icon can be found (#7).
- **Documentation.** The README now covers installing, updating and removing krdpc, using it,
  what to do when something goes wrong, and what is not built.
- **Preferences.** **Preferences…** in the main menu (Ctrl+,) sets krdpc's colours (follow the
  desktop's theme, light or dark, for desktops with no theme for Qt to follow, such as Fedora
  under WSL; #5), the size of the icons in the list (small, medium or large), whether deleting a computer asks first, whether krdpc remembers
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
  in the edit dialog. KDE's krdp server refuses a wrong password by ending the session a moment
  after connecting; krdpc now says the password may be wrong and forgets the saved one, instead
  of showing a message about another session (#17). If the computer uses a gateway, its password is asked for and remembered
  too. The password is sent to `xfreerdp` through a pipe, so it is never on its command line or
  in your profile file. A blank domain is sent as blank, so `xfreerdp` no longer stops to ask for
  one. Where no desktop session has started the wallet (such as Fedora under WSL), krdpc starts
  the installed KDE Wallet itself and tells it where the screen is, so it no longer closes at
  once (#11); if there is no wallet at all it says so in plain words and keeps asking for the
  password instead (#8).
- **Certificate dialog.** When the remote computer's certificate cannot be verified (for example
  a self-signed one), krdpc shows its subject, issuer, dates and SHA-256 fingerprint and asks
  whether to trust it, instead of `xfreerdp` asking in the terminal. Trusting it saves the
  fingerprint for that computer only; the Advanced tab shows it with a **Forget** button. If the
  certificate later differs, krdpc warns that it has changed before asking again.
- **Connect.** Double-click a computer, press Enter, or right-click it and choose Connect. krdpc
  starts `xfreerdp` with that computer's saved options and updates its "Last used" time. If
  `xfreerdp` is missing, the options cannot be turned into a command, or the connection fails,
  a message says what went wrong in plain words and shows the last lines `xfreerdp` printed.
  An option FreeRDP cannot understand (in the extra arguments, for example) is reported as such,
  with FreeRDP's own words about it, instead of as a licensing problem (#13).
  The commands set to run before connecting and after disconnecting are run, and a failing
  before-command stops the connection. Closing krdpc while connections are open asks first, and
  so does opening a second connection to a computer that is already open. Problems are shown one
  at a time, with `xfreerdp`'s log under **Show Details**, and a status-bar message confirms
  that a connection started. Ctrl+C in the terminal ends the connections and quits. When there is
  no X11 display for `xfreerdp` (such as Fedora under WSL when WSL's X11 display has stopped),
  krdpc starts FreeRDP's SDL client (`sdl-freerdp`), which also works on Wayland; it asks about
  untrusted certificates in its own window. The `.deb` recommends `freerdp3-sdl`, which provides
  it on Debian and Ubuntu (#12). Under WSL the SDL client is started with software rendering,
  because with WSL's GPU driver it crashed as soon as it drew its window (#15). Closing the SDL client's window ends the session
  quietly instead of showing "The connection was cancelled before it finished" (#18).
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
