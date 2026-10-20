import tempfile
from pathlib import Path
import unittest
from monitorize.desktop.remote_login_controller import configure,UNIT,unit_content


class ControllerTests(unittest.TestCase):
    def test_enable_and_disable_restore_existing_autostart_without_stopping_gui(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);desktop=root/'autostart/monitorize.desktop';desktop.parent.mkdir();desktop.write_bytes(b'original autostart')
            calls=[];configure(True,config_home=root,run=calls.append)
            self.assertFalse(desktop.exists())
            self.assertIn(('enable',UNIT),[tuple(c) for c in calls])
            unit=root/'systemd/user'/UNIT;self.assertIn('Restart=on-failure',unit.read_text())
            self.assertNotIn('After=graphical-session.target',unit.read_text())
            configure(False,config_home=root,run=calls.append)
            self.assertEqual(desktop.read_bytes(),b'original autostart');self.assertFalse(unit.exists())
            self.assertFalse(any('--now' in call or 'stop' in call for call in calls))

    def test_custom_unit_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);unit=root/'systemd/user'/UNIT;unit.parent.mkdir(parents=True);unit.write_text('custom')
            with self.assertRaises(ValueError):configure(True,config_home=root,run=lambda args:None)
            self.assertEqual(unit.read_text(),'custom')

    def test_unit_arguments_escape_percent_and_quotes(self):
        content=unit_content('/path/with % and "quote/python','/source %/linux')
        self.assertIn('%%',content);self.assertIn('\\"quote',content)
        with self.assertRaises(ValueError):unit_content('/bad\npath')
