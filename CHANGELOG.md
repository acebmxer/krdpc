# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

krdpc is a native KDE app that keeps a list of remote computers and opens each
one with FreeRDP's `xfreerdp`.

## [Unreleased]

### Added

- **Connect.** Double-click a computer, press Enter, or right-click it and choose Connect. krdpc
  starts `xfreerdp` with that computer's saved options and updates its "Last used" time. If
  `xfreerdp` is missing, the options cannot be turned into a command, or the connection fails,
  a message says what went wrong in plain words and shows the last lines `xfreerdp` printed.
  The commands set to run before connecting and after disconnecting are run, and a failing
  before-command stops the connection. Closing krdpc while connections are open asks first, and
  so does opening a second connection to a computer that is already open. Problems are shown one
  at a time, with `xfreerdp`'s log under **Show Details**, and a status-bar message confirms
  that a connection started. Ctrl+C in the terminal ends the connections and quits.
  Until the password box arrives, `xfreerdp` asks for the password in the terminal krdpc was
  started from.
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
