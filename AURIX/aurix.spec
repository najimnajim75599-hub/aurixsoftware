# PyInstaller recipe. Build with:  pyinstaller --noconfirm --clean aurix.spec
# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['main.py'],
    pathex=['.'],
    datas=[('assets', 'assets')],
    hiddenimports=['PySide6.QtSvg', 'PySide6.QtSvgWidgets'],
    excludes=['tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtQml', 'PySide6.QtQuick',
              'PySide6.Qt3DCore', 'PySide6.QtMultimedia', 'PySide6.QtCharts', 'PySide6.QtDataVisualization'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AURIX',
          console=False, icon='assets/logo/aurix.ico' if __import__('os').path.exists('assets/logo/aurix.ico') else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AURIX')
