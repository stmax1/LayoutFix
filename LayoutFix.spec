# PyInstaller spec: pyinstaller LayoutFix.spec
a = Analysis(
    ['layoutfix.py'],
    datas=[('icon.ico', '.')],
    hiddenimports=['pystray._win32'],
    excludes=['numpy', 'matplotlib'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='LayoutFix',
          icon='icon.ico', console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='LayoutFix', upx=False)
