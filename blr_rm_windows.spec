# -*- mode: python ; coding: utf-8 -*-
# GUI and CLI share a single onedir runtime.
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_all

root = Path(SPECPATH)
metadata = [(str(root / "build/build_identity.json"), ".")]
metadata += [(str(root / 'src/blr_rm/autumn/023_0821.py'), 'autumn')]
for distribution in ["numpy", "scipy", "pandas", "matplotlib"]:
    metadata += copy_metadata(distribution)
binaries = []
hiddenimports = ['tkinter', 'matplotlib.backends.backend_agg', 'scipy.optimize', 'scipy.sparse', 'scipy.linalg']
for package in ('jax', 'jaxlib', 'numba', 'llvmlite'):
    result = collect_all(package, filter_submodules=lambda n: not any(
        s in n for s in ('test', 'pallas', 'mosaic', 'triton', 'source_mapper',
                        'array_serialization', 'colocated_python', '.cuda', 'gpu_')))
    metadata += result[0]
    binaries += result[1]
    hiddenimports += result[2]
a = Analysis([str(root / "tools/frozen_entry.py")], pathex=[str(root / "src")],
             binaries=binaries, datas=metadata, hiddenimports=hiddenimports,
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=["IPython", "jupyter", "notebook", "pytest", "sphinx", "torch", "tensorflow",
                       "sklearn", "cv2", "PyQt5", "PyQt6", "PySide2", "PySide6"])
pyz = PYZ(a.pure)
executables = []
for name in ["BLRWorkbench", "blr-rm", "GenerateData", "BatchGenerate", "MEMOptimizer", "Detector", "Analysis"]:
    executables.append(EXE(pyz, a.scripts, [], exclude_binaries=True, name=name,
                           debug=False, bootloader_ignore_signals=False, strip=False,
                           upx=False, console=(name == "blr-rm")))
coll = COLLECT(*executables, a.binaries, a.datas, strip=False, upx=False, name="BLR-RM")
