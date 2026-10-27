"""Isolated palette and QML theme checks; no backend/services or live display."""
import os
import subprocess
import sys
import unittest


class AppearanceTest(unittest.TestCase):
    def test_modes_and_persistence(self):
        program = r'''
import tempfile,os
from pathlib import Path
from PyQt6.QtCore import QUrl,Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication
from PyQt6.QtQml import QQmlEngine,QQmlComponent
from monitorize.config.settings import load_general_settings,save_general_settings
from monitorize.desktop.appearance import apply_palette,system_dark
app=QApplication([])
with tempfile.TemporaryDirectory() as d:
    os.environ['XDG_CONFIG_HOME']=d
    import monitorize.config.settings as settings_module
    settings_module.CONFIG_DIR=d
    settings_module.CONFIG_FILE=str(Path(d)/'settings.ini')
    assert load_general_settings()['theme_mode']=='system'
    engine=QQmlEngine()
    component=QQmlComponent(engine,QUrl.fromLocalFile(str(Path('linux/monitorize/qml/Theme.qml').resolve())))
    theme=component.create()
    assert theme, [e.toString() for e in component.errors()]
    accent=None
    for mode,dark in [('dark',True),('light',False),('system',system_dark(app))]:
        save_general_settings(theme_mode=mode)
        assert load_general_settings()['theme_mode']==mode
        theme.setProperty('mode',mode)
        assert theme.property('dark')==dark
        apply_palette(app,mode)
        assert app.palette().color(QPalette.ColorRole.Text).lightness() > 128 if dark else app.palette().color(QPalette.ColorRole.Text).lightness() < 128
        current=theme.property('buttonBackground').name()
        assert current=='#1676d2'
        accent=current
        assert theme.property('background').lightness() < 128 if dark else theme.property('background').lightness() > 128
    theme.setProperty('mode','system')
    if hasattr(app.styleHints(),'setColorScheme'):
        for scheme,expected in [(Qt.ColorScheme.Dark,True),(Qt.ColorScheme.Light,False)]:
            app.styleHints().setColorScheme(scheme)
            app.processEvents()
            assert theme.property('dark')==system_dark(app)
    else:
        theme.setProperty('systemDarkFallback',system_dark(app))
        assert theme.property('dark')==system_dark(app)
    save_general_settings(minimize_to_tray=True)
    assert load_general_settings()['theme_mode']=='system'
    try:save_general_settings(theme_mode='invalid')
    except ValueError:pass
    else:raise AssertionError('Invalid theme accepted')
    del theme
    del component
    del engine
'''
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-c", program], env=env, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_qt64_fallback_preserves_native_palette_across_overrides(self):
        from types import SimpleNamespace
        from PyQt6.QtGui import QColor, QPalette
        from monitorize.desktop.appearance import system_dark
        for dark in (False, True):
            with self.subTest(dark=dark):
                palette = QPalette()
                palette.setColor(QPalette.ColorRole.Window, QColor('#202324' if dark else '#eff0f1'))
                app = SimpleNamespace(styleHints=lambda: SimpleNamespace(), palette=lambda: palette)
                self.assertEqual(system_dark(app), dark)
                palette.setColor(QPalette.ColorRole.Window, QColor('#eff0f1' if dark else '#202324'))
                self.assertEqual(system_dark(app), dark)
