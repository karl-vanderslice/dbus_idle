#!/usr/bin/env python3

from pywayland.client import Display
from pywayland.protocol.wayland import WlSeat
from pywayland.protocol.ext_idle_notify_v1 import ExtIdleNotifierV1

def test_ext_idle():
    display = Display()
    display.connect()
    registry = display.get_registry()

    # Print available globals
    def handle_global(registry, id_, interface, version):
        print(f"Available interface: {interface} (version {version})")

    registry.dispatcher["global"] = handle_global
    display.roundtrip()

if __name__ == "__main__":
    test_ext_idle()
