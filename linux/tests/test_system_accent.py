"""Opt-in accent palette tests without altering desktop settings or calling D-Bus."""
import os
import subprocess
import sys
import unittest


class SystemAccentTest(unittest.TestCase):
    def test_accent_palette_and_opt_in(self):
        code = r'''
import tempfile
from pathlib import Path
from unittest.mock import patch
from PyQt6.QtCore import QUrl,QEventLoop,QTimer
from PyQt6.QtGui import QColor,QPalette
from PyQt6.QtWidgets import QApplication
from PyQt6.QtQml import QQmlEngine,QQmlComponent
from monitorize.desktop.system_accent import portal_color,system_accent
from monitorize.desktop.appearance import accent_colors,apply_palette
import monitorize.config.settings as settings
app=QApplication([])
with tempfile.TemporaryDirectory() as d:
    settings.CONFIG_DIR=d
    settings.CONFIG_FILE=str(Path(d)/'settings.ini')
    assert settings.load_general_settings()['use_system_accent'] is False
    for invalid in [(1,2,3),(-1,0,0),(float('nan'),0,0),None,(.5,.5)]:
        assert portal_color(invalid) is None
    assert portal_color((1,0,0)).name()=='#ff0000'
    source=system_accent(app)
    source.color=QColor('#bb2244')
    apply_palette(app,'light')
    assert app.palette().color(QPalette.ColorRole.Highlight).name()=='#1676d2'
    settings.save_general_settings(use_system_accent=True)
    apply_palette(app,'light')
    assert app.palette().color(QPalette.ColorRole.Highlight).name()=='#bb2244'
    engine=QQmlEngine()
    component=QQmlComponent(engine,QUrl.fromLocalFile(str(Path('linux/monitorize/qml/Theme.qml').resolve())))
    theme=component.create()
    assert theme, [e.toString() for e in component.errors()]
    for dark in (False,True):
        theme.setProperty('mode','dark' if dark else 'light')
        theme.setProperty('systemAccentColors',accent_colors(source.color,dark))
        theme.setProperty('useSystemAccent',True)
        assert theme.property('buttonBackground').name()=='#bb2244'
        assert theme.property('headingText').red()>theme.property('headingText').blue()
        assert theme.property('accent').red()>theme.property('accent').green()
        theme.setProperty('useSystemAccent',False)
        assert theme.property('buttonBackground').name()=='#1676d2'
    assert accent_colors(QColor('#ffff00'),False)['buttonText']=='#232629'
    assert accent_colors(QColor('#440000'),True)['buttonText']=='#ffffff'
    # Change notifications queue a bounded read; completion stays on the Qt thread.
    source._watching=True
    with patch('monitorize.desktop.system_accent.read_portal_accent',return_value=QColor('#228844')):
        source._setting_changed('org.freedesktop.appearance','accent-color',None)
        loop=QEventLoop();source.changed.connect(loop.quit);QTimer.singleShot(2000,loop.quit);loop.exec()
        assert source.color.name()=='#228844'
    settings.save_general_settings(use_system_accent=False)
    settings.save_general_settings(minimize_to_tray=True)
    assert settings.load_general_settings()['use_system_accent'] is False
    apply_palette(app,'dark')
    assert app.palette().color(QPalette.ColorRole.Highlight).name()=='#1676d2'
    del theme,component,engine
'''
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
