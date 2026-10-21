# -*- mode: python ; coding: utf-8 -*-
# GUI and CLI share a single onedir runtime.
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH)
metadata = [(str(root / "build/build_identity.json"), ".")]
for distribution in ["numpy", "scipy", "pandas", "matplotlib"]:
    metadata += copy_metadata(distribution)
a = Analysis([str(root / "tools/frozen_entry.py")], pathex=[str(root / "src")],
             binaries=[], datas=metadata, hiddenimports=["tkinter", "matplotlib.backends.backend_agg"],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=["IPython", "jupyter", "notebook", "pytest", "sphinx", "torch", "tensorflow",
                       "sklearn", "numba", "llvmlite", "cv2", "PyQt5", "PyQt6", "PySide2", "PySide6"])
pyz = PYZ(a.pure)
executables = []
for name in ["BLRWorkbench", "blr-rm"]:
    executables.append(EXE(pyz, a.scripts, [], exclude_binaries=True, name=name,
                           debug=False, bootloader_ignore_signals=False, strip=False,
                           upx=False, console=(name == "blr-rm")))
coll = COLLECT(*executables, a.binaries, a.datas, strip=False, upx=False, name="BLR-RM")
