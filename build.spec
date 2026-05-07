# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

edge_tts_datas, edge_tts_binaries, edge_tts_hiddenimports = collect_all('edge_tts')


a = Analysis(
    ['app/main.py'],
    pathex=[],
    binaries=edge_tts_binaries,
    datas=[
        ('workflow.md', '.'),
        ('app/assets', 'app/assets'),
    ] + edge_tts_datas,
    hiddenimports=[
        'customtkinter',
        'pymupdf',
        'pdfplumber',
        'pydantic',
        'httpx',
        'keyring',
        'edge_tts',
        'edge_tts.voices',
        'aiohttp',
        'aiohttp.client',
        'aiohttp.connector',
        'aiohttp.web',
        'aiosignal',
        'frozenlist',
        'multidict',
        'yarl',
        'attrs',
        'charset_normalizer',
        'async_timeout',
    ] + edge_tts_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BaoCaoGiaoBan-VideoGenerator',
    debug=False,
    bootloader_ignore_signals=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
