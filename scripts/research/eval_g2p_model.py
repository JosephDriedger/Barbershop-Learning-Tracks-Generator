"""Measure how a g2p pack's neural model relates to its dictionary (evidence about what it was trained on).

Usage: python scripts/research/eval_g2p_model.py g2p-arpabet.zip [--sample 20000] [--seed 1] [--cmudict FILE]

Needs ``onnxruntime`` (a research tool; BLT itself does not use it). It reproduces OpenUtau's
``ArpabetG2p`` / ``G2pPack.Predict`` greedy decoding exactly (same symbol tables, same loop), runs it on
the dictionary words of the pack, and compares the prediction with the dictionary's pronunciation(s):

* word error rate (no listed pronunciation matches) and phoneme error rate (edit distance to the closest
  listed pronunciation / its length), exactly the measures the OpenUtau g2p trainer reports;
* with ``--cmudict``: the same for words that are NOT in that dictionary file (a dictionary the model
  never saw would make no difference to a model trained on something else).

A model trained on a dictionary reproduces it clearly better than a model trained on another source
would; this is circumstantial evidence about training data, not proof. It says nothing about licences.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import onnxruntime as ort

GRAPHEMES = ["", "", "", "", "'", "-", *"abcdefghijklmnopqrstuvwxyz"]
PHONEMES = [
    "", "", "", "", "aa", "ae", "ah", "ao", "aw", "ay", "b", "ch", "d", "dh", "eh", "er", "ey", "f",
    "g", "hh", "ih", "iy", "jh", "k", "l", "m", "n", "ng", "ow", "oy", "p", "r", "s", "sh", "t", "th",
    "uh", "uw", "v", "w", "y", "z", "zh",
]  # fmt: skip
TAIL_DIGITS = re.compile(r"\d+$")


def edit_distance(a: list[str], b: list[str]) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def load_entries(text: str, lowercase: bool = True) -> dict[str, list[list[str]]]:
    entries: dict[str, list[list[str]]] = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith(";;;"):
            continue
        parts = line.strip().split("  ")
        if len(parts) != 2:
            continue
        word = parts[0].lower() if lowercase else parts[0]
        word = re.sub(r"\(\d+\)$", "", word)
        pron = [TAIL_DIGITS.sub("", p.lower()) for p in parts[1].split()]
        entries.setdefault(word, []).append(pron)
    return entries


class Model:
    def __init__(self, data: bytes) -> None:
        self.session = ort.InferenceSession(data, providers=["CPUExecutionProvider"])
        self.index = {g: i for i, g in enumerate(GRAPHEMES) if g}

    def predict(self, word: str) -> list[str]:
        ids = [self.index[c] for c in word.lower() if c in self.index]
        if not ids:
            return []
        src = np.array([ids], dtype=np.int32)
        tgt = [2]
        t = 0
        while t < len(ids) and len(tgt) < 48:
            out = self.session.run(
                None,
                {
                    "src": src,
                    "tgt": np.array([tgt], dtype=np.int32),
                    "t": np.array([t], dtype=np.int32),
                },
            )
            pred = int(out[0].reshape(-1)[0])
            if pred != 2:
                tgt.append(pred)
            else:
                t += 1
        return [PHONEMES[i] for i in tgt[1:]]


def measure(
    model: Model, words: list[str], entries: dict[str, list[list[str]]]
) -> dict[str, float]:
    wrong_words = 0
    errors = 0
    length = 0
    for word in words:
        prediction = model.predict(word)
        references = entries[word]
        best = min(references, key=lambda ref: edit_distance(prediction, ref))
        distance = edit_distance(prediction, best)
        errors += distance
        length += len(best)
        wrong_words += prediction not in references
    return {
        "words": len(words),
        "wer_percent": 100.0 * wrong_words / len(words),
        "per_percent": 100.0 * errors / length,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--sample", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--cmudict", type=Path)
    args = parser.parse_args(argv)
    with zipfile.ZipFile(args.pack) as archive:
        entries = load_entries(archive.read("dict.txt").decode("utf-8", "replace"))
        model = Model(archive.read("g2p.onnx"))
    rng = random.Random(args.seed)
    words = sorted(w for w in entries if 1 <= len(w) <= 40 and all(c in model.index for c in w))
    print(f"{args.pack.name}: {len(entries)} dictionary words, {len(words)} usable")
    groups = {"all dictionary words": words}
    if args.cmudict:
        other = load_entries(args.cmudict.read_text(encoding="latin-1"))
        groups["words also in --cmudict"] = [w for w in words if w in other]
        groups["words NOT in --cmudict"] = [w for w in words if w not in other]
    for name, group in groups.items():
        if not group:
            print(f"{name}: none")
            continue
        sample = rng.sample(group, min(args.sample, len(group)))
        result = measure(model, sample, entries)
        print(
            f"{name}: {len(group)} words, sample {result['words']}: "
            f"WER {result['wer_percent']:.2f} %, PER {result['per_percent']:.2f} %"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
