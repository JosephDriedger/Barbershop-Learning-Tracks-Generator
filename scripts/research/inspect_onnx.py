"""Describe an ONNX file without any ONNX library: producer, metadata, graph, operators, weights.

Usage: python scripts/research/inspect_onnx.py model.onnx [--json]

ONNX is protocol buffers; this reads only the wire format (varint / length-delimited fields) and the
field numbers of onnx.proto (ModelProto, GraphProto, NodeProto, TensorProto, ValueInfoProto). It exists
so that the provenance of a model can be examined on a PC that has no ONNX tooling, and so that the
result is reproducible from the file alone. It never executes the model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

DATA_TYPES = {
    1: "float32", 2: "uint8", 3: "int8", 4: "uint16", 5: "int16", 6: "int32", 7: "int64",
    8: "string", 9: "bool", 10: "float16", 11: "float64", 12: "uint32", 13: "uint64",
}  # fmt: skip


def varint(buf: bytes, pos: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def fields(buf: bytes) -> list[tuple[int, int, Any]]:
    """Every (field number, wire type, value) of one message; length-delimited values are bytes."""
    out: list[tuple[int, int, Any]] = []
    pos = 0
    while pos < len(buf):
        key, pos = varint(buf, pos)
        number, wire = key >> 3, key & 7
        value: Any
        if wire == 0:
            value, pos = varint(buf, pos)
        elif wire == 2:
            length, pos = varint(buf, pos)
            value = buf[pos : pos + length]
            pos += length
        elif wire == 1:
            value = buf[pos : pos + 8]
            pos += 8
        elif wire == 5:
            value = buf[pos : pos + 4]
            pos += 4
        else:
            raise ValueError(f"unsupported wire type {wire} at {pos}")
        out.append((number, wire, value))
    return out


def text(value: bytes) -> str:
    return value.decode("utf-8", "replace")


def tensor(buf: bytes) -> dict[str, Any]:
    info: dict[str, Any] = {"dims": [], "name": "", "type": "?", "bytes": 0}
    for number, wire, value in fields(buf):
        if number == 1:
            if wire == 0:
                info["dims"].append(value)
            else:  # packed
                pos = 0
                while pos < len(value):
                    item, pos = varint(value, pos)
                    info["dims"].append(item)
        elif number == 2:
            info["type"] = DATA_TYPES.get(value, str(value))
        elif number == 8:
            info["name"] = text(value)
        elif number == 9:
            info["bytes"] += len(value)
    return info


def value_info(buf: bytes) -> dict[str, Any]:
    info: dict[str, Any] = {"name": "", "type": "?", "shape": []}
    for number, _, value in fields(buf):
        if number == 1:
            info["name"] = text(value)
        elif number == 2:  # TypeProto
            for n2, _, v2 in fields(value):
                if n2 != 1:  # tensor_type
                    continue
                for n3, _, v3 in fields(v2):
                    if n3 == 1:
                        info["type"] = DATA_TYPES.get(v3, str(v3))
                    elif n3 == 2:  # TensorShapeProto
                        for n4, _, v4 in fields(v3):
                            if n4 != 1:
                                continue
                            dim: Any = "?"
                            for n5, _, v5 in fields(v4):
                                dim = v5 if n5 == 1 else (text(v5) if n5 == 2 else dim)
                            info["shape"].append(dim)
    return info


def node(buf: bytes) -> dict[str, Any]:
    info: dict[str, Any] = {"op": "", "name": "", "doc": ""}
    for number, _, value in fields(buf):
        if number == 4:
            info["op"] = text(value)
        elif number == 3:
            info["name"] = text(value)
        elif number == 6:
            info["doc"] = text(value)
    return info


def inspect(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    report: dict[str, Any] = {
        "file": path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "ir_version": None,
        "producer_name": "",
        "producer_version": "",
        "domain": "",
        "model_version": None,
        "doc_string": "",
        "opsets": [],
        "metadata_props": {},
        "graph_name": "",
        "graph_doc_string": "",
        "inputs": [],
        "outputs": [],
        "operators": {},
        "node_names_sample": [],
        "initializers": 0,
        "weight_bytes": 0,
        "weight_tensors": [],
    }
    nodes: list[dict[str, Any]] = []
    for number, _, value in fields(data):
        if number == 1:
            report["ir_version"] = value
        elif number == 2:
            report["producer_name"] = text(value)
        elif number == 3:
            report["producer_version"] = text(value)
        elif number == 4:
            report["domain"] = text(value)
        elif number == 5:
            report["model_version"] = value
        elif number == 6:
            report["doc_string"] = text(value)
        elif number == 8:
            domain, version = "", None
            for n2, _, v2 in fields(value):
                if n2 == 1:
                    domain = text(v2)
                elif n2 == 2:
                    version = v2
            report["opsets"].append({"domain": domain or "ai.onnx", "version": version})
        elif number == 14:
            key = val = ""
            for n2, _, v2 in fields(value):
                if n2 == 1:
                    key = text(v2)
                elif n2 == 2:
                    val = text(v2)
            report["metadata_props"][key] = val
        elif number == 7:
            for n2, _, v2 in fields(value):
                if n2 == 1:
                    nodes.append(node(v2))
                elif n2 == 2:
                    report["graph_name"] = text(v2)
                elif n2 == 10:
                    report["graph_doc_string"] = text(v2)
                elif n2 == 5:
                    t = tensor(v2)
                    report["initializers"] += 1
                    report["weight_bytes"] += t["bytes"]
                    report["weight_tensors"].append(t)
                elif n2 == 11:
                    report["inputs"].append(value_info(v2))
                elif n2 == 12:
                    report["outputs"].append(value_info(v2))
    report["operators"] = dict(sorted(Counter(n["op"] for n in nodes).items()))
    report["node_count"] = len(nodes)
    report["node_names_sample"] = [n["name"] for n in nodes[:12]]
    report["weight_tensors"].sort(key=lambda t: -t["bytes"])
    return report


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = inspect(args.model)
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    for key in (
        "file", "bytes", "sha256", "ir_version", "producer_name", "producer_version", "domain",
        "model_version", "doc_string", "opsets", "metadata_props", "graph_name", "graph_doc_string",
        "inputs", "outputs", "node_count", "operators", "initializers", "weight_bytes",
    ):  # fmt: skip
        print(f"{key}: {report[key]}")
    print("node names (first 12):", report["node_names_sample"])
    print("largest weights:")
    for t in report["weight_tensors"][:12]:
        print(f"  {t['name']}: {t['type']} {t['dims']} ({t['bytes']} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
