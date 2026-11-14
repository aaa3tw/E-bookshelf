# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
import sys
from pathlib import Path

BASE_DIR = Path('E:/AI_project/acrobat_bookshelf').resolve()
BACKEND_DIR = BASE_DIR / 'backend'

datas = [
    (str(BASE_DIR / 'frontend'), 'frontend'),
]
binaries = []
hiddenimports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'fastapi',
    'starlette',
    'pydantic',
    'pydantic_core',
    'sqlite3',
    'aiohttp',
    'requests',
    'charset_normalizer',
    'bs4',
    'ebooklib',
    'ebooklib.epub',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'opencc',
    'fitz',
    'pymupdf',
    'app_paths',
    'database',
    'book_service',
    'epub_converter',
    'zlib_client',
    'main',
    'crawler.service',
    'crawler.downloader',
    'crawler.adapters',
    'crawler.searcher',
    'crawler.exporter',
    'crawler.cleaner',
    'crawler.zlib_client',
    'crawler.epub_converter',
]

for pkg in ['opencc', 'fitz', 'pymupdf', 'ebooklib', 'uvicorn', 'fastapi']:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"Hook warning for {pkg}: {e}")

a = Analysis(
    ['E:/AI_project/acrobat_bookshelf/desktop_app.py'],
    pathex=[
        str(BASE_DIR),
        str(BACKEND_DIR),
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'torch', 'torchvision', 'torchaudio'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AcrobatBookshelf',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon='E:/AI_project/acrobat_bookshelf/app_icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AcrobatBookshelf',
)
