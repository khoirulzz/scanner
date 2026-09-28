import os
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path.cwd()
ICON_PATH = ROOT / 'assets' / 'scanner.ico'
if not ICON_PATH.is_file():
    raise FileNotFoundError(f'Ikon aplikasi wajib tersedia: {ICON_PATH}')

APP_VERSION = os.environ.get('KK_SCANNER_VERSION', '0.0.0')
version_numbers = [int(value) for value in re.findall(r'\d+', APP_VERSION)[:4]]
version_tuple = tuple((version_numbers + [0, 0, 0, 0])[:4])
VERSION_INFO_PATH = ROOT / 'build' / 'version_info.txt'
VERSION_INFO_PATH.parent.mkdir(parents=True, exist_ok=True)
VERSION_INFO_PATH.write_text(
    f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={version_tuple}, prodvers={version_tuple}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Nalaro Dev'),
      StringStruct('FileDescription', 'KK Scanner Desktop'),
      StringStruct('FileVersion', '{APP_VERSION}'),
      StringStruct('InternalName', 'KK Scanner'),
      StringStruct('OriginalFilename', 'KK Scanner.exe'),
      StringStruct('ProductName', 'KK Scanner'),
      StringStruct('ProductVersion', '{APP_VERSION}')
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)""",
    encoding='utf-8',
)

hiddenimports = []
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('sqlalchemy.dialects.sqlite')

datas = [
    ('app/static', 'app/static'),
    ('app/templates', 'app/templates'),
    ('app/layouts', 'app/layouts'),
    (str(ICON_PATH), 'assets'),
]

analysis_excludes = [
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    'tkinter',
    'pytest',
    'alembic',
    'psycopg', 'psycopg_binary', 'psycopg2',
    'watchfiles', 'websockets',
]

a = Analysis(
    ['desktop/launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=analysis_excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KK Scanner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ICON_PATH),
    version=str(VERSION_INFO_PATH),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KK Scanner',
)
