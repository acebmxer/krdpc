"""Reading the size of a running xfreerdp window, and reusing it on the next connection.

xfreerdp has no option to remember its window and says nothing about its size when it ends,
so krdpc looks at the window while the session runs (through the X11 display, which on a
Wayland desktop is Xwayland) and keeps the last size and maximized state it saw.
FreeRDP's SDL client opens a native Wayland window that cannot be read this way.
"""

import ctypes
import ctypes.util
from dataclasses import dataclass

from krdpc.profile import Profile

# A window smaller than this is a splash or a progress box, not the session.
_MINIMUM = 200

# Options that already decide the window's size or position: the user's own, kept.
_SIZE_OPTIONS = ("/size:", "/w:", "/h:", "+workarea", "-workarea", "/workarea", "+multimon")


@dataclass(frozen=True)
class SessionWindow:
    """The last size an xfreerdp window had, and whether it was maximized."""

    width: int
    height: int
    maximized: bool = False

    def usable(self) -> bool:
        return self.width >= _MINIMUM and self.height >= _MINIMUM


def window_arguments(profile: Profile, window: SessionWindow | None, extra: list[str]) -> list[str]:
    """The options that open the window as it was last left, or none.

    A maximized window opens maximized (`+workarea`); any other size is asked for with
    `/size`, which "follow the window size" computers still resize from. A computer with a
    fixed size, full screen or several monitors keeps what its settings say, and so does one
    whose extra arguments already choose a size.
    """
    if (
        window is None
        or not (window.maximized or window.usable())
        or profile.resolution_mode == "fixed"
        or profile.fullscreen
        or profile.maximize
        or profile.multimon
        or any(arg == "/f" or arg.startswith(_SIZE_OPTIONS) for arg in extra)
    ):
        return []
    if window.maximized:
        return ["+workarea"]
    return [f"/size:{window.width}x{window.height}"]


# ---- reading a window ---------------------------------------------------------------------


class _X11:
    """Just enough of libX11 to read a window's size, state and process."""

    ANY_PROPERTY_TYPE = 0
    SUCCESS = 0

    def __init__(self, library: ctypes.CDLL) -> None:
        self.lib = library
        library.XOpenDisplay.restype = ctypes.c_void_p
        library.XOpenDisplay.argtypes = [ctypes.c_char_p]
        library.XCloseDisplay.argtypes = [ctypes.c_void_p]
        library.XDefaultRootWindow.restype = ctypes.c_ulong
        library.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        library.XInternAtom.restype = ctypes.c_ulong
        library.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        library.XFree.argtypes = [ctypes.c_void_p]
        library.XGetWindowProperty.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_long,
            ctypes.c_long,
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
        ]
        library.XGetGeometry.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
        ]

    def values(self, display, window: int, name: str) -> list[int]:
        """A property made of 32-bit numbers (atoms, window ids, a process id); empty if unset."""
        lib = self.lib
        actual_type, actual_format = ctypes.c_ulong(), ctypes.c_int()
        count, remaining = ctypes.c_ulong(), ctypes.c_ulong()
        data = ctypes.POINTER(ctypes.c_ubyte)()
        status = lib.XGetWindowProperty(
            display,
            window,
            lib.XInternAtom(display, name.encode(), 0),
            0,
            1024,
            0,
            self.ANY_PROPERTY_TYPE,
            ctypes.byref(actual_type),
            ctypes.byref(actual_format),
            ctypes.byref(count),
            ctypes.byref(remaining),
            ctypes.byref(data),
        )
        if status != self.SUCCESS or not data:
            return []
        try:
            if actual_format.value != 32:
                return []
            # Xlib stores 32-bit items as C longs.
            items = ctypes.cast(data, ctypes.POINTER(ctypes.c_long))
            return [items[index] & 0xFFFFFFFF for index in range(count.value)]
        finally:
            lib.XFree(data)

    def size(self, display, window: int) -> tuple[int, int] | None:
        root, x, y = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_int()
        width, height = ctypes.c_uint(), ctypes.c_uint()
        border, depth = ctypes.c_uint(), ctypes.c_uint()
        ok = self.lib.XGetGeometry(
            display,
            window,
            ctypes.byref(root),
            ctypes.byref(x),
            ctypes.byref(y),
            ctypes.byref(width),
            ctypes.byref(height),
            ctypes.byref(border),
            ctypes.byref(depth),
        )
        return (width.value, height.value) if ok else None


def _load() -> _X11 | None:
    name = ctypes.util.find_library("X11")
    if name is None:
        return None
    try:
        return _X11(ctypes.CDLL(name))
    except OSError:
        return None


def read_session_window(process_id: int) -> SessionWindow | None:
    """The size and maximized state of the window of this process, or None.

    None when there is no X11 display, the process has no window (yet) or anything about
    reading it fails: remembering the size is a convenience, never a reason to fail.
    """
    x11 = _load()
    if x11 is None:
        return None
    display = x11.lib.XOpenDisplay(None)
    if not display:
        return None
    try:
        root = x11.lib.XDefaultRootWindow(display)
        maximized_atoms = {
            x11.lib.XInternAtom(display, name, 0)
            for name in (b"_NET_WM_STATE_MAXIMIZED_HORZ", b"_NET_WM_STATE_MAXIMIZED_VERT")
        }
        best: SessionWindow | None = None
        for window in x11.values(display, root, "_NET_CLIENT_LIST"):
            if process_id not in x11.values(display, window, "_NET_WM_PID"):
                continue
            size = x11.size(display, window)
            if size is None:
                continue
            state = set(x11.values(display, window, "_NET_WM_STATE"))
            found = SessionWindow(size[0], size[1], maximized_atoms <= state)
            if found.usable() and (
                best is None or found.width * found.height > best.width * best.height
            ):
                best = found
        return best
    except (OSError, ValueError, ctypes.ArgumentError):
        return None
    finally:
        x11.lib.XCloseDisplay(display)
