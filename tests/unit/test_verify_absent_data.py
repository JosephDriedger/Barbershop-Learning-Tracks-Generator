"""packaging/verify_absent_data.py finds removed data wherever it is, and refuses a vacuous pass."""

import os
import sys
from pathlib import Path

import pytest

PACKAGING = Path(__file__).resolve().parents[2] / "packaging"
sys.path.insert(0, str(PACKAGING))

import verify_absent_data as vad  # noqa: E402


def _checkout(root: Path) -> dict[str, bytes]:
    """A fake pinned checkout with every file the script fingerprints; returns name -> content."""
    contents: dict[str, bytes] = {}
    for index, name in enumerate(vad.REMOVED):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = os.urandom(4096) + bytes([index])
        path.write_bytes(data)
        contents[name] = data
    vogen = root / "OpenUtau.Core" / "Vogen" / "Data"
    vogen.mkdir(parents=True)
    (vogen / "model.onnx").write_bytes(os.urandom(2048))
    (vogen / "yue.csv").write_bytes(b"")
    return contents


def test_a_clean_folder_passes(tmp_path: Path) -> None:
    _checkout(tmp_path / "src")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "app.dll").write_bytes(os.urandom(10000))
    assert vad.scan(package, tmp_path / "src") == []


@pytest.mark.parametrize("where", ["host/OpenUtau.Core.dll", "renamed/innocent.bin", "a/b/c/d.dat"])
def test_removed_data_is_found_embedded_in_any_file_with_any_name(
    tmp_path: Path, where: str
) -> None:
    contents = _checkout(tmp_path / "src")
    package = tmp_path / "pkg"
    target = package / where
    target.parent.mkdir(parents=True)
    plus = contents["OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip"]
    target.write_bytes(os.urandom(3000) + plus + os.urandom(3000))
    hits = vad.scan(package, tmp_path / "src")
    assert hits == [f"{where} contains data of OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip"]


def test_the_english_cv_template_is_found_too(tmp_path: Path) -> None:
    contents = _checkout(tmp_path / "src")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "OpenUtau.Plugin.Builtin.dll").write_bytes(
        contents["OpenUtau.Plugin.Builtin/Data/en_cPv.template.yaml"]
    )
    assert any("en_cPv.template.yaml" in hit for hit in vad.scan(package, tmp_path / "src"))


def test_a_checkout_without_the_removed_files_is_an_error_not_a_pass(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (tmp_path / "empty-src").mkdir()
    with pytest.raises(SystemExit):
        vad.scan(package, tmp_path / "empty-src")


def _english_pack(root: Path) -> bytes:
    """The pinned English pack (dict.txt, phones.txt and a g2p.onnx); returns the model's bytes."""
    import zipfile

    model = os.urandom(4096)
    pack = root / vad.ENGLISH_PACK
    pack.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dict.txt", "hello  hh ah l ow\n" * 400)
        archive.writestr("phones.txt", "aa\tvowel\n")
        archive.writestr(vad.MODEL_MEMBER, model)
    return model


def test_the_g2p_model_is_only_looked_for_when_the_build_is_meant_to_lack_it(
    tmp_path: Path,
) -> None:
    _checkout(tmp_path / "src")
    model = _english_pack(tmp_path / "src")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "loose.bin").write_bytes(os.urandom(500) + model + os.urandom(500))
    assert vad.scan(package, tmp_path / "src") == []  # the default build ships the model
    hits = vad.scan(package, tmp_path / "src", without_g2p_model=True)
    assert hits == ["loose.bin contains data of OpenUtau.Core/G2p/Data/g2p-arpabet.zip/g2p.onnx"]


def test_a_package_without_the_g2p_model_passes_the_stricter_scan(tmp_path: Path) -> None:
    _checkout(tmp_path / "src")
    _english_pack(tmp_path / "src")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "app.dll").write_bytes(os.urandom(10000))
    assert vad.scan(package, tmp_path / "src", without_g2p_model=True) == []
