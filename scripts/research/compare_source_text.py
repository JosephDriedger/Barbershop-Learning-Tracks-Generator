"""Measure how much text two C++ source files share (evidence for a licensing reviewer, not a verdict).

Usage: python scripts/research/compare_source_text.py A.h B.h [--k 6 --k 10]

For two files this reports, after removing comments and whitespace:

* lines that are identical in both (a line of code is identical only if every token is);
* the share of A's token k-grams that also occur in B (and the reverse), with identifiers and numbers
  kept as written ("verbatim") and with them replaced by placeholders ("structure": the shape of the
  code regardless of naming).

Copying shows up as long runs of verbatim shared k-grams; two independent implementations of the same
textbook algorithm share short, common idioms (loops, ``const double``) and little else. The numbers
are a first indication, never a conclusion: whether one file is derived from another is a legal and
factual judgement that includes how the file came to be written (see
docs/review/source-history-review-packet.md). Nothing is copied, stored or sent anywhere.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TOKEN = re.compile(
    r"""
    [A-Za-z_][A-Za-z_0-9]*          # identifiers and keywords
  | \d+(?:\.\d*)?(?:[eE][+-]?\d+)?  # numbers
  | ::|->|<<|>>|<=|>=|==|!=|&&|\|\||\+\+|--|[-+*/%=<>!&|^~?:;,.(){}\[\]]
    """,
    re.VERBOSE,
)
KEYWORDS = {
    "const", "double", "int", "size_t", "for", "if", "else", "return", "while", "void", "class",
    "public", "private", "struct", "template", "typename", "static", "inline", "bool", "auto",
    "std", "vector", "namespace", "operator", "this", "true", "false", "unsigned", "long", "using",
    "assert", "break", "continue", "do", "new", "delete", "sizeof", "enum", "switch", "case",
    "default", "float", "char", "explicit", "virtual", "friend", "typedef",
}  # fmt: skip


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", text)


def code_lines(text: str) -> list[list[str]]:
    lines = []
    for line in strip_comments(text).splitlines():
        tokens = TOKEN.findall(line)
        if tokens:
            lines.append(tokens)
    return lines


def tokens_of(text: str, structure: bool) -> list[str]:
    out = []
    for line in code_lines(text):
        for token in line:
            if structure and re.match(r"[A-Za-z_]", token) and token not in KEYWORDS:
                out.append("ID")
            elif structure and token[0].isdigit():
                out.append("NUM")
            else:
                out.append(token)
    return out


def grams(tokens: list[str], k: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def share(a: set[tuple[str, ...]], b: set[tuple[str, ...]]) -> float:
    return 100.0 * len(a & b) / len(a) if a else 0.0


def longest_shared_run(a: list[str], b: list[str]) -> int:
    """Length (in tokens) of the longest sequence that occurs in both files, verbatim."""
    best = 0
    index: dict[str, list[int]] = {}
    for j, token in enumerate(b):
        index.setdefault(token, []).append(j)
    for i, token in enumerate(a):
        for j in index.get(token, []):
            length = 0
            while i + length < len(a) and j + length < len(b) and a[i + length] == b[j + length]:
                length += 1
            best = max(best, length)
    return best


def compare(text_a: str, text_b: str, ks: tuple[int, ...] = (6, 10)) -> dict[str, object]:
    lines_a = {tuple(line) for line in code_lines(text_a)}
    lines_b = {tuple(line) for line in code_lines(text_b)}
    result: dict[str, object] = {
        "code_lines_a": len(code_lines(text_a)),
        "code_lines_b": len(code_lines(text_b)),
        "identical_code_lines": len(lines_a & lines_b),
        "identical_lines": sorted(" ".join(line) for line in lines_a & lines_b),
        "longest_verbatim_run_tokens": longest_shared_run(
            tokens_of(text_a, False), tokens_of(text_b, False)
        ),
    }
    for structure, name in ((False, "verbatim"), (True, "structure")):
        tokens_a, tokens_b = tokens_of(text_a, structure), tokens_of(text_b, structure)
        result[f"tokens_{name}"] = (len(tokens_a), len(tokens_b))
        for k in ks:
            ga, gb = grams(tokens_a, k), grams(tokens_b, k)
            result[f"{name}_{k}gram_share_of_a_in_b_percent"] = round(share(ga, gb), 1)
            result[f"{name}_{k}gram_share_of_b_in_a_percent"] = round(share(gb, ga), 1)
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument("--k", type=int, action="append")
    args = parser.parse_args(argv)
    ks = tuple(args.k) if args.k else (6, 10)
    result = compare(
        args.a.read_text(encoding="utf-8", errors="replace"),
        args.b.read_text(encoding="utf-8", errors="replace"),
        ks,
    )
    print(f"A = {args.a.name}   B = {args.b.name}")
    for key, value in result.items():
        if key == "identical_lines":
            print("identical code lines:")
            for line in value:  # type: ignore[attr-defined]
                print(f"    {line}")
        else:
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
