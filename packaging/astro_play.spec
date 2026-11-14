# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for the downloadable Astro Play build.
# Build from the project root:   pyinstaller packaging/astro_play.spec --noconfirm
# Output: dist/AstroPlay/ (run AstroPlay.exe on Windows, ./AstroPlay on Linux).
#
# Built as a folder ("onedir"), not a single file: a one-file build unpacks itself to a temp folder on every launch,
# which makes the game noticeably slower to start. UPX is off for the same reason (and it upsets antivirus tools).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "data" / "donki_archive.json"), "data"),
    (str(ROOT / "data" / "osdr_studies.json"), "data"),
    (str(ROOT / "data" / "settings.json"), "data"),
    (str(ROOT / "data" / "knowledge_sources.txt"), "data"),
]
datas += collect_data_files("ursina", excludes=["**/*.py", "**/__pycache__/*"])
datas += collect_data_files("panda3d", excludes=["**/*.py", "**/__pycache__/*"])   # etc/Config.prc, models
datas += collect_data_files("arabic_reshaper")
binaries = collect_dynamic_libs("panda3d")           # display, audio and ffmpeg plugins load at runtime

hiddenimports = (
    collect_submodules("ursina", filter=lambda m: ".editor" not in m and ".build" not in m)
    + collect_submodules("astro")
    + ["panda3d.core", "panda3d.direct", "panda3d.physics", "panda3d.fx", "panda3d.egg", "direct.showbase.ShowBase"]
)

# Left out on purpose: ChromaDB and its ML stack (hundreds of MB, slow first start; the assistant falls back to
# keyword search), test tools, and the asset generators (the generated files are already in assets/).
excludes = [
    "chromadb", "onnxruntime", "torch", "tensorflow", "transformers", "tokenizers", "sentence_transformers",
    "pytest", "_pytest", "fontTools", "scipy", "matplotlib", "pandas", "IPython", "jupyter", "notebook",
    "tkinter", "unittest", "pydoc_data",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[str(ROOT / "packaging" / "rthook_panda3d.py")],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

icon = ROOT / "packaging" / "icon.ico"
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AstroPlay",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon) if icon.exists() and sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="AstroPlay")
