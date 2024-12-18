{
  pkgs ? import <nixpkgs> { },
}:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python3
    python3Packages.pywayland
    wayland
    wayland-protocols
    pkg-config
    # Add development tools
    python3Packages.pip
    python3Packages.wheel
    python3Packages.setuptools
    python3Packages.dasbus
    xprintidle
    swayidle
  ];

  shellHook = ''
    export PYTHONPATH="$PWD:$PYTHONPATH"
    # Print PyWayland version for debugging
    python3 -c "import pywayland; print(f'PyWayland version: {pywayland.__version__}')"
  '';
}
