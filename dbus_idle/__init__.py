import logging
import subprocess
from typing import List, Type

from pywayland.client import Display
from pywayland.protocol.wayland import WlDisplay

logger = logging.getLogger("dbus_idle")
logging.basicConfig(level=logging.ERROR)


class IdleMonitor:
    subclasses: List[Type["IdleMonitor"]] = []

    def __init__(self, *, idle_threshold: int = 120, debug: bool = False) -> None:
        self.idle_threshold = idle_threshold
        if debug:
            logger.setLevel(logging.DEBUG)

    def __init_subclass__(self) -> None:
        super().__init_subclass__()
        self.subclasses.append(self)

    @classmethod
    def get_monitor(cls, backend: str = "dbus", **kwargs) -> "IdleMonitor":
        for monitor_class in cls.subclasses:
            if backend.lower() in monitor_class.__name__.lower():
                try:
                    return monitor_class(**kwargs)
                except Exception:
                    logger.warning("Could not load %s", monitor_class, exc_info=True)
        raise RuntimeError(f"Could not find a working monitor for backend: {backend}")

    def get_idle_time(self) -> float:
        raise NotImplementedError()

    def is_idle(self) -> bool:
        return self.get_idle_time() > self.idle_threshold


class WaylandIdleMonitor(IdleMonitor):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.display = Display.connect()
        self.registry = self.display.get_registry()
        self.display.dispatch()
        self.display.roundtrip()

        # Placeholder: Wayland-specific idle protocol setup
        self.idle_manager = None  # Add Wayland idle manager setup
        if not self.idle_manager:
            raise RuntimeError("Wayland idle protocol not available")

    def get_idle_time(self) -> float:
        # Placeholder: Query Wayland compositor for idle time
        return 0.0


class SwayIdleMonitor(IdleMonitor):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        command = subprocess.run(
            ["which", "swayidle"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if command.returncode != 0:
            raise RuntimeError("swayidle not available on this system")

    def get_idle_time(self) -> float:
        try:
            output = subprocess.check_output(
                ["swayidle", "--idle", "1"], stderr=subprocess.PIPE
            ).decode()
            idle_time = float(output.strip())
            return idle_time
        except Exception as e:
            logger.error("Failed to get idle time from swayidle: %s", str(e))
            return 0.0


class DBusIdleMonitor(IdleMonitor):
    def get_idle_time(self) -> float:
        from dasbus.connection import SessionMessageBus

        session_bus = SessionMessageBus()
        idle_service = None
        for service in session_bus.proxy.ListNames():
            if "IdleMonitor" in service:
                service_path = f"/{service.replace('.', '/')}/Core"
                connection = session_bus.get_proxy(service, service_path)
                idle_service = connection
                break

        if not idle_service:
            raise RuntimeError("D-Bus IdleMonitor service not available")

        return int(idle_service.GetIdletime()) / 1000


class XprintidleIdleMonitor(IdleMonitor):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        command = subprocess.run(
            ["which", "xprintidle"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if command.returncode != 0:
            raise RuntimeError("xprintidle not available on this system")

    def get_idle_time(self) -> float:
        try:
            output = subprocess.check_output(
                ["xprintidle"], stderr=subprocess.PIPE
            ).decode()
            idle_time = float(output.strip()) / 1000
            return idle_time
        except Exception as e:
            logger.error("Failed to get idle time from xprintidle: %s", str(e))
            return 0.0


def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="dbus-idle", description="Get idle time from various backends"
    )
    parser.add_argument(
        "--backend",
        choices=["dbus", "wayland", "swayidle", "xprintidle"],
        default="dbus",
        help="Specify the backend to use for idle detection",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    try:
        monitor = IdleMonitor.get_monitor(backend=args.backend, debug=args.debug)
        idle_time = monitor.get_idle_time()
        print(f"Idle time: {idle_time} seconds")
    except Exception as e:
        logger.error("Failed to get idle time: %s", str(e))


if __name__ == "__main__":
    main()
