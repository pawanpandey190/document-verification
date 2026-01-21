# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include any specific data files here if needed
        # ('.env', '.'), # Uncomment if you want to bundle .env (usually not recommended for clients)
    ],
    hiddenimports=[
        'openai',
        'pydantic',
        'pydantic_core',
        'langchain',
        'langchain_openai',
        'langchain_core',
        'tenacity',
        'boto3',
        'pdfplumber',
        'pdf2image',
        'PIL',
        'openpyxl',
        'pandas'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='DocumentValidator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True, # Set to True so you can see the log output and "Enter to close"
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
app = BUNDLE(
    exe,
    name='DocumentValidator.app',
    icon=None,
    bundle_identifier='com.validator.app',
)
