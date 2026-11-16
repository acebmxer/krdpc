"""Starting FreeRDP (`xfreerdp`, or its SDL client without X11) and reporting how it ended."""

import os
import re
import shutil
import socket
import sys
from collections import deque
from collections.abc import Callable

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from krdpc.certificate import parse_certificate
from krdpc.command import CommandError, build_command
from krdpc.profile import Profile
from krdpc.store import ProfileStore

# Exit codes that mean the session simply ended: 0 success, 2 logged off,
# 11 closed by the user (FreeRDP's XF_EXIT_CODE list; its SDL client uses the same numbers).
NORMAL_EXIT_CODES = frozenset({0, 2, 11})

_EXIT_MESSAGES = {
    1: "The remote computer disconnected.",
    3: "The session ended because it sat idle for too long.",
    5: "Another connection took over this session.",
    7: "The remote computer refused the connection.",
    9: "Your account is not allowed to connect remotely.",
    128: "FreeRDP did not understand one of the options. Check the extra arguments.",
    131: "Could not connect. Check the address and that the computer is switched on.",
    132: "Sign-in was refused. Check the username, domain and password.",
    133: "No security method both sides accept. Try another Security setting on the Advanced tab.",
    134: "Sign-in failed. Check the username, domain and password.",
    135: "That account is locked out.",
    137: "Could not connect. Check the address and that the computer is switched on.",
    139: "The address could not be looked up.",
    140: "The address could not be looked up.",
    141: "Could not connect. Check the address and that the computer is switched on.",
    143: "The secure (TLS) connection failed. Try ignoring certificate errors on the Advanced tab.",
    144: "That account does not have the rights to connect.",
    145: "The connection was cancelled before it finished.",
    147: "The connection to the remote computer broke while connecting.",
    148: "That password has expired.",
    149: "That password must be changed before you can sign in.",
    151: "That account is disabled.",
    154: "The password is wrong.",
    155: "Access was denied. Check the username and password.",
    157: "That account has expired.",
    159: "The username or password is missing.",
    160: "The remote computer is still starting up. Try again in a minute.",
    161: "The remote computer requires NLA. Set Security to NLA on the Advanced tab.",
}

_OPTIONS_NOT_UNDERSTOOD = _EXIT_MESSAGES[128]

# FreeRDP 3.33.1 stops with 22, 23, 24 or 255 when it cannot parse its options, codes that
# otherwise mean licensing or other errors, so that case is recognised by what it prints:
# an ERROR from its command-line parser, or its usage text, which nothing else prints.
_OPTION_ERROR = re.compile(
    r"^.*\[ERROR\]\[com\.(?:winpr\.commandline|freerdp\.client\.common\.cmdline)\]"
    r"(?: - )?(?P<what>.*)$",
    re.MULTILINE,
)
_USAGE_BANNER = re.compile(r"^\S+ - A Free Remote Desktop Protocol Implementation$", re.MULTILINE)

# Exit codes for a refused sign-in: a remembered password that gets one is forgotten.
LOGIN_REFUSED_CODES = frozenset({132, 134, 154, 155})

# FreeRDP 3's program is `xfreerdp` on Fedora and Arch but `xfreerdp3` on Debian and Ubuntu,
# where plain `xfreerdp` may be FreeRDP 2, which krdpc does not support. The 3 name goes first.
XFREERDP_NAMES = ("xfreerdp3", "xfreerdp")

# FreeRDP 3's SDL client draws on Wayland as well as X11, and takes the same options and
# `/args-from:stdin`. It is used when there is no X11 display for xfreerdp: under WSL when
# Xwayland is not running, or a Wayland desktop without Xwayland. xfreerdp stays the first
# choice wherever X11 works, because krdpc reads its certificate prompt (the SDL client
# asks about certificates in its own window). Same naming as above: the 3 name first.
SDL_NAMES = ("sdl-freerdp3", "sdl-freerdp")

# Under WSL, Mesa drives the Windows GPU through its `d3d12` driver, and the SDL client crashes
# (segmentation fault) as soon as it draws its window. Software rendering avoids it, and a
# remote desktop window does not need the GPU.
_WSL_SDL_ENVIRONMENT = {"LIBGL_ALWAYS_SOFTWARE": "1"}

