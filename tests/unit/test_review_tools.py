"""The tools that feed the independent review: the packets, the ONNX reader, the text comparison."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "research"))

import compare_source_text as cst  # noqa: E402
import inspect_onnx as onnx  # noqa: E402

# --- inspect_onnx: a hand-made ONNX file (protocol buffers: tag = number << 3 | wire type) ---


def varint(number: int) -> bytes:
    out = bytearray()
    while True:
        byte = number & 0x7F
        number >>= 7
        out.append(byte | (0x80 if number else 0))
        if not number:
            return bytes(out)


def field(number: int, payload: bytes | int) -> bytes:
    if isinstance(payload, int):
        return varint(number << 3) + varint(payload)
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def tiny_model() -> bytes:
    node = field(4, b"LSTM") + field(3, b"lstm_0")
    node2 = field(4, b"MatMul")
    weights = field(1, 2) + field(1, 3) + field(2, 1) + field(8, b"w") + field(9, bytes(24))
    graph = (
        field(1, node)
        + field(1, node2)
        + field(2, b"torch-jit-export")
        + field(5, weights)
        + field(11, field(1, b"src"))
        + field(12, field(1, b"pred"))
    )
    return (
        field(1, 7)
        + field(2, b"pytorch")
        + field(3, b"1.10")
        + field(7, graph)
        + field(8, field(2, 11))
        + field(14, field(1, b"author") + field(2, b"nobody"))
    )


def test_the_onnx_reader_reports_producer_graph_operators_and_weights(tmp_path: Path) -> None:
    path = tmp_path / "m.onnx"
    path.write_bytes(tiny_model())
    report = onnx.inspect(path)
    assert report["producer_name"] == "pytorch"
    assert report["producer_version"] == "1.10"
    assert report["ir_version"] == 7
    assert report["graph_name"] == "torch-jit-export"
    assert report["operators"] == {"LSTM": 1, "MatMul": 1}
    assert report["opsets"] == [{"domain": "ai.onnx", "version": 11}]
    assert report["metadata_props"] == {"author": "nobody"}
    assert report["weight_tensors"][0]["dims"] == [2, 3]
    assert report["weight_bytes"] == 24
    assert report["sha256"] == hashlib.sha256(tiny_model()).hexdigest()
    assert [i["name"] for i in report["inputs"]] == ["src"]
    assert [o["name"] for o in report["outputs"]] == ["pred"]


def test_the_real_model_in_the_pinned_source_is_what_the_provenance_page_says(
    tmp_path: Path,
) -> None:
    pack = REPO / "research-output" / "openutau-src" / "OpenUtau.Core/G2p/Data/g2p-arpabet.zip"
    if not pack.is_file():
        pytest.skip("the pinned OpenUtau checkout is not here")
    import zipfile

    with zipfile.ZipFile(pack) as archive:
        data = archive.read("g2p.onnx")
    path = tmp_path / "g2p-test.onnx"
    path.write_bytes(data)
    report = onnx.inspect(path)
    assert report["sha256"] == "10779eca9db25cab467f2a6271519c3f0c96f562845c393043fa5fa85ae06059"
    assert report["producer_name"] == "pytorch"
    assert report["producer_version"] == "1.10"
    assert report["operators"]["LSTM"] == 4
    assert (
        report["weight_bytes"] // 4 == 440715
    )  # float32 parameters, as docs/g2p-model-provenance.md says


# --- compare_source_text ---


SPLINE_LIKE = """
// a comment that is ignored
class Curve {
 public:
  Curve(const std::vector<double>& x, const std::vector<double>& y) : x_(x), y_(y) {}
  double at(double v) const {
    double total = 0.0;
    for (size_t i = 0; i < x_.size(); ++i) { total += y_[i] * (v - x_[i]); }
    return total;
  }
};
"""


def test_identical_text_shares_everything_and_comments_do_not_count() -> None:
    result = cst.compare(SPLINE_LIKE, SPLINE_LIKE + "// another comment\n", ks=(5,))
    assert result["verbatim_5gram_share_of_a_in_b_percent"] == 100.0
    assert result["identical_code_lines"] == result["code_lines_a"]


def test_renamed_identifiers_share_structure_but_not_text() -> None:
    renamed = SPLINE_LIKE.replace("Curve", "Line").replace("total", "sum").replace("at", "value")
    renamed = renamed.replace("x_", "xs_").replace("y_", "ys_").replace("v", "w")
    result = cst.compare(SPLINE_LIKE, renamed, ks=(5,))
    assert float(str(result["structure_5gram_share_of_a_in_b_percent"])) > 90.0
    assert float(str(result["verbatim_5gram_share_of_a_in_b_percent"])) < 60.0


def test_unrelated_code_shares_little() -> None:
    other = "int main() { std::string s = read(); print(s.size()); return s.empty() ? 1 : 0; }"
    result = cst.compare(SPLINE_LIKE, other, ks=(8,))
    assert float(str(result["verbatim_8gram_share_of_a_in_b_percent"])) == 0.0
    assert int(str(result["longest_verbatim_run_tokens"])) < 8


# --- the review packets ---


def test_every_packet_has_a_readme_a_manifest_and_a_reproducible_zip(tmp_path: Path) -> None:
    hashes = []
    for name in ("one", "two"):
        out = tmp_path / name
        done = subprocess.run(
            [sys.executable, str(REPO / "packaging" / "review_packets.py"), "--out", str(out)],
            capture_output=True,
            text=True,
            cwd=REPO,
            check=False,
            timeout=300,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        hashes.append(
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob("*.zip")}
        )
    expected = {
        "checklist",
        "qt",
        "source-history",
        "g2p-model",
        "ai-authorship",
        "native-dependencies",
        "worldline",
    }
    folders = {p.name for p in (tmp_path / "one").iterdir() if p.is_dir()}
    assert folders == expected
    for name in expected:
        folder = tmp_path / "one" / name
        assert (folder / "README.md").is_file(), name
        manifest = json.loads((folder / "MANIFEST.json").read_text(encoding="utf-8"))
        assert manifest["packet"] == name
        for relative, digest in manifest["files"].items():
            assert hashlib.sha256((folder / relative).read_bytes()).hexdigest() == digest
    assert hashes[0].keys() == {f"{n}-review-packet.zip" for n in expected}
    # the zips are byte-for-byte reproducible (sorted members, fixed timestamps)
    same = {n for n in hashes[0] if hashes[0][n] == hashes[1][n]}
    assert {"checklist-review-packet.zip", "native-dependencies-review-packet.zip"} <= same


def test_the_history_packet_carries_the_replacement_spline_as_it_was() -> None:
    done = subprocess.run(
        ["git", "show", "b4b99bb:host/native/patched/natural_spline.h"],
        capture_output=True,
        cwd=REPO,
        check=False,
    )
    if done.returncode != 0:
        pytest.skip("the full git history is not available (a shallow clone)")
    assert hashlib.sha256(done.stdout).hexdigest().startswith("bc9ebdc7af55493c")
