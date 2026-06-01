# solar_twin.spec
# This file tells PyInstaller exactly what to include

block_cipher = None

a = Analysis(
    ['main.py'],                        # entry point
    pathex=['.'],                       # search path
    binaries=[],
    datas=[
        # include non-Python files the app needs
        ('config',   'config'),         # settings.py
        ('ui/styles', 'ui/styles'),     # theme.qss
        ('outputs',  'outputs'),        # model outputs folder
        ('logs',     'logs'),           # logs folder
    ],
    hiddenimports=[
        # packages PyInstaller misses automatically
        'xgboost',
        'xgboost.sklearn',
        'shap',
        'plotly',
        'plotly.graph_objects',
        'openpyxl',
        'sklearn',
        'sklearn.utils._typedefs',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SolarDigitalTwin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                      # False = no terminal window
    icon='assets/sun.ico',              # app icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SolarDigitalTwin',
)