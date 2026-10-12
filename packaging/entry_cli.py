"""PyInstaller entry point of the console program (blt.exe)."""

import sys

from barbershop_tracks.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
