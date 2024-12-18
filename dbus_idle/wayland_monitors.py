from typing import Optional, Any
import time
import logging

from pywayland.client import Display
from pywayland.protocol.wayland import WlSeat
from pywayland.protocol.ext_idle_notify_v1 import ExtIdleNotifierV1

logger = logging.getLogger(__name__)

class WaylandMonitorBase:
    def __init__(self, idle_threshold: int = 120):
        self.idle_threshold = idle_threshold
        self.display = Display()
        self.display.connect()
        self.registry = self.display.get_registry()
        self.seat: Optional[WlSeat] = None

        self.registry.dispatcher["global"] = self._handle_global
        self.display.roundtrip()

        if not self.seat:
            raise RuntimeError("No Wayland seat found")

    def _handle_global(self, registry: Any, id_: int, interface: str, version: int) -> None:
        if interface == "wl_seat":
            self.seat = registry.bind(id_, WlSeat, min(version, 7))

    def cleanup(self):
        if self.display:
            self.display.disconnect()

class ExtIdleMonitor(WaylandMonitorBase):
    def __init__(self, idle_threshold: int = 120):
        super().__init__(idle_threshold)
        self.idle_manager: Optional[ExtIdleNotifierV1] = None
        self.notifier = None
        self.idle_since: Optional[int] = None
        self.last_activity = time.time()

        self.registry.dispatcher["global"] = self._handle_ext_idle_global
        self.display.roundtrip()

        if not self.idle_manager:
            raise RuntimeError("ext-idle-notify manager not found")

        self._setup_idle_notifier()

    def _handle_ext_idle_global(self, registry: Any, id_: int, interface: str, version: int) -> None:
        super()._handle_global(registry, id_, interface, version)
        if interface == "ext_idle_notify_v1":
            self.idle_manager = registry.bind(id_, ExtIdleNotifierV1, version)

    def _setup_idle_notifier(self):
        self.notifier = self.idle_manager.get_idle_notification(
            self.seat,
            self.idle_threshold * 1000
        )
        self.notifier.dispatcher["idle"] = self._handle_idle
        self.notifier.dispatcher["resumed"] = self._handle_resumed

    def _handle_idle(self, notifier: Any, timestamp: int) -> None:
        self.idle_since = timestamp

    def _handle_resumed(self, notifier: Any) -> None:
        self.idle_since = None
        self.last_activity = time.time()

    def get_idle_time(self) -> float:
        self.display.dispatch_pending()
        if self.idle_since is not None:
            return (time.time_ns() // 1_000_000 - self.idle_since) / 1000.0
        return time.time() - self.last_activity
