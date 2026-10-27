"""Exercise real QML with fake networking; never request live authorization."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

PROGRAM=r'''
import copy
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from PyQt6.QtCore import QObject,QUrl,QEventLoop,QTimer,QMetaObject,Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtQml import QQmlExpression
from PyQt6.QtQuickWidgets import QQuickWidget
from monitorize.desktop.backend import MonitorizeBackend

app=QApplication([])
class Operations:
    version='2'
    calls=[]
    def discover(self):
        return {'profiles':[{'uuid':'uuid-one','name':'same-name','version':self.version,'active':True,'eligible':True,'configuration':'needs_setup'},
                            {'uuid':'uuid-two','name':'same-name','version':'4','active':False,'eligible':True,'configuration':'needs_setup'}],
                'status':{'code':'selection_required','message':'Fixture networks'}}
    def configure(self,uuid,version,password):
        # Retain only target/version; never retain the fixture password.
        self.calls.append((uuid,version))
        assert password=='fixture-password'
        self.version='3'
        return {'success':True,'code':'configured','message':'Configured for boot — verify after reboot.','boot_verified':False}
operations=Operations()
def settle():
    loop=QEventLoop();QTimer.singleShot(150,loop.quit);loop.exec()
with tempfile.TemporaryDirectory() as config:
    os.environ['XDG_CONFIG_HOME']=config
    with patch('monitorize.desktop.backend.get_local_ip',return_value='192.0.2.1'), \
         patch('monitorize.desktop.backend.find_sunshine_command',return_value=None), \
         patch('monitorize.desktop.backend.get_system_setup_status',return_value={'available':False}), \
         patch('monitorize.desktop.backend.load_general_settings',return_value={'system_setup_decided':True}), \
         patch('monitorize.desktop.backend.MonitorizeVkmsClient'), \
         patch('monitorize.platform.networkmanager_boot_wifi.WifiOperations',return_value=operations):
        backend=MonitorizeBackend('sway')
        view=QQuickWidget();view.resize(860,820)
        view.rootContext().setContextProperty('backend',backend)
        qml=Path('linux/monitorize/qml').resolve()
        try:
            view.setSource(QUrl.fromLocalFile(str(qml/'main.qml')))
            view.show();settle()
            assert view.status()==QQuickWidget.Status.Ready
            expression=QQmlExpression(view.rootContext(),view.rootObject(),'navigate("BootWifiSetupPage.qml")')
            expression.evaluate();assert not expression.hasError()
            for _ in range(10):
                settle()
                page=view.rootObject().findChild(QObject,'bootWifiSetupPage')
                if page and page.property('selectedUuid')=='uuid-one' and not backend.bootWifiBusy:break
            assert page is not None
            assert not view.rootObject().findChild(QObject,"globalBackButton").property("visible")
            assert page.property('selectedUuid')=='uuid-one'
            button=page.findChild(QObject,'bootWifiApply')
            password=page.findChild(QObject,'bootWifiPassword')
            assert page.findChild(QObject,'bootWifiConsent') is None
            assert not button.property('enabled')
            password.setProperty('text','fixture-password');settle()
            assert button.property('enabled')
            QMetaObject.invokeMethod(button,'clicked',Qt.ConnectionType.DirectConnection)
            assert password.property('text')==''
            for _ in range(10):
                settle()
                if operations.calls and not backend.bootWifiBusy:break
            assert operations.calls==[('uuid-one','2')]
            assert 'Configured for boot' in page.property('resultMessage')
            assert password.property('text')==''
            # New versions revoke stale consent and discard partially entered input.
            password.setProperty('text','fixture-password')
            operations.version='4';backend.refreshBootWifi()
            for _ in range(10):
                settle()
                if not backend.bootWifiBusy:break
            assert page.property('selectedVersion')=='4'
            print('Real QML setup, exact target, secret clearing and stale-version checks passed')
        finally:
            view.setSource(QUrl());view.close();backend.close();app.processEvents()
'''


class BootWifiUiTest(unittest.TestCase):
    def test_consent_selection_and_secret_lifetime_in_qml(self):
        environment=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software')
        result=subprocess.run([sys.executable,'-c',PROGRAM],cwd=Path(__file__).resolve().parents[2],
                              env=environment,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('stale-version checks passed',result.stdout)
