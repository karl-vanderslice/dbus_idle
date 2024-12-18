#!/usr/bin/env python3

import os
from pywayland.scanner.protocol import Protocol
from pywayland.scanner.printer import Printer

def generate_protocols():
    # Get the project root directory
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Protocol paths
    protocol_dir = os.path.join(project_root, "dbus_idle", "protocols")
    output_dir = os.path.join(project_root, "dbus_idle", "protocols")

    # Create protocol directory if it doesn't exist
    os.makedirs(protocol_dir, exist_ok=True)

    # Parse the protocol XML
    protocol_file = os.path.join(protocol_dir, "idle.xml")
    protocol = Protocol.parse_file(protocol_file)

    # Generate Python code
    printer = Printer(protocol)
    printer.write_protocol(output_dir)

if __name__ == "__main__":
    generate_protocols()
