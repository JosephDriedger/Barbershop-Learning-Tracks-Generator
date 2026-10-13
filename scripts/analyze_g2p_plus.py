"""Reproducible numbers about OpenUtau's g2p-arpabet-plus.zip against its plain g2p-arpabet.zip.

    python scripts/analyze_g2p_plus.py <OpenUtau checkout> [--cmudict FILE] [--json]

The plain pack is CMUdict 0.07 (its header says so). The plus pack adds the entries this script
classifies. Nothing here decides a licence question: it only measures how much of the plus pack
can be traced to the plain (CMUdict) pack and how much cannot. With ``--cmudict`` (CMU's original
``cmudict-0.7b``) it also checks that the plain pack's dictionary has exactly the entries of
CMUdict. The checkout is only read.
"""

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

DATA = Path("OpenUtau.Core") / "G2p" / "Data"
VARIANT = re.compile(r"\(\d+\)$")


def parse(data: bytes) -> list[tuple[str, str]]:
    """(word, pronunciation) per dictionary line, lower-cased; comment and blank lines skipped.

    Latin-1 and an explicit split on line feeds: the files hold a few non-UTF-8 bytes, and
    str.splitlines would also split on some of them.
    """
    result: list[tuple[str, str]] = []
    for line in data.decode("latin-1").split(chr(10)):
        line = line.rstrip(chr(13))
        if not line.strip() or line.startswith(";"):
            continue
        word, _, pronunciation = line.partition("  ")
        result.append((word.lower(), " ".join(pronunciation.lower().split())))
    return result


def entries(pack: Path) -> list[tuple[str, str]]:
    with zipfile.ZipFile(pack) as archive:
        return parse(archive.read("dict.txt"))


def base_word(word: str) -> str:
    """The word without its variant number and without the apostrophe markers ARPAsing+ adds."""
    return VARIANT.sub("", word).strip("'")


def analyze(checkout: Path, cmudict: Path | None = None) -> dict[str, object]:
    plain_path = checkout / DATA / "g2p-arpabet.zip"
    plus_path = checkout / DATA / "g2p-arpabet-plus.zip"
    plain = entries(plain_path)
    plus_lines = entries(plus_path)
    plus = list(dict.fromkeys(plus_lines))  # the pack repeats lines that differ only in case
    plain_set = set(plain)
    plain_words = {base_word(word) for word, _ in plain}
    identical = [e for e in plus if e in plain_set]
    same_word = [e for e in plus if e not in plain_set and base_word(e[0]) in plain_words]
    new_words = [e for e in plus if e not in plain_set and base_word(e[0]) not in plain_words]
    new_base = sorted({base_word(w) for w, _ in new_words})
    result: dict[str, object] = {
        "plain_pack_sha256": hashlib.sha256(plain_path.read_bytes()).hexdigest(),
        "plus_pack_sha256": hashlib.sha256(plus_path.read_bytes()).hexdigest(),
        "plain_entries": len(plain),
        "plus_dictionary_lines": len(plus_lines),
        "plus_distinct_entries": len(plus),
        "plus_identical_to_plain_entry": len(identical),
        "plus_known_word_other_form": len(same_word),
        "plus_word_not_in_plain_pack": len(new_words),
        "plus_distinct_new_base_words": len(new_base),
        "plain_words_missing_from_plus": len(plain_words - {base_word(w) for w, _ in plus}),
        "examples_new_words": new_base[:: max(1, len(new_base) // 20)][:20],
    }
    if cmudict:
        official = parse(cmudict.read_bytes())
        result["cmudict_sha256"] = hashlib.sha256(cmudict.read_bytes()).hexdigest()
        result["cmudict_entries"] = len(official)
        result["plain_pack_equals_cmudict"] = set(official) == plain_set and len(official) == len(
            plain
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--cmudict", type=Path, help="CMU's original cmudict-0.7b to compare with")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = analyze(args.checkout, args.cmudict)
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
