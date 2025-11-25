# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

security_datas = []

spec_path = globals().get('__file__')
if spec_path:
    spec_path = Path(spec_path).resolve()
else:
    argv_path = Path(sys.argv[0]).resolve()
    if argv_path.suffix == '.spec':
        spec_path = argv_path
    else:
        spec_path = (Path.cwd() / 'packaging' / 'earctl.spec').resolve()

repo_root = spec_path.parent.parent if spec_path and spec_path.exists() else Path.cwd()
security_dir = repo_root / "security"
if security_dir.exists():
    for file_path in security_dir.iterdir():
        if file_path.is_file():
            security_datas.append((str(file_path), "security"))


a = Analysis(
    ['../earCrawler/cli/__main__.py'],
    pathex=['..'],
    binaries=[],
    datas=security_datas,
    hiddenimports=collect_submodules('earCrawler.cli'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='earctl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)
