"""只读检查参考 EXE；不启动 EXE，不导入或执行其内嵌模块。

此工具为可选开发审查工具，不是工作台运行依赖。使用与参考程序相同
小版本的 CPython 和 PyInstaller 的 archive reader。反汇编只能写入
显式指定的本地目录，公开源码包不包含参考程序或反汇编内容。
"""

from __future__ import annotations

import argparse
import dis
import hashlib
import importlib.util
import json
import marshal
import platform
import struct
import sys
import types
from pathlib import Path

COOKIE_MAGIC = b"MEI\014\013\012\013\016"
COOKIE_FORMAT = "!8sIIII64s"
REVIEW_MODULES = {"generator": ("simulation_core",), "solver": ("MEMECHO_GUI",)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def literal(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, frozenset)):
        return {"type": type(value).__name__, "items": [literal(item) for item in value]}
    if isinstance(value, bytes):
        return {"type": "bytes", "bytes": len(value), "sha256": digest(value)}
    if isinstance(value, complex):
        return {"type": "complex", "real": value.real, "imag": value.imag}
    return {"type": type(value).__name__}


def outline(code):
    return {
        "name": code.co_name,
        "qualname": code.co_qualname,
        "source_file": code.co_filename,
        "source_first_line": code.co_firstlineno,
        "names": list(code.co_names),
        "arguments_and_locals": list(code.co_varnames),
        "imports": [
            {"offset": item.offset, "module": item.argval}
            for item in dis.get_instructions(code)
            if item.opname == "IMPORT_NAME"
        ],
        "literal_constants": [
            literal(item) for item in code.co_consts if not isinstance(item, types.CodeType)
        ],
        "children": [outline(item) for item in code.co_consts if isinstance(item, types.CodeType)],
    }


def visible_defaults(code, label):
    """仅识别这两个样本中的字面量模式；不执行构造器或任意表达式。"""
    if label == "generator" and code.co_name == "<module>":
        items = list(dis.get_instructions(code))
        for index, item in enumerate(items):
            if item.opname == "STORE_NAME" and item.argval == "DEFAULTS":
                previous = max(i for i in range(index) if items[i].opname == "STORE_NAME")
                pairs = []
                for i in range(previous + 3, index):
                    if items[i].opname == "MAP_ADD" and all(
                        x.opname == "LOAD_CONST" for x in items[i - 2 : i]
                    ):
                        key, value = (x.argval for x in items[i - 2 : i])
                        if not isinstance(key, str) or not isinstance(value, (str, int, float, bool)):
                            raise ValueError("DEFAULTS 含有未支持的字面量")
                        pairs.append((key, value))
                return {"generator_gui_defaults": dict(pairs), "method": "literal_constants_only"}
    if label == "solver" and code.co_name == "<module>":
        gui = next(
            (x for x in code.co_consts if isinstance(x, types.CodeType) and x.co_name == "MemechoGUI"), None
        )
        if gui is None:
            return {}
        init = next(x for x in gui.co_consts if isinstance(x, types.CodeType) and x.co_name == "__init__")
        items = list(dis.get_instructions(init))
        groups = {}
        for index, item in enumerate(items):
            if item.opname != "STORE_ATTR" or item.argval not in ("basic", "advanced"):
                continue
            if items[index - 2].opname != "BUILD_CONST_KEY_MAP" or items[index - 3].opname != "LOAD_CONST":
                raise ValueError("GUI 默认值模式改变，请人工审查")
            keys = items[index - 3].argval
            values = [
                items[i - 1].argval
                for i in range(1, index - 3)
                if items[i].opname == "LOAD_CONST"
                and items[i].argval == ("value",)
                and items[i - 1].opname == "LOAD_CONST"
            ]
            if len(values) < len(keys):
                raise ValueError("GUI 默认值数量不一致")
            groups[item.argval] = dict(zip(keys, values[-len(keys) :], strict=True))
        return {"solver_gui_defaults": groups, "method": "literal_Tk_values_only_not_solver_defaults"}
    return {}


def pe_metadata(data):
    if data[:2] != b"MZ":
        raise ValueError("输入没有 DOS/PE 文件头")
    offset = struct.unpack_from("<I", data, 60)[0]
    if data[offset : offset + 4] != b"PE\0\0":
        raise ValueError("输入没有 PE 签名")
    machine, section_count, timestamp = struct.unpack_from("<HHI", data, offset + 4)
    optional = offset + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic not in (0x10B, 0x20B):
        raise ValueError("不支持的 PE 可选头")
    directory = optional + (112 if magic == 0x20B else 96)
    certificate_offset, certificate_bytes = struct.unpack_from("<II", data, directory + 4 * 8)
    return {
        "format": "PE32+" if magic == 0x20B else "PE32",
        "machine": hex(machine),
        "architecture": "x86_64" if machine == 0x8664 else "OTHER",
        "subsystem": struct.unpack_from("<H", data, optional + 68)[0],
        "section_count": section_count,
        "header_timestamp_raw": timestamp,
        "certificate_table_offset": certificate_offset,
        "certificate_table_bytes": certificate_bytes,
        "authenticode_present": certificate_bytes > 0,
        "authenticode_verification": "NOT_PERFORMED",
    }


