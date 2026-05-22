# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

from app.release import (
    APP_DESCRIPTION,
    APP_DISPLAY_NAME,
    APP_EXE_NAME,
    APP_LEGAL_COPYRIGHT,
    APP_PUBLISHER,
    APP_VERSION,
    APP_VERSION_TUPLE,
)


ROOT = Path.cwd()
ICON_PATH = ROOT / "assets" / "icons" / "whisperclip.ico"

binaries = collect_dynamic_libs("ctranslate2")
try:
    binaries += collect_dynamic_libs("onnxruntime")
except Exception:
    pass

version_info = None
if os.name == "nt":
    from PyInstaller.utils.win32.versioninfo import (  # type: ignore[attr-defined]
        VSVersionInfo,
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
    )

    version_info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=APP_VERSION_TUPLE,
            prodvers=APP_VERSION_TUPLE,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", APP_PUBLISHER),
                            StringStruct("FileDescription", APP_DESCRIPTION),
                            StringStruct("FileVersion", APP_VERSION),
                            StringStruct("InternalName", APP_EXE_NAME),
                            StringStruct("OriginalFilename", f"{APP_EXE_NAME}.exe"),
                            StringStruct("ProductName", APP_DISPLAY_NAME),
                            StringStruct("ProductVersion", APP_VERSION),
                            StringStruct("LegalCopyright", APP_LEGAL_COPYRIGHT),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=[],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "sounddevice",
        "numpy",
        "faster_whisper",
        "optimum.onnxruntime",
        "transformers",
        "transformers.models.whisper",
        "onnxruntime",
        "sentencepiece",
        "huggingface_hub",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    module_collection_mode={
        "optimum": "py",
        "transformers": "py",
    },
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
    version=version_info,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=APP_EXE_NAME,
)