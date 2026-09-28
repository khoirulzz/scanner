from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path.cwd()
ICON_PATH = ROOT / 'assets' / 'scanner.ico'

hiddenimports = []
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('sqlalchemy.dialects.sqlite')

datas = [
    ('app/static', 'app/static'),
    ('app/templates', 'app/templates'),
    ('app/layouts', 'app/layouts'),
]
if ICON_PATH.exists():
    datas.append((str(ICON_PATH), 'assets'))

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

exe_options = {}
if ICON_PATH.exists():
    exe_options['icon'] = str(ICON_PATH)

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
    **exe_options,
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
