"""显式白名单归档；CRC/成员/SHA 独立校验；不上传任何文件。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--with-evidence", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    patterns = [
        "README.md",
        "NOTICE.md",
        "CITATION.cff",
        "pyproject.toml",
        "MANIFEST.in",
        "provenance.json",
        ".gitignore",
        "*.spec",
        "requirements-tested-*.txt",
        "requirements-runtime.txt",
        "1D/*.json",
        "1D/*.cmd",
        "1D/*.command",
        "2D/*.json",
        "2D/*.cmd",
        "2D/*.command",
        "src/**/*.py",
        "tests/*.py",
        "tools/*.py",
        "tools/*.c",
        "docs/*.md",
        "docs/*.png",
        "docs/*.csv",
        "docs/*.json",
        ".github/workflows/*.yml",
    ]
    files = {path for pattern in patterns for path in root.glob(pattern) if path.is_file()}
    if args.with_evidence:
        files.update(
            path
            for path in (root / "evidence").rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix in (".json", ".xml", ".csv", ".npz", ".png", ".html", ".txt")
        )
    forbidden = re.compile(
        rb"(?m)^-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----|\bAKIA[A-Z0-9]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b"
    )
    entries = {}
    for path in sorted(files):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or any(
            part in (".ssh", ".aws", ".env", ".venv", "__pycache__") for part in path.relative_to(root).parts
        ):
            raise ValueError(f"不允许的源文件: {relative}")
        data = path.read_bytes()
        if forbidden.search(data):
            raise ValueError(f"检测到疑似凭据，停止归档: {relative}")
        entries[relative] = {"bytes": len(data), "sha256": digest(data)}
    provenance = json.loads((root / "provenance.json").read_text())
    for item in provenance["files"]:
        assert digest((root / item["target"]).read_bytes()) == item["packaged_sha256"], item["target"]
    manifest = {
        "schema_version": 1,
        "kind": "review_preview_not_public_release",
        "files": entries,
        "license": "PENDING_AUTHOR_CONFIRMATION",
        "windows_binary_validation": "NOT_RUN",
        "includes_local_evidence": args.with_evidence,
        "credential_pattern_scan": "PASS_FOR_KNOWN_PATTERNS_ONLY",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in entries:
            archive.write(root / name, name)
        archive.writestr("PACKAGE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    with zipfile.ZipFile(args.out) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(entries) | {"PACKAGE_MANIFEST.json"}
        for name, item in entries.items():
            assert digest(archive.read(name)) == item["sha256"], name
    receipt = {
        "archive": args.out.name,
        "sha256": digest(args.out.read_bytes()),
        "members": len(entries) + 1,
        "bytes": args.out.stat().st_size,
        "crc": "PASS",
        "member_set": "PASS",
        "sha256_validation": "PASS",
        "license": manifest["license"],
        "windows_binary_validation": "NOT_RUN",
    }
    with args.out.with_suffix(".validation.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