_MISSING = (
    "xfreerdp was not found. Install the freerdp package, "
    "or set where it is in Preferences, then try again."
)
_NO_DISPLAY = (
    "There is no X11 display for xfreerdp, and FreeRDP's SDL client, which works without "
    "one, was not found. Install it (Fedora and Arch: package freerdp; Debian and Ubuntu: "
    "package freerdp3-sdl), then try again."
)
_TAIL_LINES = 12
_OUTPUT_LIMIT = 200_000  # characters of xfreerdp output kept, to find the certificate in


def x11_display_available(environ=os.environ) -> bool:
    """True if `$DISPLAY` names an X11 display that answers.

    A local display (`:0`, `unix:0.0`) is checked by connecting to its socket, as an X11
    program would; a remote one (`host:0`) is trusted as set. Under WSL, `DISPLAY=:0` is set
    even when Xwayland has crashed and its socket is gone.
    """
    display = environ.get("DISPLAY", "").strip()
    host, _colon, number = display.rpartition(":")
    number = number.split(".")[0]
    if not display or not number.isdigit():
        return False
    if host not in ("", "unix"):
        return True
    path = f"/tmp/.X11-unix/X{number}"
    for address in (path, "\0" + path):  # the socket file, then Linux's abstract socket
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(1)
            try:
                probe.connect(address)
            except OSError:
                continue
            return True
    return False


def running_under_wsl(environ=os.environ, osrelease: str = "/proc/sys/kernel/osrelease") -> bool:
    """True inside Windows Subsystem for Linux."""
    if environ.get("WSL_DISTRO_NAME") or environ.get("WSL_INTEROP"):
        return True
    try:
        with open(osrelease) as handle:
            return "microsoft" in handle.read().lower()
    except OSError:
        return False


def explain_exit(code: int, program: str = "xfreerdp") -> str:
    """A plain sentence for a FreeRDP exit code that is not a normal end."""
    if code in _EXIT_MESSAGES:
        return _EXIT_MESSAGES[code]
    if 16 <= code <= 26:
        return "The remote computer reported a licensing problem."
    if 32 <= code <= 127:
        return "The remote computer reported a problem."
    return f"{program} stopped with code {code}."


def option_errors(output: str) -> list[str] | None:
    """What FreeRDP said about options it could not parse, or None if it parsed them all.

    An empty list means it printed only its usage text."""
    if not (_OPTION_ERROR.search(output) or _USAGE_BANNER.search(output)):
        return None
    return [match["what"].strip() for match in _OPTION_ERROR.finditer(output)]


def _program(run: "_Run") -> str:
    """The FreeRDP program's name, as messages show it."""
    return os.path.basename(run.process.program()) or "FreeRDP"


class _Run:
    """One connection: its profile, its process and the last lines it printed."""

    def __init__(self, profile: Profile, process: QProcess) -> None:
        self.profile = profile
        self.process = process
        self.tail: deque[str] = deque(maxlen=_TAIL_LINES)
        self.partial = ""
        self.text = ""


