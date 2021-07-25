# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

datas = [
    ('images', 'images'),
    ('data', 'data'),
    ('settings.default.toml', '.')
]

a = Analysis(['src\\stroll.py'],
             pathex=[],
             binaries=[],
             datas=datas,
             hiddenimports=["pystray._win32"],
             hookspath=[],
             runtime_hooks=[],
             excludes=['altgraph', 'future', 'pefile', 'pyinstaller', 'pyinstaller-hooks-contrib', 'pywin32-ctypes'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='stroll',
          debug=True,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True , icon='images\\stroll.ico')
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='stroll')
