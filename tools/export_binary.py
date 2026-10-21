"""归档实际分发目录，并复核 ZIP 成员、CRC 与文件 SHA。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def export(args):
    bundle, destination = args.bundle.resolve(), args.out.resolve()
    if destination.exists():
        raise FileExistsError(str(destination))
    files = {}
    for path in sorted(bundle.rglob("*")):
        if path.is_symlink():
            files[path.relative_to(bundle).as_posix()] = {"symlink": path.readlink().as_posix()}
        elif path.is_file():
            files[path.relative_to(bundle).as_posix()] = {
                "bytes": path.stat().st_size,
                "sha256": digest(path.read_bytes()),
            }
    manifest = {
        "schema_version": 1,
        "version": "0.1.0.dev1",
        "platform": args.platform,
        "files": files,
        "native_windows_execution": "NOT_RUN",
        "scientific_acceptance": "NOT_ASSESSED",
    }
    manifest_path = bundle / "PACKAGE_MANIFEST.json"
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    files[manifest_path.name] = {"sha256": digest(manifest_path.read_bytes())}
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = "BLR_MEM_Windows" if args.platform == "windows" else bundle.name
    if args.platform == "macos":
        subprocess.run(
            ["/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(bundle), str(destination)],
            check=True,
            timeout=180,
        )
    else:
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in files:
                archive.write(bundle / name, prefix + "/" + name)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        for name, record in files.items():
            data = archive.read(prefix + "/" + name)
            if "sha256" in record:
                assert digest(data) == record["sha256"], name
            elif "symlink" in record:
                assert data.decode() == record["symlink"], name
    receipt = {
        "archive": destination.name,
        "bytes": destination.stat().st_size,
        "sha256": digest(destination.read_bytes()),
        "files_and_symlinks": len(files),
        "crc": "PASS",
        "member_hashes": "PASS",
        "platform": args.platform,
        "native_windows_execution": "NOT_RUN",
        "scientific_acceptance": "NOT_ASSESSED",
    }
    with destination.with_suffix(".validation.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "macos"), required=True)
    export(parser.parse_args())
