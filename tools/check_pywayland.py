#!/usr/bin/env python3

import pywayland
import pkgutil

print(f"PyWayland version: {pywayland.__version__}")
print("\nAvailable modules:")
for importer, modname, ispkg in pkgutil.walk_packages(pywayland.__path__, pywayland.__name__ + '.'):
    print(modname)
