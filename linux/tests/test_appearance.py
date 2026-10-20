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
from monitorize.desktop.appearance import apply_palette
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
    for mode,dark in [('dark',True),('light',False),('system',app.styleHints().colorScheme()==Qt.ColorScheme.Dark)]:
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
    for scheme,expected in [(Qt.ColorScheme.Dark,True),(Qt.ColorScheme.Light,False)]:
        app.styleHints().setColorScheme(scheme)
        app.processEvents()
        # Platforms may decline an explicit scheme request; follow the reported value.
        assert theme.property('dark')==(app.styleHints().colorScheme()==Qt.ColorScheme.Dark)
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
