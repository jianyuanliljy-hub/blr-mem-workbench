"""不覆盖输出；观测和真值分文件；记录哈希及运行环境。"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import __version__


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def save_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(canonical(value))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def array_identity(arrays: dict) -> str:
    digest = hashlib.sha256()
    for key in sorted(arrays):
        value = np.ascontiguousarray(arrays[key])
        digest.update(key.encode())
        digest.update(str(value.dtype).encode())
        digest.update(str(value.shape).encode())
        digest.update(value.tobytes())
    return digest.hexdigest()


def load_arrays(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    if any(value.dtype.kind not in "biuf" for value in arrays.values()):
        raise ValueError("数组文件只接受数值和布尔类型")
    return arrays


def save_arrays(path: Path, arrays: dict) -> None:
    with path.open("xb") as stream:
        np.savez_compressed(stream, **arrays)


def environment() -> dict:
    versions = {}
    for name in ("numpy", "scipy", "pandas", "matplotlib"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "unknown"
    source = Path(__file__).parent
    source_hashes = {str(p.relative_to(source)): sha256(p) for p in sorted(source.rglob("*.py"))}
    binary_hash = None
    if getattr(sys, "frozen", False):
        identity = Path(sys._MEIPASS) / "build_identity.json"
        if identity.exists():
            source_hashes = read_json(identity)["source_sha256"]
        binary_hash = sha256(sys.executable)
    return {
        "utc": datetime.now(UTC).isoformat(),
        "version": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "dependencies": versions,
        "source_sha256": source_hashes,
        "executable_sha256": binary_hash,
    }


def seal(directory: Path, manifest: str, metadata: dict) -> None:
    files = {p.name: sha256(p) for p in sorted(directory.iterdir()) if p.is_file() and p.name != manifest}
    save_json(directory / manifest, {**metadata, "files": files})


def verify(directory: Path, manifest: str, names: tuple[str, ...] | None = None) -> dict:
    metadata = read_json(directory / manifest)
    if metadata.get("schema_version") != 1:
        raise ValueError("不支持的 schema_version")
    if names is not None and set(names) - set(metadata["files"]):
        raise ValueError("清单缺少所需输入文件")
    for name, expected in metadata["files"].items():
        if names is not None and name not in names:
            continue
        if Path(name).name != name or name in (".", "..") or (directory / name).is_symlink():
            raise ValueError("清单包含不安全的文件路径")
        if sha256(directory / name) != expected:
            raise ValueError(f"文件哈希不匹配: {name}")
    return metadata