class Launcher(QObject):
    """Starts connections. Signals carry the profile id.

    A finished QProcess is left owned by the launcher rather than scheduled for
    deletion: deleting it from inside its own `finished` signal crashed Qt when
    the launcher was torn down soon after. It is a few kilobytes per connection.
    """

    started = Signal(str)
    ended = Signal(str)
    failed = Signal(str, str)  # profile id, what went wrong
    certificate_untrusted = Signal(str, object)  # profile id, CertificateInfo
    login_rejected = Signal(str)  # profile id: the remote computer refused the sign-in

    def __init__(
        self,
        store: ProfileStore,
        find_executable: Callable[[str], str | None] = shutil.which,
        parent: QObject | None = None,
        has_x11_display: Callable[[], bool] = lambda: True,
        under_wsl: Callable[[], bool] = lambda: False,
    ) -> None:
        """`has_x11_display` decides between xfreerdp and the SDL client, and `under_wsl`
        whether the SDL client needs software rendering; the app passes
        `x11_display_available` and `running_under_wsl`."""
        super().__init__(parent)
        self._store = store
        self._find = find_executable
        self._has_x11_display = has_x11_display
        self._under_wsl = under_wsl
        self._runs: list[_Run] = []
        self._stopping = False

    def active_count(self) -> int:
        return len(self._runs)

    def active_count_for(self, profile_id: str) -> int:
        """How many connections to this computer are open or still starting."""
        return sum(1 for run in self._runs if run.profile.id == profile_id)

    def stop_all(self) -> None:
        """End every connection. What follows is not reported as a failure."""
        self._stopping = True
        for run in list(self._runs):
            run.process.terminate()
            run.process.waitForFinished(2000)

    def connect_to(self, profile: Profile, password: str = "", gateway_password: str = "") -> None:
        """Start a connection. The passwords go to FreeRDP through a pipe, never its arguments."""
        if self._has_x11_display():
            # xfreerdp first; the SDL client if only that is installed.
            names, missing = XFREERDP_NAMES + SDL_NAMES, _MISSING
        else:
            names, missing = SDL_NAMES, _NO_DISPLAY
        executable = next((found for name in names if (found := self._find(name))), None)
        if executable is None:
            self.failed.emit(profile.id, missing)
            return
        try:
            command = build_command(profile, executable, password, gateway_password or None)
        except CommandError as error:
            self.failed.emit(profile.id, str(error))
            return
        if profile.before_command:
            self._run_before(profile, command)
        else:
            self._start(profile, command)

    # ---- the before command ----------------------------------------------

    def _run_before(self, profile: Profile, command: list[str]) -> None:
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        def done(code: int, status: QProcess.ExitStatus) -> None:
            output = bytes(process.readAll()).decode(errors="replace").strip()
            if status == QProcess.ExitStatus.NormalExit and code == 0:
                self._start(profile, command)
            else:
                self.failed.emit(
                    profile.id,
                    f"The command to run before connecting failed (code {code}).\n{output}".strip(),
                )

        process.finished.connect(done)
        process.start("/bin/sh", ["-c", profile.before_command])

    # ---- FreeRDP ----------------------------------------------------------

    def _start(self, profile: Profile, command: list[str]) -> None:
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        if os.path.basename(command[0]) in SDL_NAMES and self._under_wsl():
            environment = QProcessEnvironment.systemEnvironment()
            for name, value in _WSL_SDL_ENVIRONMENT.items():
                if not environment.contains(name):  # a value the user set is kept
                    environment.insert(name, value)
            process.setProcessEnvironment(environment)
        run = _Run(profile, process)
        process.readyRead.connect(lambda: self._read(run))
        process.finished.connect(lambda code, status: self._finished(run, code, status))
        process.errorOccurred.connect(lambda error: self._error(run, error))
        self._runs.append(run)
        # The arguments, password included, are read from the pipe: one per line.
        process.start(command[0], ["/args-from:stdin"])
        if process.waitForStarted(5000):
            process.write(("\n".join(command[1:]) + "\n").encode())
            process.closeWriteChannel()
            try:
                self._store.touch_last_used(profile.id)
            except (KeyError, OSError, ValueError):
                pass  # the list's "Last used" is a convenience, never a reason to fail
            self.started.emit(profile.id)

    def _read(self, run: _Run) -> None:
        text = bytes(run.process.readAll()).decode(errors="replace")
        sys.stdout.write(text)
        sys.stdout.flush()
        run.text = (run.text + text)[-_OUTPUT_LIMIT:]
        *lines, run.partial = (run.partial + text).split("\n")
        run.tail.extend(line for line in lines if line.strip())

    def _error(self, run: _Run, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and run in self._runs:
            self._runs.remove(run)
            self.failed.emit(run.profile.id, _MISSING)

    def _finished(self, run: _Run, code: int, status: QProcess.ExitStatus) -> None:
        self._read(run)
        if run.partial.strip():
            run.tail.append(run.partial)
        if run in self._runs:
            self._runs.remove(run)
        profile = run.profile
        if profile.after_command:
            QProcess.startDetached("/bin/sh", ["-c", profile.after_command])
        if self._stopping:
            self.ended.emit(profile.id)
            return
        details = "\n".join(run.tail)
        if status == QProcess.ExitStatus.CrashExit:
            problem = f"{_program(run)} stopped unexpectedly."
        elif code in NORMAL_EXIT_CODES:
            self.ended.emit(profile.id)
            return
        elif (errors := option_errors(run.text)) is not None:
            # The usage text that follows the errors would only bury them.
            problem, details = _OPTIONS_NOT_UNDERSTOOD, "\n".join(errors)
        else:
            problem = explain_exit(code, _program(run))
        certificate = parse_certificate(run.text)
        if certificate is not None:
            self.certificate_untrusted.emit(profile.id, certificate)
            return
        if code in LOGIN_REFUSED_CODES:
            self.login_rejected.emit(profile.id)
        self.failed.emit(profile.id, f"{problem}\n\n{details}" if details else problem)
