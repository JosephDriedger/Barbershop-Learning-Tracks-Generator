"""Command-line entry point.

The core library must be usable without the GUI. Real subcommands arrive in later
milestones; for now this only proves the entry point works.
"""

import argparse
from collections.abc import Sequence

from barbershop_tracks import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="barbershop-tracks",
        description="Generate four-part barbershop learning tracks from MusicXML.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
