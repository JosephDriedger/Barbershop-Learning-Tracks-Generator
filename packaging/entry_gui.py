"""PyInstaller entry point of the windowed application."""

import sys

from barbershop_tracks.frozen_fixups import restore_for_frozen_app

restore_for_frozen_app()  # before anything imports NumPy

try:
    from barbershop_tracks.ui.app import main
except ImportError as error:
    # A windowed program that cannot load Qt would otherwise show the loader's "Unhandled exception"
    # box and wait for a click. The packaging checks start the program on purpose without a Qt
    # library (packaging/replaceability-test.ps1) and the smoke tests run unattended: for those the
    # failure is a message on the error stream and an exit code, never a window.
    if "--smoke-test" not in sys.argv[1:]:
        raise
    if sys.stderr is not None:
        sys.stderr.write(f"BLT cannot start: {error}\n")
    sys.exit(3)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
