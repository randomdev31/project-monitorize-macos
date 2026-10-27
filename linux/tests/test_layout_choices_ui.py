"""Exercise the two-choice selector through real QML and backend persistence."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest

spec=importlib.util.spec_from_file_location('layout_ui_fixture',Path(__file__).with_name('test_host_configuration_ui.py'))
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
PREFIX=fixture.PROGRAM.split('            backend.startConfiguredListeners')[0]
SCENARIO=r'''
            from PyQt6.QtCore import QMetaObject,Q_ARG
            evaluate('navigate("DisplaySetupPage.qml")');settle()
            selector=view.rootObject().findChild(QObject,'displayBehaviorSelector')
            assert selector and selector.property('count')==2
            selector.setProperty('currentIndex',1)
            QMetaObject.invokeMethod(selector,'activated',Q_ARG(int,1))
            assert backend.configuration_state.draft['display_behavior']=='virtual_only'
            assert not backend.saveDisplayBehavior('primary')
            assert backend.loadDisplayBehavior()['modes']==['extend','virtual_only']
            view.setSource(QUrl());view.deleteLater();settle()
'''


class LayoutChoicesUiTest(unittest.TestCase):
    def test_x11_and_niri_select_virtual_only_without_saving_primary(self):
        for desktop,extra in [('x11',{'XDG_SESSION_TYPE':'x11','DISPLAY':':monitorize-test'}),('niri',{'XDG_SESSION_TYPE':'wayland','NIRI_SOCKET':'/nonexistent-monitorize-test-socket'})]:
            code=(PREFIX+SCENARIO).replace("'sway'",repr(desktop))
            # Feature discovery checks the CLI, but this scenario never invokes it.
            code=code.replace('app=QApplication([])',"tool_patch=patch('monitorize.platform.session_layout.shutil.which',return_value='/fake/tool');tool_patch.start()\napp=QApplication([])")
            env={**os.environ,**extra,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','PYTHONDONTWRITEBYTECODE':'1'}
            result=subprocess.run([sys.executable,'-c',code],env=env,text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,desktop+'\n'+result.stdout+result.stderr)
