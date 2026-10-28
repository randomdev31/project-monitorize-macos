# Build from repository root: python -m PyInstaller --noconfirm macos/Monitorize.spec
from pathlib import Path

root = Path(SPECPATH).parent
package = root / 'linux' / 'monitorize'
a = Analysis(
    [str(root / 'macos' / 'launcher.py')],
    pathex=[str(root / 'linux')],
    binaries=[(str(package / 'macos/native/monitorize-display'), 'monitorize/macos/native')],
    datas=[(str(package / 'assets/monitorize_desktop_logo.png'), 'monitorize/assets')],
    hiddenimports=[],
    excludes=['dbus', 'gi', 'PyQt6.QtQml', 'PyQt6.QtQuick'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Monitorize',
          console=False, target_arch='x86_64', codesign_identity='-')
collection = COLLECT(exe, a.binaries, a.datas, name='Monitorize')
app = BUNDLE(collection, name='Monitorize.app', codesign_identity='-', bundle_identifier='com.monitorize.macos.intel',
             info_plist={'LSMinimumSystemVersion': '12.0', 'NSHighResolutionCapable': True})