def audit(path, label, reader_class, disassembly_dir):
    data = path.read_bytes()
    before = digest(data)
    cookie_at = data.rfind(COOKIE_MAGIC)
    cookie_size = struct.calcsize(COOKIE_FORMAT)
    if cookie_at < 0 or cookie_at + cookie_size > len(data):
        raise ValueError("没有完整的 PyInstaller CArchive cookie")
    _, length, toc_at, toc_size, pyversion, library = struct.unpack_from(COOKIE_FORMAT, data, cookie_at)
    if pyversion != sys.version_info.major * 100 + sys.version_info.minor:
        raise ValueError(f"参考程序 Python={pyversion}，请使用相同小版本解释器读取代码对象")
    start = cookie_at + cookie_size - length
    if not (0 <= start < cookie_at and start + toc_at + toc_size == cookie_at):
        raise ValueError("CArchive 长度或目录范围不一致")
    archive = reader_class(str(path))
    pyz_entries = [name for name, entry in archive.toc.items() if entry[-1] == "z"]
    if len(pyz_entries) != 1:
        raise ValueError("需要恰好一个 PYZ 归档")
    pyz_name = pyz_entries[0]
    pyz_at, pyz_length, _, compressed, _ = archive.toc[pyz_name]
    if compressed or pyz_length < 12:
        raise ValueError("需要未额外压缩的标准 PYZ 归档")
    header = data[start + pyz_at : start + pyz_at + 12]
    if header[:4] != b"PYZ\0" or header[4:8] != importlib.util.MAGIC_NUMBER:
        raise ValueError("PYZ 字节码 magic 与当前解释器不同，停止解析")
    pyz = archive.open_embedded_archive(pyz_name)
    modules = {}
    sources = [
        (name, archive.extract(name))
        for name, entry in archive.toc.items()
        if entry[-1] == "s" and not name.startswith(("pyi_", "pyiboot"))
    ]
    sources.extend((name, pyz.extract(name, raw=True)) for name in REVIEW_MODULES[label])
    for name, raw in sources:
        code = marshal.loads(raw)
        if not isinstance(code, types.CodeType):
            raise ValueError(f"{name} 不包含代码对象")  # noqa: TRY004
        modules[name] = {
            "marshal_sha256": digest(raw),
            "marshal_bytes": len(raw),
            "outline": outline(code),
            **visible_defaults(code, label),
        }
        if disassembly_dir is not None:
            if not name.replace("_", "").isalnum():
                raise ValueError("模块名不能用作审查文件名")
            target = disassembly_dir / f"{label}_{name}.dis.txt"
            with target.open("x", encoding="utf-8") as stream:
                stream.write("STATIC DISASSEMBLY ONLY; embedded modules were not executed.\n")
                dis.dis(code, file=stream, show_caches=False, adaptive=False)
    options = list(archive.options)
    contents = [option.split(" ", 1)[1] for option in options if option.startswith("pyi-contents-directory ")]
    expected = [path.parent / name for name in contents]
    solver_candidates = []
    if label == "solver":
        solver_candidates = [path.parent / "023_0821.py"] + [
            directory / "023_0821.py" for directory in expected
        ]
    if digest(path.read_bytes()) != before:
        raise ValueError("审查期间输入文件内容改变")
    return {
        "input_name": path.name,
        "input_bytes": len(data),
        "input_sha256_before": before,
        "input_sha256_after": before,
        "pe": pe_metadata(data),
        "packaging": {
            "python_version_code": pyversion,
            "python_library": library.rstrip(b"\0").decode("ascii"),
            "python_magic": header[4:8].hex(),
            "python_magic_matches_host": True,
            "options": options,
            "contents_directories": [
                {"name": item.name, "exists_beside_exe": item.is_dir()} for item in expected
            ],
            "solver_script_candidates": [
                {"relative_path": item.relative_to(path.parent).as_posix(), "exists": item.is_file()}
                for item in solver_candidates
            ],
            "carchive": [
                {"name": name, "type": entry[-1], "stored_bytes": entry[1], "uncompressed_bytes": entry[2]}
                for name, entry in archive.toc.items()
            ],
            "pyz_module_count": len(pyz.toc),
            "pyz_modules": list(pyz.toc),
            "solver_script_in_embedded_archives": "023_0821.py" in archive.toc or "023_0821" in pyz.toc,
        },
        "reviewed_modules": modules,
        "analysis_only": True,
        "exe_executed": False,
        "embedded_module_imported_or_executed": False,
        "reference_bytecode_saved_in_package": False,
    }


def write_json(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="新的本地审查目录")
    parser.add_argument("--reader-dir", type=Path, help="可选：隔离安装 PyInstaller 的目录")
    parser.add_argument("--disassembly-dir", type=Path, help="可选：新的私有反汇编目录，勿加入公开交付包")
    args = parser.parse_args()
    if args.reader_dir:
        sys.path.insert(0, str(args.reader_dir.resolve()))
    from PyInstaller import __version__ as reader_version
    from PyInstaller.archive.readers import CArchiveReader

    if args.disassembly_dir:
        args.disassembly_dir.mkdir(parents=True, exist_ok=False)
    reports = {
        label: audit(path.resolve(), label, CArchiveReader, args.disassembly_dir)
        for label, path in (("generator", args.generator), ("solver", args.solver))
    }
    args.out.mkdir(parents=True, exist_ok=False)
    for label, report in reports.items():
        write_json(args.out / f"{label}.json", report)
    receipt = {
        "schema_version": 1,
        "mode": "static_only",
        "python": platform.python_version(),
        "pyinstaller_reader": reader_version,
        "script_sha256": digest(Path(__file__).read_bytes()),
        "inputs": {
            label: {"name": item["input_name"], "sha256": item["input_sha256_before"], "unchanged": True}
            for label, item in reports.items()
        },
        "outputs": {path.name: digest(path.read_bytes()) for path in sorted(args.out.glob("*.json"))},
        "native_windows_execution": "NOT_RUN",
        "solver_algorithm_audit": "NOT_AUDITED_EXTERNAL_SOLVER_NOT_EXECUTED",
        "official_author_and_license": "UNVERIFIED",
    }
    write_json(args.out / "receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
