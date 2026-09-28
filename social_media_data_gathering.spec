# PyInstaller spec: builds a single-file binary for Mac/Windows.
# Usage:
#   pip install pyinstaller
#   pyinstaller social_media_data_gathering.spec
#
# Output: dist/social-media-data-gathering (Mac/Linux) or dist/social-media-data-gathering.exe (Windows)

# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

block_cipher = None

hiddenimports = []
hiddenimports += collect_submodules("yt_dlp")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("fastapi")
hiddenimports += collect_submodules("smdg")
hiddenimports += collect_submodules("curl_cffi")

datas = [("static", "static"), ("smdg/codebook.md", "smdg"), ("smdg/document.schema.json", "smdg")]
datas += collect_data_files("yt_dlp")
datas += collect_data_files("imageio_ffmpeg")  # bundled ffmpeg binary
datas += collect_data_files("curl_cffi")

binaries = collect_dynamic_libs("curl_cffi")

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="social-media-data-gathering",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if sys.platform == "darwin":
    app_bundle = BUNDLE(
        exe,
        name="social-media-data-gathering.app",
        bundle_identifier="com.kwartler.social-media-data-gathering",
    )
