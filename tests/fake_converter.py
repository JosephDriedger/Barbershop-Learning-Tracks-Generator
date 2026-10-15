"""A stand-in for MuseScore's and Audiveris's command lines, for the tests of BLT's conversion layer.

It is started through a ``.cmd`` wrapper (a program file BLT can run) with the arguments BLT passes:

    MuseScore:  -o OUTPUT INPUT
    Audiveris:  -batch -export -output DIR INPUT

``FAKE_CONVERTER_MODE`` chooses what it does: ``ok`` (write the MusicXML named by ``FAKE_CONVERTER_SOURCE``),
``fail`` (exit 3 with a message), ``no_output`` (exit 0, write nothing), ``empty`` (write an empty file),
``garbage`` (write something that is not XML), ``two`` (Audiveris: two pieces), ``hang`` (never finish),
``mxl`` (Audiveris: write a compressed ``.mxl``). Every start appends a line to ``FAKE_CONVERTER_LOG``.
"""

import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path


def main() -> int:
    arguments = sys.argv[1:]
    mode = os.environ.get("FAKE_CONVERTER_MODE", "ok")
    source = Path(os.environ["FAKE_CONVERTER_SOURCE"])
    log = os.environ.get("FAKE_CONVERTER_LOG")
    if log:
        with Path(log).open("a", encoding="utf-8") as handle:
            handle.write(" ".join(arguments) + "\n")
    environment_log = os.environ.get("FAKE_CONVERTER_ENV")
    if environment_log:  # what the converting program was started with
        Path(environment_log).write_text(json.dumps(dict(os.environ)), encoding="utf-8")
    if mode == "hang":
        time.sleep(600)
        return 0
    if mode == "fail":
        print("the file was written by a newer version", file=sys.stderr)
        return 3
    if "-o" in arguments:  # MuseScore
        output = Path(arguments[arguments.index("-o") + 1])
        if mode == "no_output":
            return 0
        if mode == "empty":
            output.write_bytes(b"")
        elif mode == "garbage":
            output.write_bytes(b"this is not xml")
        else:
            shutil.copyfile(source, output)
        return 0
    directory = Path(arguments[arguments.index("-output") + 1])  # Audiveris
    stem = Path(arguments[-1]).stem
    directory.mkdir(parents=True, exist_ok=True)
    if mode == "no_output":
        return 0
    if mode == "two":
        shutil.copyfile(source, directory / f"{stem}.mvt1.xml")
        shutil.copyfile(source, directory / f"{stem}.mvt2.xml")
        return 0
    if mode == "mxl":
        with zipfile.ZipFile(directory / f"{stem}.mxl", "w") as archive:
            archive.writestr(
                "META-INF/container.xml",
                '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>',
            )
            archive.write(source, "score.xml")
        return 0
    shutil.copyfile(source, directory / f"{stem}.xml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
