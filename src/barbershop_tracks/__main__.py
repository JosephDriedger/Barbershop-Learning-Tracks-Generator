"""``python -m barbershop_tracks`` launches the GUI."""

import sys

from barbershop_tracks.ui.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
