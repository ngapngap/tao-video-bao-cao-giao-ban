# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

edge_tts_datas, edge_tts_binaries, edge_tts_hiddenimports = collect_all('edge_tts')
aiohttp_datas, aiohttp_binaries, aiohttp_hiddenimports = collect_all('aiohttp')
tabulate_datas, tabulate_binaries, tabulate_hiddenimports = collect_all('tabulate')


a = Analysis(
    ['app/main.py'],
    pathex=[],
    binaries=edge_tts_binaries + aiohttp_binaries + tabulate_binaries,
    datas=[
        ('workflow.md', '.'),
        ('app/assets', 'app/assets'),
    ] + edge_tts_datas + aiohttp_datas + tabulate_datas,
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
        'tabulate',
        'aiosignal',
        'frozenlist',
        'multidict',
        'yarl',
        'attrs',
        'charset_normalizer',
        'async_timeout',
    ] + edge_tts_hiddenimports + aiohttp_hiddenimports + tabulate_hiddenimports,
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
