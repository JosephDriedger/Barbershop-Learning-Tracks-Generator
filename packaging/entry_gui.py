"""PyInstaller entry point of the windowed application."""

import sys

from barbershop_tracks.frozen_fixups import restore_for_frozen_app

restore_for_frozen_app()  # before anything imports NumPy

from barbershop_tracks.ui.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
