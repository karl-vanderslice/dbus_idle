import logging
import subprocess
import time
import ctypes
import ctypes.util
from typing import Any, List, Type

from pywayland.client import Display
from pywayland.protocol.wayland import WlSeat, WlRegistry
from .protocols.idle import OrgKdeKwinIdle
from .wayland_monitors import ExtIdleMonitor

logger = logging.getLogger("dbus_idle")
logging.basicConfig(level=logging.ERROR)

class IdleMonitor:
    subclasses: List[Type["IdleMonitor"]] = []
    def __init__(self, *, idle_threshold: int = 120, debug: bool=False) -> None:
        self.idle_threshold = idle_threshold
        if debug:
            logger.setLevel(logging.DEBUG)
    def __init_subclass__(self) -> None:
        super().__init_subclass__()
        self.subclasses.append(self)
    @classmethod
    def get_monitor(cls, **kwargs) -> "IdleMonitor":
        for monitor_class in cls.subclasses:
            try:
                return monitor_class(**kwargs)
            except Exception:
                logger.warning("Could not load %s", monitor_class, exc_info=True)
        raise RuntimeError("Could not find a working monitor.")
    def get_dbus_idle(self) -> float:
        for monitor_class in self.subclasses:
            try:
                idle_time = monitor_class().get_dbus_idle()
                logger.debug("Using: %s", monitor_class.__name__)
                return idle_time
            except Exception:
                logger.warning("Could not load %s", monitor_class.__name__, exc_info=False)
        return None
    def is_idle(self) -> bool:
        return self.get_dbus_idle() > self.idle_threshold


class WaylandKdeIdleMonitor(IdleMonitor):
    """
    Idle monitor for KDE on Wayland using the org_kde_kwin_idle protocol.
    The protocol signals "idle" after the threshold, and "resumed" on activity.
    We track the last known user activity timestamp to determine idle time.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.display = Display()
        self.display.connect()
        self.registry = self.display.get_registry()

        self.idle_manager = None
        self.seat = None
        self.idle_timeout = None

        self.last_activity = time.time()
        self.idle_active = False

        self.registry.add_listener(self._registry_handler)
        self.display.roundtrip()

        if not self.idle_manager or not self.seat:
            raise AttributeError("Could not find idle manager or seat on Wayland.")

        # Convert threshold to milliseconds as per the protocol's expectation
        threshold_ms = self.idle_threshold * 1000
        self.idle_timeout = self.idle_manager.get_idle_timeout(self.seat, threshold_ms)
        self.idle_timeout.add_listener(self._idle_timeout_handler)

        # Prime a roundtrip so we are ready for events
        self.display.dispatch_pending()

    def _registry_handler(self, registry: WlRegistry, name: int, interface: str, version: int) -> None:
        if interface == 'wl_seat':
            self.seat = registry.bind(name, WlSeat, min(version, 7))
        elif interface == 'org_kde_kwin_idle':
            self.idle_manager = registry.bind(name, OrgKdeKwinIdle, version)

    def _idle_timeout_handler(self, idle_timeout, event_name):
        # According to the kde-idle protocol, events are 'idle' or 'resumed'
        if event_name == 'idle':
            self.idle_active = True
        elif event_name == 'resumed':
            self.idle_active = False
            self.last_activity = time.time()

    def get_dbus_idle(self) -> float:
        # Pump the event queue so we process any idle/resume events
        self.display.dispatch_pending()

        if self.idle_active:
            # If idle, idle time is at least the threshold
            return self.idle_threshold
        else:
            # If not idle, compute how long since last activity
            return time.time() - self.last_activity


class DBusIdleMonitor(IdleMonitor):
    def __init__(self, **kwargs) -> None:
        from dasbus.connection import SessionMessageBus
        super().__init__(**kwargs)
        session_bus = SessionMessageBus()
        for service in session_bus.proxy.ListNames():
            if 'IdleMonitor' in service:
                service_path = f"/{service.replace('.', '/')}/Core"
                self.connection = session_bus.get_proxy(service, service_path)
                self.service = service
                break
        if not hasattr(self, 'connection'):
            raise AttributeError()
    def get_dbus_idle(self) -> float:
        return int(self.connection.GetIdletime()) / 1000.0


class XprintidleIdleMonitor(IdleMonitor):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        command = subprocess.run(["which", "xprintidle"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if command.returncode != 0:
            raise AttributeError()
    def get_dbus_idle(self) -> float:
        stdout = subprocess.run('xprintidle', stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode("UTF-8")
        return int(stdout.strip())/1000.0


class X11IdleMonitor(IdleMonitor):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        class XScreenSaverInfo(ctypes.Structure):
            _fields_ = [
                ("window", ctypes.c_ulong),
                ("state", ctypes.c_int),
                ("kind", ctypes.c_int),
                ("since", ctypes.c_ulong),
                ("idle", ctypes.c_ulong),
                ("event_mask", ctypes.c_ulong),
            ]
        lib_x11 = self._load_lib("X11")
        lib_x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib_x11.XOpenDisplay.restype = ctypes.c_void_p
        lib_x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib_x11.XDefaultRootWindow.restype = ctypes.c_uint32
        self.display = lib_x11.XOpenDisplay(None)
        if self.display is None:
            raise AttributeError()
        self.root_window = lib_x11.XDefaultRootWindow(self.display)
        self.lib_xss = self._load_lib("Xss")
        self.lib_xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(XScreenSaverInfo)]
        self.lib_xss.XScreenSaverQueryInfo.restype = ctypes.c_int
        self.lib_xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
        self.xss_info = self.lib_xss.XScreenSaverAllocInfo()

    def get_dbus_idle(self) -> float:
        self.lib_xss.XScreenSaverQueryInfo(self.display, self.root_window, self.xss_info)
        return self.xss_info.contents.idle/1000.0

    def _load_lib(self, name: str) -> Any:
        path = ctypes.util.find_library(name)
        if path is None:
            raise OSError(f"Could not find library `{name}`")
        return ctypes.cdll.LoadLibrary(path)


class WindowsIdleMonitor(IdleMonitor):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        import win32api
        self.win32api = win32api
    def get_dbus_idle(self) -> float:
        current_tick = self.win32api.GetTickCount()
        last_tick = self.win32api.GetLastInputInfo()
        return (current_tick - last_tick)/1000.0


if __name__ == "__main__":
    monitor = IdleMonitor.get_monitor(idle_threshold=120, debug=True)
    print("Idle time:", monitor.get_dbus_idle(), "seconds")
    print("Is idle:", monitor.is_idle())
